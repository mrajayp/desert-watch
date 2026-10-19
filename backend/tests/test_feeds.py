"""Feed discovery (collectors/feeds.py, plan C-R2.3): the homepage's <link rel=alternate>, the usual
paths and the WordPress API, accepted only when feedparser reads the feed cleanly and it is fresh; the
failure streak and auto-pause of outlet feeds (collectors/rss.py); the admin list; the nightly job.
Everything here runs against a fake HTTP transport: no request leaves the test."""
import inspect
import json
from datetime import date, timedelta

import httpx
from sqlalchemy import select

from app.collectors import feeds, rss
from app.models import Country, Item, Outlet, utcnow

from .conftest import login

TODAY = date(2026, 10, 19)
FEED = """<?xml version="1.0"?><rss version="2.0"><channel><title>t</title><link>https://x/</link>
<item><title>الكهرباء في طرابلس</title><link>https://x/1</link><pubDate>Sat, 10 Oct 2026 10:00:00 GMT</pubDate></item>
<item><title>Oil in Libya</title><link>https://x/2</link><pubDate>Fri, 09 Oct 2026 10:00:00 GMT</pubDate></item>
</channel></rss>"""
STALE = FEED.replace("10 Oct 2026", "11 Jul 2026").replace("09 Oct 2026", "10 Jul 2026")
BROKEN = "<?xml version='1.0'?><rss><channel><item><title>x</title><link>https://x/9</link>"
HOME = "<html lang='ar'><head><title>أخبار ليبيا</title>{links}</head><body><nav><a>ليبيا</a></nav></body></html>"


def _handler(request: httpx.Request) -> httpx.Response:
    u = str(request.url)
    routes = {
        "https://a.com/": (200, HOME.format(links="<link rel='alternate' type='application/rss+xml' href='/rss/all.xml'>")),
        "https://a.com/rss/all.xml": (200, FEED),
        "https://b.com/": (200, HOME.format(links="")), "https://b.com/feed/": (404, "no"), "https://b.com/rss": (200, FEED),
        "https://c.com/": (200, HOME.format(links="")),
        "https://c.com/wp-json/wp/v2/posts?per_page=1": (200, json.dumps([{"id": 1, "title": {"rendered": "x"}}])),
        "https://c.com/?feed=rss2": (200, FEED),
        "https://d.com/": (200, HOME.format(links="")),
        "https://e.com/": (200, HOME.format(links="<link href='https://e.com/old.xml' type='application/atom+xml' rel='alternate'>")),
        "https://e.com/old.xml": (200, STALE), "https://e.com/feed/": (200, BROKEN),
        "https://p.com/feed/": (200, FEED), "https://q.com/feed/": (500, "down"),
    }
    if u == "https://big.com/":
        return httpx.Response(200, content=b"<html>" + b"x" * (feeds.MAX_BYTES + 10))
    if u.startswith("https://dead.com"):
        raise httpx.ConnectError("refused", request=request)
    status, body = routes.get(u, (404, "not here"))
    return httpx.Response(status, text=body, headers={"content-type": "text/html" if u.endswith("/") else "application/xml"})


def _client():
    return httpx.Client(transport=httpx.MockTransport(_handler), headers={"User-Agent": "test"})


def _outlet(db, domain, articles=1, days_ago=30, **kw):
    c = db.scalar(select(Country))
    o = Outlet(country_id=c.id, name=domain, domain=domain, languages=["ar"], created_via="auto", **kw)
    db.add(o)
    db.flush()
    for i in range(articles):
        db.add(Item(country_id=c.id, kind="article", source_key="gnews", dedupe_key=f"url:{domain}/{i}", url=f"https://{domain}/{i}",
                    title="ليبيا", published_at=utcnow() - timedelta(days=days_ago), outlet_id=o.id, relevant=True, extra={}))
    db.commit()
    return o


def test_feed_links_and_feed_checks():
    html = ("<link rel=\"alternate\" type=\"application/rss+xml\" title=\"RSS\" href=\"/feed/\">"
            "<link type='application/atom+xml' rel='alternate' href='https://cdn.x/atom.xml'>"
            "<link rel='stylesheet' href='/s.css'><link rel='alternate' type='text/html' href='/en/'>"
            "<link rel='alternate' type='application/rss+xml' href='/feed/'>")
    assert feeds.feed_links(html, "https://x.com/") == ["https://x.com/feed/", "https://cdn.x/atom.xml"]
    assert feeds.check_feed(FEED.encode(), TODAY) == (True, "2 entries, newest 2026-10-10")
    assert feeds.check_feed(STALE.encode(), TODAY) == (False, "newest entry 2026-07-11")
    assert feeds.check_feed(BROKEN.encode(), TODAY)[0] is False and "not clean" in feeds.check_feed(BROKEN.encode(), TODAY)[1]
    assert feeds.check_feed(b"<rss version='2.0'><channel><title>t</title></channel></rss>", TODAY) == (False, "no entries")


def test_discovery_finds_feeds_by_link_path_and_wordpress_api_and_keeps_the_rest_for_later(db):
    c = db.scalar(select(Country))
    a, b, cc, d, e = (_outlet(db, dom, articles=n) for dom, n in (("a.com", 9), ("b.com", 8), ("c.com", 7), ("d.com", 6), ("e.com", 5)))
    _outlet(db, "facebook.com/page", articles=20)              # a social account: no homepage to crawl
    _outlet(db, "nothing.com", articles=0)                     # dormant: not a candidate
    _outlet(db, "has.com", articles=30, rss_url="https://has.com/feed/")   # already has a feed
    assert [o.domain for o in feeds.candidates(db, c, 50, TODAY)] == ["a.com", "b.com", "c.com", "d.com", "e.com"]
    with _client() as client:
        res = feeds.discover(db, limit=50, client=client, today=TODAY, min_interval=0)
    assert res.rows == 3 and res.errors == 0
    assert res.detail.startswith("5 outlets searched, 3 feeds found") and "a.com: link_rel" in res.detail
    db.expire_all()
    assert (a.rss_url, a.external["feed"]) == ("https://a.com/rss/all.xml", {"found_at": "2026-10-19", "how": "link_rel", "url": "https://a.com/rss/all.xml"})
    assert (b.rss_url, b.external["feed"]["how"]) == ("https://b.com/rss", "/rss")
    assert (cc.rss_url, cc.external["feed"]["how"]) == ("https://c.com/?feed=rss2", "wp-json")
    assert d.rss_url is None and d.external["feed_search"] == {"at": "2026-10-19", "result": "none", "tried": 6}   # 5 paths + wp-json
    assert e.rss_url is None and e.external["feed_search"]["result"] == "none"   # a stale feed and a broken one are not feeds
    # the homepage's scope signals are kept as a suggestion only (register.py): no label was written
    assert a.external["scope_suggestion"]["scope"] == "libyan" and a.external["scope_suggestion"]["confidence"] == "unverified"
    from app.api.common import outlet_categories
    assert not outlet_categories(db, [a.id, b.id, cc.id, d.id, e.id])
    # searched outlets are not asked again for RECHECK_DAYS; a later night has nothing left
    assert feeds.candidates(db, c, 50, TODAY) == []
    assert [o.domain for o in feeds.candidates(db, c, 50, TODAY + timedelta(days=feeds.RECHECK_DAYS + 1))] == ["d.com", "e.com"]


def test_discovery_takes_the_busiest_first_up_to_its_limit_and_survives_big_or_dead_sites(db):
    c = db.scalar(select(Country))
    big = _outlet(db, "big.com", articles=9)
    dead = _outlet(db, "dead.com", articles=8)
    a = _outlet(db, "a.com", articles=7)
    with _client() as client:
        res = feeds.discover(db, limit=2, client=client, today=TODAY, min_interval=0)
    assert res.rows == 0 and "2 outlets searched" in res.detail
    db.expire_all()
    assert big.external["feed_search"]["result"] == "none" and dead.external["feed_search"]["result"] == "none"
    assert "feed_search" not in (a.external or {})                        # beyond tonight's limit
    assert [o.domain for o in feeds.candidates(db, c, 50, TODAY)] == ["a.com"]


def test_paused_feeds_are_tried_again_after_a_fortnight(db):
    p = _outlet(db, "p.com", articles=3, rss_url="https://p.com/feed/",
                external={"feed_paused": {"since": "2026-09-20", "failures": 10, "error": "x"}, "feed_failed_runs": 10})
    q = _outlet(db, "q.com", articles=3, rss_url="https://q.com/feed/",
                external={"feed_paused": {"since": "2026-10-15", "failures": 10, "error": "x"}})
    with _client() as client:
        res = feeds.discover(db, limit=50, client=client, today=TODAY, min_interval=0)
    assert "1 paused feeds tried again, 1 unpaused" in res.detail
    db.expire_all()
    assert "feed_paused" not in p.external and "feed_failed_runs" not in p.external
    assert q.external["feed_paused"]["since"] == "2026-10-15" and "retried_at" not in q.external["feed_paused"]
    q.external = {"feed_paused": {"since": "2026-09-01", "failures": 10, "error": "x"}}
    db.commit()
    with _client() as client:
        feeds.discover(db, limit=50, client=client, today=TODAY, min_interval=0)
    db.expire_all()
    assert q.external["feed_paused"]["retried_at"] == "2026-10-19" and q.external["feed_paused"]["error"] == "HTTP 500"


def test_an_outlet_feed_is_paused_after_ten_failed_runs_and_a_new_address_clears_it(client, users, db, monkeypatch):
    z = _outlet(db, "z.com", articles=0, rss_url="https://z.com/feed/")
    for o in db.scalars(select(Outlet).where(Outlet.rss_url.is_not(None), Outlet.id != z.id)):
        o.active = False                                     # the seeded feeds stay out of this run
    db.commit()
    calls = []

    def failing(client, url, **kw):
        calls.append(url)
        raise httpx.ConnectError("refused")

    monkeypatch.setattr(rss, "polite_get", failing)
    for n in range(1, rss.FEED_PAUSE_AFTER + 1):
        res = rss.collect(db)
        db.expire_all()
        assert res.errors == 1 and len(calls) == n
        if n < rss.FEED_PAUSE_AFTER:
            assert z.external["feed_failed_runs"] == n and "feed_paused" not in z.external
            assert res.detail == f"z.com: refused ({n} in a row)"
    assert z.external["feed_paused"]["failures"] == rss.FEED_PAUSE_AFTER
    assert res.detail == "z.com: paused after 10 failed runs in a row, last refused"
    res = rss.collect(db)
    assert len(calls) == rss.FEED_PAUSE_AFTER and res.errors == 0 and res.detail == "1 paused feed skipped"
    login(client, "admin@example.org", "admin-password-1")
    listed = client.get("/api/admin/feeds").json()
    assert [p["domain"] for p in listed["paused"]] == ["z.com"] and listed["paused"][0]["failures"] == 10
    assert listed["with_feed"] >= 1 and "candidates_left" in listed and listed["nightly"] == feeds.NIGHTLY
    assert client.patch(f"/api/outlets/{z.id}", json={"rss_url": "https://z.com/rss"}).status_code == 200
    db.expire_all()
    assert z.rss_url == "https://z.com/rss" and "feed_paused" not in z.external and "feed_failed_runs" not in z.external
    client.post("/api/auth/logout")
    login(client, "j@example.org", "journo-password-1")
    assert client.get("/api/admin/feeds").status_code == 403


def test_the_admin_list_shows_discovered_feeds(client, users, db):
    _outlet(db, "a.com", articles=9)
    with _client() as c:
        feeds.discover(db, limit=50, client=c, today=TODAY, min_interval=0)
    login(client, "admin@example.org", "admin-password-1")
    listed = client.get("/api/admin/feeds").json()
    assert [(d["domain"], d["how"], d["found_at"]) for d in listed["discovered"]] == [("a.com", "link_rel", "2026-10-19")]
    assert listed["searched"] == {"outlets": 1, "last": "2026-10-19", "found": 1} and listed["paused"] == []


def test_nightly_runs_the_discovery_and_the_strip_knows_it(db, capsys):
    from app import jobs
    from app.cli import main
    from app.collectors import EXTRA_HEALTH, SCHEDULE_HOURS, stale_hours
    nightly = inspect.getsource(jobs).split("def nightly():", 1)[1].split("\ndef ", 1)[0]
    assert nightly.index('collect("gnews_social")') < nightly.index("_discover_feeds()")
    assert "discover_feeds" in jobs.JOBS and "discover_feeds" in EXTRA_HEALTH
    assert SCHEDULE_HOURS["discover_feeds"] == 24 and stale_hours("discover_feeds") == 48
    # the command on an empty register makes no request at all (no candidate) and reports a clean run
    assert main(["discover-feeds", "--limit", "5"]) == 0
    out = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert out["status"] == "ok" and out["changed"] == 0 and out["detail"].startswith("0 outlets searched")
