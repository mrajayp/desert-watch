"""Feed discovery (plan C-R2.3): the nightly search for the feeds of outlets that have none.

Only 46 of the register's outlets have a feed, so most coverage arrives through Google News, which
caps, samples and favours recent weeks. Every night, NIGHTLY outlets among the active ones (a counted
article in the last year, a website rather than a social account, no feed yet, not searched in the last
RECHECK_DAYS days), busiest first, get one homepage fetch and a few polite probes:

  1. <link rel="alternate" type="application/rss+xml|atom+xml"> on the homepage
  2. /feed/, /rss, /rss.xml, /feed.xml, /ar/feed/
  3. /wp-json/wp/v2/posts?per_page=1: a WordPress site answers with a post; its feed is then /?feed=rss2

A candidate is accepted only when feedparser reads it without complaint (bozo 0), it has entries with
links, and its newest entry is at most FRESH_DAYS old. The address goes into Outlet.rss_url with
external.feed = {found_at, how, url}; the hourly RSS collector then reads it. What the homepage says
about where the outlet is from (<html lang>, og:locale, mentions of the country) is kept as a scope
SUGGESTION only (register.store_suggestion), for the Contribute review queue.

Feeds that keep failing: collectors/rss.py counts a feed's failed runs in a row and pauses it after
FEED_PAUSE_AFTER (external.feed_paused); a paused feed is tried again here after PAUSE_RETRY_DAYS and
unpaused when it reads cleanly. GET /api/admin/feeds lists paused and discovered feeds.

Polite: the desert-watch user agent, one request at a time, MIN_INTERVAL seconds between requests
whatever the host, at most MAX_BYTES read per response, nothing retried."""
import calendar
import re
import time
from datetime import date, datetime, timedelta, timezone
from urllib.parse import urljoin, urlsplit

import feedparser
import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import register
from ..models import Country, Outlet
from .base import RunResult, http_client

NIGHTLY = 50
PATHS = ("/feed/", "/rss", "/rss.xml", "/feed.xml", "/ar/feed/")
WP_PROBE = "/wp-json/wp/v2/posts?per_page=1"
WP_FEED = "/?feed=rss2"
MAX_BYTES = 2 * 1024 * 1024
FRESH_DAYS = 60
RECHECK_DAYS = 60        # an outlet searched without result is searched again after this
PAUSE_RETRY_DAYS = 14    # a paused feed gets one try again after this
PAUSED_PER_NIGHT = 10
MIN_INTERVAL = 2.0
TIMEOUT = 20.0
FEED_TYPES = ("application/rss+xml", "application/atom+xml", "application/rdf+xml", "text/xml", "application/xml")

_LINK = re.compile(r"<link\b[^>]*>", re.I)
_ATTR = re.compile(r"([\w:-]+)\s*=\s*(?:\"([^\"]*)\"|'([^']*)'|([^\s\"'>]+))")


class TooBig(Exception):
    """The response went past MAX_BYTES."""


def _attrs(tag: str) -> dict:
    # findall gives '' for the quoting styles that did not match, so the first non-empty value is the one
    return {k.lower(): (a or b or c) for k, a, b, c in _ATTR.findall(tag)}


def feed_links(html: str, base: str) -> list[str]:
    """Feed addresses the page advertises: <link rel="alternate" type="application/rss+xml" href=...>,
    in page order, resolved against the page, without repeats."""
    out, seen = [], set()
    for tag in _LINK.findall(html[:300_000]):
        a = _attrs(tag)
        rel = (a.get("rel") or "").lower().split()
        typ = (a.get("type") or "").lower().split(";")[0].strip()
        href = a.get("href")
        if "alternate" in rel and typ in FEED_TYPES and href:
            url = urljoin(base, href.strip())
            if url.startswith(("http://", "https://")) and url not in seen:
                seen.add(url)
                out.append(url)
    return out


def check_feed(content: bytes, today: date | None = None) -> tuple[bool, str]:
    """(accepted, why): feedparser must read it without complaint, with entries that have links, and
    the newest entry must be at most FRESH_DAYS old."""
    parsed = feedparser.parse(content)
    if parsed.bozo:
        return False, f"not clean: {getattr(parsed, 'bozo_exception', 'parse error')}"[:120]
    entries = [e for e in parsed.entries if e.get("link")]
    if not entries:
        return False, "no entries"
    dates = [e.get("published_parsed") or e.get("updated_parsed") for e in entries]
    dates = [d for d in dates if d]
    if not dates:
        return False, "entries carry no date"
    newest = max(datetime.fromtimestamp(calendar.timegm(d), timezone.utc).date() for d in dates)
    if newest < (today or date.today()) - timedelta(days=FRESH_DAYS):
        return False, f"newest entry {newest.isoformat()}"
    return True, f"{len(entries)} entries, newest {newest.isoformat()}"


class Fetcher:
    """One request at a time, MIN_INTERVAL between any two, at most MAX_BYTES per answer."""

    def __init__(self, client: httpx.Client, min_interval: float = MIN_INTERVAL):
        self.client, self.min_interval, self.last, self.requests = client, min_interval, 0.0, 0

    def get(self, url: str) -> tuple[int, str, bytes]:
        wait = self.last + self.min_interval - time.monotonic()
        if wait > 0:
            time.sleep(wait)
        self.requests += 1
        try:
            with self.client.stream("GET", url) as r:
                body = bytearray()
                for chunk in r.iter_bytes():
                    body += chunk
                    if len(body) > MAX_BYTES:
                        raise TooBig(url)
                return r.status_code, str(r.url), bytes(body)
        finally:
            self.last = time.monotonic()


def _ok(status: int) -> bool:
    return 200 <= status < 300


def search_outlet(f: Fetcher, o: Outlet, country: Country, today: date) -> tuple[str | None, str | None, list[str]]:
    """Try the homepage and the probes for one outlet. Returns (feed url, how, notes). Keeps the homepage's
    scope signals on the outlet as a suggestion (never a label)."""
    notes = []
    home = f"https://{o.domain}/"
    try:
        status, final, body = f.get(home)
    except Exception as e:  # noqa: BLE001 - one outlet's homepage down is a note, not a run error
        return None, None, [f"homepage: {type(e).__name__}"]
    if not _ok(status):
        return None, None, [f"homepage: HTTP {status}"]
    html = body.decode("utf-8", "replace")
    register.store_suggestion(o, html, final, country, today)
    base = final if final.startswith("http") else home
    origin = f"{urlsplit(base).scheme}://{urlsplit(base).netloc}"
    candidates = [(u, "link_rel") for u in feed_links(html, base)]
    candidates += [(origin + p, p) for p in PATHS]
    tried = set()
    for url, how in candidates:
        if url in tried:
            continue
        tried.add(url)
        try:
            status, _final, content = f.get(url)
        except Exception as e:  # noqa: BLE001
            notes.append(f"{how}: {type(e).__name__}")
            continue
        if not _ok(status):
            notes.append(f"{how}: HTTP {status}")
            continue
        ok, why = check_feed(content, today)
        notes.append(f"{how}: {why}")
        if ok:
            return url, how, notes
    # a WordPress site answers its API with a post; its feed is then the query form, which survives
    # a blocked /feed/ path
    try:
        status, _final, content = f.get(origin + WP_PROBE)
        if _ok(status) and content.lstrip().startswith(b"[") and b'"id"' in content[:2000]:
            url = origin + WP_FEED
            status, _final, content = f.get(url)
            if _ok(status):
                ok, why = check_feed(content, today)
                notes.append(f"wp-json: {why}")
                if ok:
                    return url, "wp-json", notes
            else:
                notes.append(f"wp-json: feed HTTP {status}")
        else:
            notes.append("wp-json: no")
    except Exception as e:  # noqa: BLE001
        notes.append(f"wp-json: {type(e).__name__}")
    return None, None, notes


def candidates(s: Session, country: Country, limit: int, today: date) -> list[Outlet]:
    """Active website outlets of the country with a counted article in the last year, no feed, not a
    social account or shortener, not searched in the last RECHECK_DAYS days; busiest first."""
    volume = register.counted_articles(s, country.id, register.DORMANT_DAYS)
    vanity = register.vanity_domains(country.config)
    cutoff = (today - timedelta(days=RECHECK_DAYS)).isoformat()
    out = []
    for o in s.scalars(select(Outlet).where(Outlet.active.is_(True), Outlet.country_id == country.id,
                                            Outlet.rss_url.is_(None))):
        if o.id not in volume or not register.is_site(o.domain) or o.domain.lower() in vanity or o.monitored is False:
            continue
        last = ((o.external or {}).get("feed_search") or {}).get("at")
        if last and last >= cutoff:
            continue
        out.append(o)
    out.sort(key=lambda o: (-volume.get(o.id, 0), o.id))
    return out[:limit]


def paused_feeds(s: Session, country: Country | None = None) -> list[Outlet]:
    q = select(Outlet).where(Outlet.active.is_(True), Outlet.rss_url.is_not(None))
    if country is not None:
        q = q.where(Outlet.country_id == country.id)
    return [o for o in s.scalars(q) if (o.external or {}).get("feed_paused")]


def discover(s: Session, *, limit: int = NIGHTLY, client: httpx.Client | None = None, today: date | None = None,
             min_interval: float = MIN_INTERVAL) -> RunResult:
    """The nightly search (jobs.discover_feeds, CLI discover-feeds). rows = feeds found. Also gives paused
    feeds older than PAUSE_RETRY_DAYS one try again (at most PAUSED_PER_NIGHT)."""
    res = RunResult()
    today = today or date.today()
    searched = found = retried = unpaused = 0
    notes = []
    own = client is None
    client = client or http_client(timeout=TIMEOUT)
    f = Fetcher(client, min_interval)
    try:
        for country in s.scalars(select(Country)).all():
            for o in candidates(s, country, limit, today):
                searched += 1
                url, how, why = search_outlet(f, o, country, today)
                ext = {k: v for k, v in (o.external or {}).items() if k != "feed_search"}
                ext["feed_search"] = {"at": today.isoformat(), "result": "found" if url else "none", "tried": len(why)}
                if url:
                    o.rss_url = url
                    ext["feed"] = {"found_at": today.isoformat(), "how": how, "url": url}
                    found += 1
                    notes.append(f"{o.domain}: {how}")
                o.external = ext
                s.commit()   # one outlet at a time: the write lock is never held across a request
            cutoff = (today - timedelta(days=PAUSE_RETRY_DAYS)).isoformat()
            for o in paused_feeds(s, country):
                if retried >= PAUSED_PER_NIGHT or (o.external["feed_paused"].get("since") or "") > cutoff:
                    continue
                retried += 1
                try:
                    status, _final, content = f.get(o.rss_url)
                    ok, why = check_feed(content, today) if _ok(status) else (False, f"HTTP {status}")
                except Exception as e:  # noqa: BLE001
                    ok, why = False, type(e).__name__
                ext = dict(o.external or {})
                if ok:
                    ext.pop("feed_paused", None)
                    ext.pop("feed_failed_runs", None)
                    unpaused += 1
                    notes.append(f"{o.domain}: unpaused")
                else:
                    ext["feed_paused"] = {**ext["feed_paused"], "retried_at": today.isoformat(), "error": why[:200]}
                o.external = ext
                s.commit()
    finally:
        if own:
            client.close()
    res.rows = found
    head = f"{searched} outlets searched, {found} feeds found, {f.requests} requests"
    if retried:
        head += f"; {retried} paused feeds tried again, {unpaused} unpaused"
    res.detail = (head + ("; " + "; ".join(notes) if notes else ""))[:1000]
    return res


def admin_list(s: Session) -> dict:
    """GET /api/admin/feeds: feeds on record, the paused ones, the discovered ones and the search so far."""
    with_feed = s.scalars(select(Outlet).where(Outlet.active.is_(True), Outlet.rss_url.is_not(None))).all()
    paused, discovered = [], []
    for o in with_feed:
        ext = o.external or {}
        if ext.get("feed_paused"):
            p = ext["feed_paused"]
            paused.append({"id": o.id, "name": o.name, "domain": o.domain, "rss_url": o.rss_url,
                           "since": p.get("since"), "failures": p.get("failures"), "error": p.get("error"),
                           "retried_at": p.get("retried_at")})
        if ext.get("feed"):
            discovered.append({"id": o.id, "name": o.name, "domain": o.domain, "rss_url": o.rss_url,
                               "found_at": ext["feed"].get("found_at"), "how": ext["feed"].get("how")})
    discovered.sort(key=lambda d: (d["found_at"] or "", d["id"]), reverse=True)
    searched = [o for o in s.scalars(select(Outlet).where(Outlet.active.is_(True)))
                if ((o.external or {}).get("feed_search") or {}).get("at")]
    last = max((o.external["feed_search"]["at"] for o in searched), default=None)
    left = sum(len(candidates(s, c, 10_000, date.today())) for c in s.scalars(select(Country)))
    return {"with_feed": len(with_feed), "paused": paused, "discovered": discovered[:200],
            "searched": {"outlets": len(searched), "last": last, "found": len(discovered)},
            "candidates_left": left, "nightly": NIGHTLY}
