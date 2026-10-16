"""Find the outlet's own link for Google News items.

Google News gives us a redirect link (news.google.com/rss/articles/...). Engagement services key
on the outlet's real URL, so we look it up and store it in item.extra['resolved_url']. item.url
never changes: the dedupe key depends on it.

Two routes, in order:
  copy       the same story from the same outlet through its feed, Google Alerts or the backfill
             (headline Jaccard >= MATCH_JACCARD, published within a day)
  wp_search  the outlet's WordPress search API, GET /wp-json/wp/v2/search?search=<first 6 words>.
             Whether a site has it is probed once and cached in outlet.external['wp_json'].
             Same headline test; the date comes from the URL or, only if needed, the post's self link.
We never use Google's undocumented batchexecute decoder. One request per second per site, and a
per-run cap on items."""
import logging
import re
from collections import defaultdict
from datetime import date, datetime, timedelta
from html import unescape
from itertools import zip_longest
from urllib.parse import urlsplit

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from .collectors.base import http_client, polite_get
from .engagement import SHORTENERS, is_google_link
from .fetch_meta import _check_public
from .models import Item, Outlet, utcnow
from .network import jaccard, title_tokens
from .textnorm import normalise

log = logging.getLogger("desert_watch.resolve")

MATCH_JACCARD = 0.8
MATCH_DAYS = 1
COPY_SOURCES = ("rss", "backfill", "galerts")
SEARCH_WORDS = 6
WP_PROBE_DAYS = 30        # re-check whether a site answers /wp-json after this long
MAX_TRIES = 2             # an item nobody could resolve is tried on two runs, then left alone
DEFAULT_LIMIT = 400

_HASHTAG_LABEL = re.compile(r"^\s*#\S+\s*[|:]\s*")    # "#ليبيا | headline" (libyaakhbar)
_URL_DATE = re.compile(r"/(20\d\d)/(\d\d)/(\d\d)/")
_PUNCT = re.compile(r"[^\w\s]+", re.UNICODE)


def clean_title(t: str | None) -> str:
    return _HASHTAG_LABEL.sub("", unescape(t or "")).strip()


# Daily recurring headlines ("exchange rates ... (Thursday 8 October)") differ only in a number
# or a weekday, which Jaccard barely sees. A title with a number or weekday the other lacks, while
# the other has one this lacks, is a different story. One side merely missing them (truncation) is fine.
_WEEKDAYS = {normalise(d).strip() for d in (
    "الأحد", "الاثنين", "الإثنين", "الأثنين", "الثلاثاء", "الأربعاء", "الخميس", "الجمعة", "السبت",
    "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")}
_DIGITS = re.compile(r"\d+")


def _markers(norm: str) -> tuple[set, set]:
    return set(_DIGITS.findall(norm)), {w for w in norm.split() if w in _WEEKDAYS}


def _conflict(x: set, y: set) -> bool:
    return bool(x - y) and bool(y - x)


def title_score(a: str | None, b: str | None) -> float:
    na, nb = normalise(clean_title(a)), normalise(clean_title(b))
    ta, tb = title_tokens(na), title_tokens(nb)
    if len(ta) < 3 or len(tb) < 3:
        return 0.0
    (da, wa), (db, wb) = _markers(na), _markers(nb)
    if _conflict(da, db) or _conflict(wa, wb):
        return 0.0
    return jaccard(ta, tb)


def search_terms(title: str) -> str:
    words = [w for w in _PUNCT.sub(" ", clean_title(title)).split() if len(w) > 1]
    return " ".join(words[:SEARCH_WORDS])


def url_date(url: str) -> date | None:
    m = _URL_DATE.search(urlsplit(url).path)
    if not m:
        return None
    try:
        return date(int(m[1]), int(m[2]), int(m[3]))
    except ValueError:
        return None


def same_site(url: str, domain: str) -> bool:
    host = urlsplit(url).netloc.lower().split(":")[0]
    return host == domain or host.endswith("." + domain)


def best_copy(item_title: str, published: datetime, pool: list) -> object | None:
    """pool: rows with .url, .title, .published_at. The closest headline within the time window."""
    best, best_score = None, MATCH_JACCARD
    for r in pool:
        if abs((r.published_at - published).total_seconds()) > MATCH_DAYS * 86400:
            continue
        sc = title_score(item_title, r.title)
        if sc >= best_score:
            best, best_score = r, sc
    return best


def _public_only(request: httpx.Request):
    _check_public(str(request.url))   # outlet domains come from feeds: never follow one to a private address


def resolver_client() -> httpx.Client:
    c = http_client(timeout=20)
    c.event_hooks["request"] = [_public_only]
    return c


def wp_available(client: httpx.Client, o: Outlet, today: date) -> bool:
    """Cached probe of the outlet's WordPress search API (outlet.external['wp_json'])."""
    cached = (o.external or {}).get("wp_json") or {}
    if cached.get("checked") and (today - date.fromisoformat(cached["checked"])).days < WP_PROBE_DAYS:
        return bool(cached.get("ok"))
    try:
        r = polite_get(client, f"https://{o.domain}/wp-json/wp/v2/search", params={"search": "news", "per_page": 1},
                       min_interval=1.0, retries=0)
    except Exception as e:  # noqa: BLE001 - unreachable now: try again next run, cache nothing
        log.info("wp probe %s: %s", o.domain, e)
        return False
    try:
        ok = r.status_code == 200 and isinstance(r.json(), list)
    except ValueError:
        ok = False
    o.external = {**(o.external or {}), "wp_json": {"ok": ok, "checked": today.isoformat()}}
    return ok


def _post_date(client: httpx.Client, hit: dict, domain: str) -> datetime | None:
    href = ((hit.get("_links") or {}).get("self") or [{}])[0].get("href")
    if not href or not same_site(href, domain):
        return None
    r = polite_get(client, href, params={"_fields": "date_gmt,date"}, min_interval=1.0, retries=1)
    if r.status_code != 200:
        return None
    d = r.json()
    raw = d.get("date_gmt") or d.get("date")
    try:
        return datetime.fromisoformat(raw[:19]) if raw else None
    except ValueError:
        return None


def wp_match(client: httpx.Client, o: Outlet, title: str, published: datetime) -> str | None:
    """Search the outlet's site for the headline. Returns the post URL or None."""
    terms = search_terms(title)
    if not terms:
        return None
    r = polite_get(client, f"https://{o.domain}/wp-json/wp/v2/search",
                   params={"search": terms, "per_page": 5}, min_interval=1.0, retries=1)
    if r.status_code != 200:
        return None
    try:
        hits = r.json()
    except ValueError:
        return None
    if not isinstance(hits, list):
        return None
    scored = sorted(((title_score(title, h.get("title")), h) for h in hits
                     if isinstance(h, dict) and h.get("url") and same_site(h["url"], o.domain)),
                    key=lambda x: -x[0])
    for sc, h in scored:
        if sc < MATCH_JACCARD:
            break
        d = url_date(h["url"])
        if d is not None:
            if abs((d - published.date()).days) <= MATCH_DAYS:
                return h["url"]
            continue
        when = _post_date(client, h, o.domain)
        if when and abs((when - published).total_seconds()) <= MATCH_DAYS * 86400:
            return h["url"]
    return None


def candidates(s: Session, *, days: int, now: datetime) -> list[Item]:
    """Counted Google News items from the last `days` days that still need an outlet link."""
    rows = s.scalars(select(Item).where(
        Item.kind == "article", Item.relevant.is_(True), Item.duplicate_of.is_(None), Item.outlet_id.is_not(None),
        Item.url.like("%news.google.com/%"), Item.published_at >= now - timedelta(days=days))
        .order_by(Item.published_at.desc())).all()
    return [r for r in rows if is_google_link(r.url) and not (r.extra or {}).get("resolved_url")
            and (r.extra or {}).get("resolve_tries", 0) < MAX_TRIES]


def _resolvable(o: Outlet) -> bool:
    """Social pages, link shorteners and Google itself have no article site to search."""
    return "/" not in o.domain and o.domain not in SHORTENERS and not o.domain.endswith("google.com")


def _interleave(items: list[Item]) -> list[Item]:
    """Newest first within each outlet, one outlet after another (busiest outlets first in each round),
    so the per-site pause rarely blocks."""
    by_outlet = defaultdict(list)
    for it in items:
        by_outlet[it.outlet_id].append(it)
    groups = sorted(by_outlet.values(), key=len, reverse=True)
    return [it for group in zip_longest(*groups) for it in group if it is not None]


def run(s: Session, *, days: int = 14, limit: int = DEFAULT_LIMIT, client: httpx.Client | None = None,
        now: datetime | None = None) -> dict:
    now = now or utcnow()
    cands = candidates(s, days=days, now=now)
    outlets = {o.id: o for o in s.scalars(select(Outlet).where(Outlet.id.in_({it.outlet_id for it in cands})))}
    usable = [it for it in cands if it.outlet_id in outlets and _resolvable(outlets[it.outlet_id])]
    todo = _interleave(usable)[:limit]
    stats = {"items": len(todo), "copy": 0, "wp_search": 0, "unresolved": 0,
             "skipped_outlets": len(cands) - len(usable), "by_outlet": {}}

    # route 1: a copy from the outlet's own feed, Google Alerts or the backfill
    pools = defaultdict(list)
    by_outlet = defaultdict(list)
    for it in todo:
        by_outlet[it.outlet_id].append(it)
    for oid, its in by_outlet.items():
        lo = min(i.published_at for i in its) - timedelta(days=MATCH_DAYS)
        hi = max(i.published_at for i in its) + timedelta(days=MATCH_DAYS)
        pools[oid] = s.execute(select(Item.id, Item.url, Item.title, Item.published_at).where(
            Item.outlet_id == oid, Item.kind == "article", Item.source_key.in_(COPY_SOURCES),
            Item.published_at >= lo, Item.published_at <= hi, Item.url.not_like("%news.google.com/%"))).all()

    own = client is None
    client = client or resolver_client()
    try:
        for it in todo:
            o = outlets[it.outlet_id]
            tally = stats["by_outlet"].setdefault(o.domain, {"items": 0, "resolved": 0})
            tally["items"] += 1
            url, via = None, None
            hit = best_copy(it.title, it.published_at, pools[o.id])
            if hit is not None:
                url, via = hit.url, "copy"
            else:
                try:
                    if wp_available(client, o, now.date()):
                        url = wp_match(client, o, it.title, it.published_at)
                        via = "wp_search" if url else None
                except Exception as e:  # noqa: BLE001 - one bad site never stops the run
                    log.info("resolve %s via %s: %s", it.id, o.domain, e)
            if url:
                it.extra = {**(it.extra or {}), "resolved_url": url, "resolved_via": via,
                            "resolved_at": now.isoformat(timespec="seconds")}
                stats[via] += 1
                tally["resolved"] += 1
            else:
                it.extra = {**(it.extra or {}), "resolve_tries": (it.extra or {}).get("resolve_tries", 0) + 1}
                stats["unresolved"] += 1
            s.commit()
    finally:
        if own:
            client.close()
    return stats


def collect(s: Session, *, days: int = 14, limit: int = DEFAULT_LIMIT, **kw) -> "RunResult":
    """run() as a recorded job (source_run 'resolve', shown in the source-health strip)."""
    from .collectors.base import RunResult
    st = run(s, days=days, limit=limit, **kw)
    return RunResult(rows=st["copy"] + st["wp_search"],
                     detail=f"{st['items']} tried: {st['copy']} from a copy, {st['wp_search']} by site search, "
                            f"{st['unresolved']} not found")
