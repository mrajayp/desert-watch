import json
from datetime import date, datetime, timedelta
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
from sqlalchemy import select

from app import resolve
from app.ingest import load_rules, store_article
from app.models import Item, Outlet

FIXTURES = json.loads((Path(__file__).parent / "fixtures" / "resolve_pairs.json").read_text(encoding="utf-8"))


@pytest.fixture()
def no_sleep(monkeypatch):
    monkeypatch.setattr("app.collectors.base.time.sleep", lambda _: None)


def test_matcher_on_hand_checked_pairs():
    for a, b in FIXTURES["same"]:
        assert resolve.title_score(a, b) >= resolve.MATCH_JACCARD, (a, b)
    for a, b in FIXTURES["different"]:
        assert resolve.title_score(a, b) < resolve.MATCH_JACCARD, (a, b)
    assert len(FIXTURES["same"]) >= 30 and len(FIXTURES["different"]) >= 20


def test_title_helpers():
    assert resolve.clean_title("#ليبيا | مؤسسة النفط تعلن الإيرادات") == "مؤسسة النفط تعلن الإيرادات"
    assert resolve.clean_title("Oil &amp; gas talks") == "Oil & gas talks"
    assert resolve.search_terms("ليبيا.. مؤسسة النفط: حولنا 1.448 مليار دولار إلى الحساب") == "ليبيا مؤسسة النفط حولنا 448 مليار"
    assert resolve.url_date("https://www.alsaaa24.com/2026/10/15/slug/") == date(2026, 10, 15)
    assert resolve.url_date("https://www.libyaakhbar.com/breaking/2897514.html") is None
    assert resolve.same_site("https://www.eanlibya.com/x", "eanlibya.com")
    assert not resolve.same_site("https://eanlibya.com.evil.example/x", "eanlibya.com")


PUB = datetime(2026, 10, 15, 18, 3)
TITLE = "مؤسسة النفط الليبية: حولنا 1.448 مليار دولار إلى الحساب السيادي خلال أكتوبر"


def wp_handler(calls: list, hits: list, posts: dict | None = None, wp: bool = True):
    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        path = request.url.path
        if not wp:
            return httpx.Response(404, text="<html>Not Found</html>")
        if path.endswith("/wp-json/wp/v2/search"):
            q = parse_qs(urlsplit(str(request.url)).query)
            if q.get("search") == ["news"]:
                return httpx.Response(200, json=[])
            return httpx.Response(200, json=hits)
        if "/wp-json/wp/v2/posts/" in path:
            return httpx.Response(200, json=(posts or {}).get(path.rsplit("/", 1)[1], {}))
        return httpx.Response(404)
    return handler


def hit(pid: int, title: str, url: str, host: str = "www.libyaakhbar.com") -> dict:
    return {"id": pid, "title": title, "url": url, "type": "post",
            "_links": {"self": [{"href": f"https://{host}/wp-json/wp/v2/posts/{pid}"}]}}


def test_wp_match_checks_title_then_date(no_sleep):
    o = Outlet(name="Libya Akhbar", domain="libyaakhbar.com")
    calls = []
    hits = [hit(1, "#ليبيا | تغيير جديد في أسعار الصرف", "https://www.libyaakhbar.com/breaking/1.html"),
            hit(2, "#ليبيا | " + TITLE, "https://www.libyaakhbar.com/breaking/2.html"),     # right title, a week old
            hit(3, TITLE + ".", "https://www.libyaakhbar.com/breaking/3.html"),             # right title and date
            hit(4, TITLE, "https://elsewhere.example/breaking/4.html")]                     # another site: ignored
    posts = {"2": {"date_gmt": "2026-10-08T10:00:00"}, "3": {"date_gmt": "2026-10-15T17:58:00"}}
    with httpx.Client(transport=httpx.MockTransport(wp_handler(calls, hits, posts))) as c:
        assert resolve.wp_match(c, o, TITLE, PUB) == "https://www.libyaakhbar.com/breaking/3.html"
    search = [u for u in calls if "/search" in u]
    assert len(search) == 1
    q = parse_qs(urlsplit(search[0]).query)
    assert q["search"] == ["مؤسسة النفط الليبية حولنا 448 مليار"] and q["per_page"] == ["5"]
    assert not any("posts/1" in u or "posts/4" in u for u in calls)   # date fetched only for title matches


def test_wp_match_uses_date_in_url_without_extra_request(no_sleep):
    o = Outlet(name="Alsaaa24", domain="alsaaa24.com")
    calls = []
    hits = [hit(9, TITLE, "https://www.alsaaa24.com/2026/10/15/slug/", host="www.alsaaa24.com")]
    with httpx.Client(transport=httpx.MockTransport(wp_handler(calls, hits))) as c:
        assert resolve.wp_match(c, o, TITLE, PUB) == "https://www.alsaaa24.com/2026/10/15/slug/"
        assert resolve.wp_match(c, o, TITLE, PUB + timedelta(days=4)) is None
    assert not any("/posts/" in u for u in calls)


def _gnews(db, country_id, rules, k, title, published, domain):
    item, _ = store_article(db, country_id, rules, url=f"https://news.google.com/rss/articles/CBM{k}?oc=5",
                            title=title, published_at=published, source_key="gnews", outlet_domain=domain)
    return item


def test_run_resolves_by_copy_and_wp_and_never_changes_url(db, no_sleep):
    country_id = db.scalar(select(Outlet.country_id).limit(1))
    rules = load_rules(db, country_id)
    now = datetime(2026, 10, 16, 6)
    copy_title = "Libya: power cuts return to Sabha as demand rises in the heat"
    store_article(db, country_id, rules, url="https://feedsite.ly/news/1", title=copy_title,
                  published_at=PUB - timedelta(hours=3), source_key="rss")
    a = _gnews(db, country_id, rules, "a", copy_title, PUB, "feedsite.ly")
    b = _gnews(db, country_id, rules, "b", "ليبيا: " + TITLE, PUB, "libyaakhbar.com")
    miss = _gnews(db, country_id, rules, "c", "Libya: a story nobody else carried today at all", PUB, "nowp.ly")
    tco = _gnews(db, country_id, rules, "d", "Libya: a link shortener posing as an outlet", PUB, "t.co")
    old = _gnews(db, country_id, rules, "e", "Libya: too old to look up any more", now - timedelta(days=20), "libyaakhbar.com")
    db.commit()
    urls = {i.id: i.url for i in (a, b, miss, tco, old)}

    calls = []

    def handler(request):
        if request.url.host.endswith("nowp.ly"):
            return wp_handler(calls, [], wp=False)(request)
        return wp_handler(calls, [hit(5, "#ليبيا | ليبيا: " + TITLE, "https://www.libyaakhbar.com/breaking/5.html")],
                          {"5": {"date_gmt": "2026-10-15T18:00:00"}})(request)

    with httpx.Client(transport=httpx.MockTransport(handler)) as c:
        stats = resolve.run(db, days=14, limit=10, client=c, now=now)
    assert (stats["copy"], stats["wp_search"], stats["searched"], stats["no_site_search"]) == (1, 1, 1, 1)
    assert stats["skipped_outlets"] == 1 and stats["probed"] == 2
    for i in (a, b, miss, tco, old):
        db.refresh(i)
    assert a.extra["resolved_url"] == "https://feedsite.ly/news/1" and a.extra["resolved_via"] == "copy"
    assert b.extra["resolved_url"] == "https://www.libyaakhbar.com/breaking/5.html" and b.extra["resolved_via"] == "wp_search"
    assert "resolved_url" not in miss.extra and miss.extra["resolve_tries"] == 1
    assert "resolved_url" not in old.extra and "resolve_tries" not in old.extra
    assert {i.id: i.url for i in (a, b, miss, tco, old)} == urls          # item.url is the dedupe key: untouched
    probes = {o.domain: (o.external or {}).get("wp_json") for o in db.scalars(select(Outlet).where(
        Outlet.domain.in_(("libyaakhbar.com", "nowp.ly", "feedsite.ly"))))}
    assert probes["libyaakhbar.com"]["ok"] is True and probes["nowp.ly"]["ok"] is False
    assert probes["feedsite.ly"] is None    # resolved from a copy: no request to the site at all

    # second run: the probe is cached, the miss is tried once more, then left alone
    n_probe = sum("search=news" in u for u in calls)
    with httpx.Client(transport=httpx.MockTransport(handler)) as c:
        resolve.run(db, days=14, limit=10, client=c, now=now)
        third = resolve.run(db, days=14, limit=10, client=c, now=now)
    assert sum("search=news" in u for u in calls) == n_probe
    db.refresh(miss)
    assert miss.extra["resolve_tries"] == resolve.MAX_TRIES and third["candidates"] == 0


def test_private_addresses_are_refused():
    with pytest.raises(Exception):
        resolve._public_only(httpx.Request("GET", "http://127.0.0.1/wp-json/wp/v2/search"))


def test_site_that_does_not_answer_is_left_for_the_next_run(db, no_sleep):
    country_id = db.scalar(select(Outlet.country_id).limit(1))
    rules = load_rules(db, country_id)
    now = datetime(2026, 10, 16, 6)
    items = [_gnews(db, country_id, rules, f"slow{k}", f"Libya: slow site story number {k} about Sabha water",
                    PUB - timedelta(hours=k), "slow.ly") for k in range(3)]
    db.commit()
    calls = []

    def handler(request):
        calls.append(str(request.url))
        raise httpx.ConnectTimeout("timed out")

    with httpx.Client(transport=httpx.MockTransport(handler)) as c:
        stats = resolve.run(db, days=14, limit=10, client=c, now=now)
    assert len(calls) == 1 and stats["site_down"] == 1 and stats["searched"] == 0
    o = db.scalar(select(Outlet).where(Outlet.domain == "slow.ly"))
    assert "wp_json" not in (o.external or {})                     # nothing cached: probe again next run
    for it in items:
        db.refresh(it)
        assert "resolve_tries" not in it.extra


def test_busiest_sites_first_and_limits(db, no_sleep):
    """Probes go to the sites with the most waiting links; searches are capped and shared round-robin."""
    country_id = db.scalar(select(Outlet.country_id).limit(1))
    rules = load_rules(db, country_id)
    now = datetime(2026, 10, 16, 6)
    for dom, n in (("big.ly", 5), ("mid.ly", 2), ("small.ly", 1)):
        for k in range(n):
            _gnews(db, country_id, rules, f"{dom}{k}", f"Libya: {dom} story {k} on the Sabha water supply cuts",
                   PUB - timedelta(hours=k), dom)
    db.commit()
    calls = []
    with httpx.Client(transport=httpx.MockTransport(wp_handler(calls, []))) as c:
        stats = resolve.run(db, days=14, limit=4, probes=2, client=c, now=now)
    probed = [urlsplit(u).hostname for u in calls if "search=news" in u]
    assert probed == ["big.ly", "mid.ly"] and stats["probed"] == 2      # small.ly waits for a later run
    searched = [urlsplit(u).hostname for u in calls if "search=news" not in u]
    assert searched == ["big.ly", "mid.ly", "big.ly", "mid.ly"] and stats["searched"] == 4
    small = db.scalar(select(Outlet).where(Outlet.domain == "small.ly"))
    assert "wp_json" not in (small.external or {})
