"""Outlet RSS feeds (Arabic + English), and YouTube channel feeds. Only items matching at least one
theme are kept."""
import calendar
import time
from datetime import datetime, timezone

import feedparser
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..ingest import load_rules, store_article
from ..models import Outlet
from ..textnorm import detect_lang
from .base import RunResult, http_client, polite_get

import re

_TAGS = re.compile(r"<[^>]+>")
YOUTUBE_FEED = "youtube.com/feeds/videos.xml"
YOUTUBE_TRIES = 3
YOUTUBE_BACKOFF = 3.0       # seconds, doubled after each failed try
YOUTUBE_FAILED_RUNS = 3     # a channel feed counts as an error only after this many failed runs in a row
# An outlet feed that fails this many runs in a row is paused (external.feed_paused): the hourly run
# skips it, so a dead feed no longer costs a request and an error line every hour. The nightly feed
# discovery (feeds.py) tries a paused feed again after a fortnight and unpauses it when it reads
# cleanly; an admin who sets a new address clears the pause (api/outlets.py).
FEED_PAUSE_AFTER = 10


def _youtube_feed(client, url: str, tries: int = YOUTUBE_TRIES):
    """YouTube channel feeds answer 404 or 500 to about half of all requests (2026-10-16) and then
    work on the next try, so we try three times with a pause."""
    for attempt in range(tries):
        try:
            r = polite_get(client, url, min_interval=1.0, retries=0)
            r.raise_for_status()
            return feedparser.parse(r.content)
        except Exception:  # noqa: BLE001
            if attempt == tries - 1:
                raise
            time.sleep(YOUTUBE_BACKOFF * 2 ** attempt)


def _store_entries(s: Session, o: Outlet, rules, feed, source_key: str) -> int:
    rows = 0
    for e in feed.entries:
        when = e.get("published_parsed") or e.get("updated_parsed")
        if not when or not e.get("link"):
            continue
        snippet = _TAGS.sub(" ", e.get("summary", ""))[:600]
        title = e.get("title", "")
        _, created = store_article(
            s, o.country_id, rules, url=e.link, title=title, snippet=snippet,
            published_at=datetime.utcfromtimestamp(calendar.timegm(when)), source_key=source_key,
            lang=detect_lang(title + " " + snippet), outlet_domain=o.domain, outlet_name=o.name,
            require_theme=True, outlet_cache={o.domain: o})
        rows += created
    s.commit()
    return rows


def _feed_outlets(s: Session, youtube: bool) -> list[Outlet]:
    q = select(Outlet).where(Outlet.rss_url.is_not(None), Outlet.active.is_(True))
    feed = Outlet.rss_url.like(f"%{YOUTUBE_FEED}%")
    return s.scalars(q.where(feed if youtube else ~feed)).all()


def collect(s: Session) -> RunResult:
    """Outlet websites' own feeds. YouTube channels run as their own collector (collect_youtube),
    so a YouTube outage shows on its own line in source health. A feed that fails FEED_PAUSE_AFTER
    runs in a row is paused and skipped from then on (see FEED_PAUSE_AFTER)."""
    res = RunResult()
    errors = []
    rules_by_country = {}
    paused = 0
    with http_client() as client:
        for o in _feed_outlets(s, youtube=False):
            ext = o.external or {}
            if ext.get("feed_paused"):
                paused += 1
                continue
            rules = rules_by_country.setdefault(o.country_id, load_rules(s, o.country_id))
            streak = ext.get("feed_failed_runs", 0)
            try:
                r = polite_get(client, o.rss_url, min_interval=0.5)
                r.raise_for_status()
                feed = feedparser.parse(r.content)
            except Exception as e:  # noqa: BLE001
                res.errors += 1
                streak += 1
                ext = {**ext, "feed_failed_runs": streak}
                if streak >= FEED_PAUSE_AFTER:
                    ext["feed_paused"] = {"since": datetime.now(timezone.utc).date().isoformat(), "failures": streak,
                                          "error": str(e)[:200]}
                    errors.append(f"{o.domain}: paused after {streak} failed runs in a row, last {e}")
                else:
                    errors.append(f"{o.domain}: {e} ({streak} in a row)")
                o.external = ext
                s.commit()
                continue
            if streak:
                o.external = {k: v for k, v in ext.items() if k != "feed_failed_runs"}
            res.rows += _store_entries(s, o, rules, feed, "rss")
    res.detail = "; ".join(errors)[:1000]
    if paused:
        res.detail = (f"{paused} paused feed{'s' if paused != 1 else ''} skipped" + ("; " + res.detail if res.detail else ""))[:1000]
    return res


def collect_youtube(s: Session) -> RunResult:
    """YouTube channel feeds (source_key 'youtube'). A failed run is only a note for a channel.
    After YOUTUBE_FAILED_RUNS failed runs in a row it counts as an error, and from then on the
    channel gets one try per run with no pauses, so an outage does not hold the job lock."""
    res = RunResult()
    errors = []
    rules_by_country = {}
    with http_client() as client:
        for o in _feed_outlets(s, youtube=True):
            rules = rules_by_country.setdefault(o.country_id, load_rules(s, o.country_id))
            streak = (o.external or {}).get("feed_failed_runs", 0)
            try:
                feed = _youtube_feed(client, o.rss_url, tries=1 if streak >= YOUTUBE_FAILED_RUNS else YOUTUBE_TRIES)
            except Exception as e:  # noqa: BLE001
                streak += 1
                o.external = {**(o.external or {}), "feed_failed_runs": streak}
                s.commit()
                if streak < YOUTUBE_FAILED_RUNS:
                    errors.append(f"{o.domain}: unavailable this run ({streak} in a row)")
                else:
                    res.errors += 1
                    errors.append(f"{o.domain}: {streak} failed runs in a row, last {e}")
                continue
            if streak:
                o.external = {k: v for k, v in o.external.items() if k != "feed_failed_runs"}
            res.rows += _store_entries(s, o, rules, feed, "youtube")
    res.detail = "; ".join(errors)[:1000]
    return res


def backfill(s: Session, *, since, max_pages: int = 2000) -> RunResult:
    """Walk WordPress-style `?paged=N` feed pages back to `since` for outlets whose feed supports
    paging (detected: page 2 differs from page 1). Feeds that ignore paging are skipped."""
    from datetime import datetime as _dt
    res = RunResult()
    notes = []
    with http_client() as client:
        for o in _feed_outlets(s, youtube=False):  # YouTube feeds have no paging
            rules = load_rules(s, o.country_id)
            try:
                p1 = feedparser.parse(polite_get(client, o.rss_url, min_interval=1.0).content)
                p2 = feedparser.parse(polite_get(client, o.rss_url, params={"paged": 2}, min_interval=1.0).content)
            except Exception as e:  # noqa: BLE001
                res.errors += 1
                notes.append(f"{o.domain}: {e}")
                continue
            links1 = {e.get("link") for e in p1.entries}
            if not p2.entries or {e.get("link") for e in p2.entries} <= links1:
                notes.append(f"{o.domain}: no paging")
                continue
            page, oldest = 1, None
            while page <= max_pages:
                feed = p1 if page == 1 else (p2 if page == 2 else feedparser.parse(
                    polite_get(client, o.rss_url, params={"paged": page}, min_interval=1.0).content))
                if not feed.entries:
                    break
                for e in feed.entries:
                    when = e.get("published_parsed") or e.get("updated_parsed")
                    if not when or not e.get("link"):
                        continue
                    pub = _dt.utcfromtimestamp(calendar.timegm(when))
                    oldest = pub if oldest is None or pub < oldest else oldest
                    snippet = _TAGS.sub(" ", e.get("summary", ""))[:600]
                    title = e.get("title", "")
                    _, created = store_article(
                        s, o.country_id, rules, url=e.link, title=title, snippet=snippet, published_at=pub,
                        source_key="rss", lang=detect_lang(title + " " + snippet), outlet_domain=o.domain,
                        outlet_name=o.name, require_theme=True, outlet_cache={o.domain: o})
                    res.rows += created
                s.commit()
                if oldest and oldest.date() < since:
                    break
                page += 1
            notes.append(f"{o.domain}: {page} pages back to {oldest.date() if oldest else '?'}")
    res.detail = "; ".join(notes)[:1000]
    return res
