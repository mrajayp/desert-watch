from datetime import datetime, timedelta
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
from sqlalchemy import select

from app import settings
from app.collectors import fb_engagement
from app.collectors.base import run_collector
from app.ingest import load_rules, store_article
from app.models import ItemEngagement, Outlet, SourceRun

NOW = datetime(2026, 10, 16, 12)


@pytest.fixture()
def keys(monkeypatch):
    monkeypatch.setattr(settings, "FB_APP_ID", "123")
    monkeypatch.setattr(settings, "FB_APP_SECRET", "s3cret")
    monkeypatch.setattr(settings, "FB_DAILY_URLS", 400)
    monkeypatch.setattr("app.collectors.base.time.sleep", lambda _: None)


def _art(db, cid, rules, url, hours_old, source="rss", outlet_domain=None, extra=None, title=None):
    item, _ = store_article(db, cid, rules, url=url, title=title or f"Libya: power cuts in Sabha {url}",
                            published_at=NOW - timedelta(hours=hours_old), source_key=source,
                            outlet_domain=outlet_domain, extra=extra)
    return item


@pytest.fixture()
def articles(db):
    cid = db.scalar(select(Outlet.country_id).limit(1))
    rules = load_rules(db, cid)
    a = {
        "h48": _art(db, cid, rules, "https://www.almarsad.co/news/1", 50),
        "d7": _art(db, cid, rules, "https://news.google.com/rss/articles/CBMx?oc=5", 7 * 24 + 2, source="gnews",
                   outlet_domain="libyaakhbar.com", extra={"resolved_url": "https://www.libyaakhbar.com/breaking/9.html"}),
        "google_only": _art(db, cid, rules, "https://news.google.com/rss/articles/CBMy?oc=5", 50, source="gnews",
                            outlet_domain="alwasat.ly"),
        "lana": _art(db, cid, rules, "https://lana.gov.ly/post.php?id=1", 50),
        "young": _art(db, cid, rules, "https://www.almarsad.co/news/2", 10),
        "stale": _art(db, cid, rules, "https://www.almarsad.co/news/3", 5 * 24),   # missed the 48 h window
        "page": _art(db, cid, rules, "https://www.facebook.com/SomePage/posts/1", 50),
    }
    db.commit()
    return a


def graph(calls, error=None, usage=None):
    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if error:
            return httpx.Response(400, json={"error": {"message": "x", "type": "OAuthException", "code": error}})
        ids = parse_qs(urlsplit(str(request.url)).query)["ids"][0].split(",")
        body = {u: {"engagement": {"reaction_count": 10, "comment_count": 2, "share_count": 3,
                                   "comment_plugin_count": 0}, "id": u} for u in ids}
        headers = {"x-app-usage": usage} if usage else {}
        return httpx.Response(200, json=body, headers=headers)
    return handler


def test_awaiting_key_until_both_are_set(db, monkeypatch):
    monkeypatch.setattr(settings, "FB_APP_ID", "123")
    monkeypatch.setattr(settings, "FB_APP_SECRET", None)
    run = run_collector(db, "fb_url", fb_engagement.collect)
    assert run.status == "awaiting_key" and "DW_FB_APP_SECRET" in run.error


def test_reads_48h_and_7d_with_the_app_token(db, keys, articles):
    calls = []
    with httpx.Client(transport=httpx.MockTransport(graph(calls))) as c:
        res = fb_engagement.collect(db, client=c, now=NOW)
    assert res.rows == 2 and res.errors == 0
    q = parse_qs(urlsplit(str(calls[0].url)).query)
    assert calls[0].url.path == "/v26.0/" and q["fields"] == ["engagement"] and "access_token" not in q
    assert calls[0].headers["authorization"] == "Bearer 123|s3cret"     # the token never goes in the URL
    assert q["ids"][0].split(",") == ["https://www.libyaakhbar.com/breaking/9.html", "https://www.almarsad.co/news/1"]
    rows = {r.item_id: r for r in db.scalars(select(ItemEngagement).where(ItemEngagement.source == "fb_url"))}
    assert set(rows) == {articles["h48"].id, articles["d7"].id}
    r = rows[articles["h48"].id]
    assert (r.age_bucket, r.reactions, r.comments, r.shares, r.total) == ("48h", 10, 2, 3, 15)
    assert r.raw["url"] == "https://www.almarsad.co/news/1" and r.raw["age_hours"] == 50
    assert rows[articles["d7"].id].age_bucket == "7d"
    # the same readings are never taken twice
    with httpx.Client(transport=httpx.MockTransport(graph(calls))) as c:
        again = fb_engagement.collect(db, client=c, now=NOW + timedelta(hours=6))
    assert again.rows == 0 and len(calls) == 1


def test_rate_limit_stops_the_run(db, keys, articles):
    calls = []
    with httpx.Client(transport=httpx.MockTransport(graph(calls, error=4))) as c:
        res = fb_engagement.collect(db, client=c, now=NOW)
    assert res.rows == 0 and res.errors == 1 and "code 4" in res.detail and len(calls) == 1
    assert not db.scalars(select(ItemEngagement)).all()


def test_usage_header_and_daily_budget(db, keys, articles, monkeypatch):
    monkeypatch.setattr(fb_engagement, "BATCH", 1)
    calls = []
    with httpx.Client(transport=httpx.MockTransport(graph(calls, usage='{"call_count": 80, "total_time": 5}'))) as c:
        res = fb_engagement.collect(db, client=c, now=NOW)
    assert res.rows == 1 and len(calls) == 1 and "cap" in res.detail
    monkeypatch.setattr(settings, "FB_DAILY_URLS", 1)       # one lookup already used in the last 24 h
    with httpx.Client(transport=httpx.MockTransport(graph(calls))) as c:
        res = fb_engagement.collect(db, client=c, now=NOW + timedelta(hours=1))
    assert res.rows == 0 and len(calls) == 1 and res.detail == "Daily budget used."


def test_secret_never_reaches_the_run_log(db, keys, articles):
    def boom(request):
        raise httpx.ConnectError(f"cannot reach {request.url}")
    with httpx.Client(transport=httpx.MockTransport(boom)) as c:
        run = run_collector(db, "fb_url", lambda s: fb_engagement.collect(s, client=c, now=NOW))
    run = db.get(SourceRun, run.id)
    assert run.status == "error" and "s3cret" not in (run.error or "") and "ConnectError" in run.error


def test_secret_never_reaches_the_server_log(db, keys, articles, caplog):
    import logging
    import app.main  # noqa: F401  (sets the httpx log level the server runs with)
    assert logging.getLogger("httpx").getEffectiveLevel() >= logging.WARNING
    caplog.set_level(logging.INFO, logger="httpx")       # even with request lines logged, no secret
    calls = []
    with httpx.Client(transport=httpx.MockTransport(graph(calls))) as c:
        res = fb_engagement.collect(db, client=c, now=NOW)
    assert res.rows == 2 and calls
    assert "graph.facebook.com" in caplog.text and "s3cret" not in caplog.text
    assert all("s3cret" not in str(r.url) for r in calls)


def test_empty_reading_is_asked_once_more_then_stands(db, keys, articles):
    calls = []

    def handler(request):
        calls.append(request)
        ids = parse_qs(urlsplit(str(request.url)).query)["ids"][0].split(",")
        # Facebook echoes the 7-day URL with another scheme and a trailing slash and has nothing for the other
        return httpx.Response(200, json={u.replace("https://", "http://") + "/": {
            "engagement": {"reaction_count": 4, "comment_count": 0, "share_count": 1}, "id": u}
            for u in ids if "libyaakhbar" in u})

    for k in range(3):
        with httpx.Client(transport=httpx.MockTransport(handler)) as c:
            fb_engagement.collect(db, client=c, now=NOW + timedelta(hours=6 * k))
    rows = {r.item_id: r for r in db.scalars(select(ItemEngagement).where(ItemEngagement.source == "fb_url"))}
    assert rows[articles["d7"].id].total == 5                    # matched despite the different echo
    miss = rows[articles["h48"].id]
    assert miss.total is None and miss.raw["missing"] and miss.raw["tries"] == fb_engagement.MISSING_TRIES
    asked = [parse_qs(urlsplit(str(r.url)).query)["ids"][0] for r in calls]
    assert sum("almarsad.co/news/1" in a for a in asked) == 2 and len(calls) == 2   # third run: nothing due


def test_url_key():
    k = fb_engagement.url_key
    assert k("https://www.libyaakhbar.com/breaking/9.html") == k("http://libyaakhbar.com/breaking/9.html/")
    assert k("https://ex.ly/%D9%84%D9%8A%D8%A8%D9%8A%D8%A7") == k("https://ex.ly/ليبيا")
    assert k("https://ex.ly/post.php?id=1") != k("https://ex.ly/post.php?id=2")
