"""Outlet RSS feeds (Arabic + English), and YouTube channel feeds. Only items matching at least one
theme are kept."""
import calendar
import time
from datetime import datetime

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


def _youtube_feed(client, url: str):
    """YouTube channel feeds answer 404 or 500 to about half of all requests (2026-10-16) and then
    work on the next try, so we try three times with a pause."""
    for attempt in range(YOUTUBE_TRIES):
        try:
            r = polite_get(client, url, min_interval=1.0, retries=0)
            r.raise_for_status()
            return feedparser.parse(r.content)
        except Exception:  # noqa: BLE001
            if attempt == YOUTUBE_TRIES - 1:
                raise
            time.sleep(YOUTUBE_BACKOFF * 2 ** attempt)


def collect(s: Session) -> RunResult:
    res = RunResult()
    errors = []
    with http_client() as client:
        outlets = s.scalars(select(Outlet).where(Outlet.rss_url.is_not(None), Outlet.active.is_(True))).all()
        rules_by_country = {}
        for o in outlets:
            rules = rules_by_country.setdefault(o.country_id, load_rules(s, o.country_id))
            youtube = YOUTUBE_FEED in o.rss_url
            try:
                if youtube:
                    feed = _youtube_feed(client, o.rss_url)
                else:
                    r = polite_get(client, o.rss_url, min_interval=0.5)
                    r.raise_for_status()
                    feed = feedparser.parse(r.content)
            except Exception as e:  # noqa: BLE001
                if youtube:  # one bad run is normal for YouTube: only a streak counts as an error
                    streak = (o.external or {}).get("feed_failed_runs", 0) + 1
                    o.external = {**(o.external or {}), "feed_failed_runs": streak}
                    s.commit()
                    if streak < YOUTUBE_FAILED_RUNS:
                        errors.append(f"{o.domain}: unavailable this run ({streak} in a row)")
                        continue
                res.errors += 1
                errors.append(f"{o.domain}: {e}")
                continue
            if youtube and (o.external or {}).get("feed_failed_runs"):
                o.external = {k: v for k, v in o.external.items() if k != "feed_failed_runs"}
            for e in feed.entries:
                when = e.get("published_parsed") or e.get("updated_parsed")
                if not when or not e.get("link"):
                    continue
                snippet = _TAGS.sub(" ", e.get("summary", ""))[:600]
                title = e.get("title", "")
                item, created = store_article(
                    s, o.country_id, rules, url=e.link, title=title, snippet=snippet,
                    published_at=datetime.utcfromtimestamp(calendar.timegm(when)),
                    source_key="youtube" if youtube else "rss",
                    lang=detect_lang(title + " " + snippet), outlet_domain=o.domain, outlet_name=o.name,
                    require_theme=True, outlet_cache={o.domain: o})
                res.rows += created
            s.commit()
    res.detail = "; ".join(errors)[:1000]
    return res


def backfill(s: Session, *, since, max_pages: int = 2000) -> RunResult:
    """Walk WordPress-style `?paged=N` feed pages back to `since` for outlets whose feed supports
    paging (detected: page 2 differs from page 1). Feeds that ignore paging are skipped."""
    from datetime import datetime as _dt
    res = RunResult()
    notes = []
    with http_client() as client:
        outlets = s.scalars(select(Outlet).where(Outlet.rss_url.is_not(None), Outlet.active.is_(True),
                                                 Outlet.rss_url.not_like(f"%{YOUTUBE_FEED}%"))).all()  # no paging
        for o in outlets:
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
