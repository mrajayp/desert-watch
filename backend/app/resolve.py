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
We never use Google's undocumented batchexecute decoder. One request per second per site, a cap on
site searches, on new sites probed and on minutes per run. A site that answers with an error page
(429, 403, 5xx, a challenge page) is a site problem: its items keep their tries, and a site that
says "slow down" (429) is left alone for the rest of the run.

item.extra is written one key at a time in SQL (json_set). A run lasts minutes and the API writes
the same column (a user's relevance decision), so writing back the copy loaded at the start of the
run would wipe it."""
import logging
import re
import time
from collections import defaultdict
from datetime import date, datetime, timedelta
from html import unescape
from itertools import zip_longest
from urllib.parse import urlsplit

import httpx
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from .collectors.base import http_client, polite_get
from .engagement import SHORTENERS, is_google_link, set_external
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
DEFAULT_LIMIT = 400       # site searches per run (copies are free and always checked)
PROBES_PER_RUN = 60       # unknown sites asked about /wp-json per run, busiest first
SITE_ERRORS = 3           # failed searches before a site is left alone for the rest of the run
DEFAULT_MINUTES = 15      # the nightly job holds the shared job lock: stop asking sites after this long

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


class SiteRefused(Exception):
    """The site answered, but with an error or a challenge page instead of results. A site problem,
    never "not found". throttled: it asked us to slow down."""

    def __init__(self, msg: str, *, throttled: bool = False):
        super().__init__(msg)
        self.throttled = throttled


def _throttled(r: httpx.Response) -> bool:
    return r.status_code == 429 or "Please limit requests" in r.text[:200]


def _challenge(r: httpx.Response) -> bool:
    # Cloudflare marks its challenge pages. Its ordinary pages also load /cdn-cgi/challenge-platform/
    # scripts, so the page text alone is not a sign.
    return r.headers.get("cf-mitigated") == "challenge" or "<title>Just a moment" in r.text[:2000]


def _json(r: httpx.Response):
    try:
        return r.json()
    except ValueError:
        return None


def _check_reply(r: httpx.Response) -> None:
    """Raises SiteRefused for 429, 403, 5xx and challenge pages."""
    if _throttled(r):
        raise SiteRefused(f"asked to slow down (HTTP {r.status_code})", throttled=True)
    if r.status_code == 403 or r.status_code >= 500 or _challenge(r):
        raise SiteRefused(f"error page (HTTP {r.status_code})")


def _public_only(request: httpx.Request):
    _check_public(str(request.url))   # outlet domains come from feeds: never follow one to a private address


def resolver_client() -> httpx.Client:
    c = http_client(timeout=10)
    c.event_hooks["request"] = [_public_only]
    return c


def site_base(o: Outlet) -> str:
    """Where to send searches: the host the probe was redirected to (www.), else the outlet domain."""
    return ((o.external or {}).get("wp_json") or {}).get("base") or f"https://{o.domain}"


def wp_cached(o: Outlet, today: date) -> bool | None:
    """The outlet's cached /wp-json answer (outlet.external['wp_json']), or None when unknown or stale."""
    cached = (o.external or {}).get("wp_json") or {}
    if cached.get("checked") and (today - date.fromisoformat(cached["checked"])).days < WP_PROBE_DAYS:
        return bool(cached.get("ok"))
    return None


def probe_wp(client: httpx.Client, o: Outlet, today: date) -> bool:
    """Asks the site once whether it answers the WordPress search API and caches the answer. Only a
    clear answer is cached: a 200, a 404 or 410, or WordPress itself refusing (a rest_ error code).
    Anything else (429, 403 from a firewall, 5xx, a challenge page, no answer) raises: nothing is
    cached, and run() tries the site again next run."""
    r = polite_get(client, f"https://{o.domain}/wp-json/wp/v2/search", params={"search": "news", "per_page": 1},
                   min_interval=1.0, retries=0)
    body = _json(r)
    wp_refusal = isinstance(body, dict) and str(body.get("code", "")).startswith("rest_")
    if (r.status_code in (401, 403) and wp_refusal) or r.status_code in (404, 410):
        ok = False
    else:
        _check_reply(r)
        if r.status_code != 200:
            raise SiteRefused(f"unclear answer (HTTP {r.status_code})")
        ok = isinstance(body, list)
    entry = {"ok": ok, "checked": today.isoformat()}
    if ok and r.url.host != o.domain and same_site(str(r.url), o.domain):
        entry["base"] = f"{r.url.scheme}://{r.url.host}"     # search there at once, without a redirect each time
    set_external(o, "wp_json", entry)
    return ok


def _post_date(client: httpx.Client, hit: dict, domain: str) -> datetime | None:
    href = ((hit.get("_links") or {}).get("self") or [{}])[0].get("href")
    if not href or not same_site(href, domain):
        return None
    r = polite_get(client, href, params={"_fields": "date_gmt,date"}, min_interval=1.0, retries=1)
    _check_reply(r)
    if r.status_code != 200:
        return None
    d = _json(r)
    if not isinstance(d, dict):
        raise SiteRefused("post date: not a WordPress reply")
    raw = d.get("date_gmt") or d.get("date")
    try:
        return datetime.fromisoformat(raw[:19]) if raw else None
    except ValueError:
        return None


def wp_match(client: httpx.Client, o: Outlet, title: str, published: datetime) -> str | None:
    """Search the outlet's site for the headline. Returns the post URL or None (not found). Raises
    SiteRefused when the site answers with anything but a list of search results."""
    terms = search_terms(title)
    if not terms:
        return None
    r = polite_get(client, f"{site_base(o)}/wp-json/wp/v2/search",
                   params={"search": terms, "per_page": 5}, min_interval=1.0, retries=1)
    _check_reply(r)
    hits = _json(r) if r.status_code == 200 else None
    if not isinstance(hits, list):
        raise SiteRefused(f"no search results (HTTP {r.status_code})")
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


# item.extra as a JSON object, whatever is stored (NULL or JSON null become {})
_EXTRA = "CASE json_type(extra) WHEN 'object' THEN extra ELSE '{}' END"
_SET_RESOLVED = text(f"UPDATE item SET extra = json_set({_EXTRA}, '$.resolved_url', :url, '$.resolved_via', :via, "
                     f"'$.resolved_at', :at) WHERE id = :id")
_ADD_TRY = text(f"UPDATE item SET extra = json_set({_EXTRA}, '$.resolve_tries', "
                f"COALESCE(json_extract({_EXTRA}, '$.resolve_tries'), 0) + 1) WHERE id = :id")


def run(s: Session, *, days: int = 14, limit: int = DEFAULT_LIMIT, probes: int = PROBES_PER_RUN,
        minutes: float = DEFAULT_MINUTES, client: httpx.Client | None = None, now: datetime | None = None) -> dict:
    """1. copies (free, every candidate). 2. probe up to `probes` unknown sites, busiest first.
    3. site search for up to `limit` items of outlets whose site answers, round-robin across sites.
    `limit` counts searches. A search can bring a few more requests (a post's date), and probes come
    on top. After `minutes` no more requests are sent.
    Items of sites without the API get one try per run (the copy check). Items of sites not probed
    yet, sites that did not answer, or beyond the limit are left untouched for a later run."""
    now = now or utcnow()
    today = now.date()
    deadline = time.monotonic() + minutes * 60
    cands = candidates(s, days=days, now=now)
    outlets = {o.id: o for o in s.scalars(select(Outlet).where(Outlet.id.in_({it.outlet_id for it in cands})))}
    usable = [it for it in cands if it.outlet_id in outlets and _resolvable(outlets[it.outlet_id])]
    stats = {"candidates": len(usable), "copy": 0, "searched": 0, "wp_search": 0, "not_found": 0,
             "no_site_search": 0, "probed": 0, "site_down": 0, "skipped_outlets": len(cands) - len(usable),
             "out_of_time": False, "by_outlet": {}}

    def out_of_time() -> bool:
        stats["out_of_time"] = stats["out_of_time"] or time.monotonic() >= deadline
        return stats["out_of_time"]

    def done(it, url, via):
        if url:
            s.execute(_SET_RESOLVED, {"url": url, "via": via, "at": now.isoformat(timespec="seconds"), "id": it.id})
            stats[via] += 1
        else:
            s.execute(_ADD_TRY, {"id": it.id})
        s.expire(it, ["extra"])
        row = stats["by_outlet"].setdefault(outlets[it.outlet_id].domain, {"items": 0, "resolved": 0})
        row["items"] += 1
        row["resolved"] += bool(url)

    # 1. a copy from the outlet's own feed, Google Alerts or the backfill
    by_outlet = defaultdict(list)
    for it in usable:
        by_outlet[it.outlet_id].append(it)
    pending = defaultdict(list)
    for oid, its in by_outlet.items():
        lo = min(i.published_at for i in its) - timedelta(days=MATCH_DAYS)
        hi = max(i.published_at for i in its) + timedelta(days=MATCH_DAYS)
        pool = s.execute(select(Item.id, Item.url, Item.title, Item.published_at).where(
            Item.outlet_id == oid, Item.kind == "article", Item.source_key.in_(COPY_SOURCES),
            Item.published_at >= lo, Item.published_at <= hi, Item.url.not_like("%news.google.com/%"))).all()
        for it in its:
            hit = best_copy(it.title, it.published_at, pool)
            if hit is not None:
                done(it, hit.url, "copy")
            else:
                pending[oid].append(it)
    s.commit()

    own = client is None
    client = client or resolver_client()
    try:
        # 2. which sites answer the WordPress search API (cached for WP_PROBE_DAYS)
        down: set[int] = set()   # sites that failed to answer this run: not asked again until the next run
        unknown = sorted((oid for oid in pending if wp_cached(outlets[oid], today) is None),
                         key=lambda oid: -len(pending[oid]))
        for oid in unknown[:probes]:
            if out_of_time():
                break
            try:
                probe_wp(client, outlets[oid], today)
                stats["probed"] += 1
            except Exception as e:  # noqa: BLE001 - one bad site never stops the run
                log.info("wp probe %s: %s", outlets[oid].domain, e)
                down.add(oid)
                stats["site_down"] += 1
            s.commit()
        searchable = []
        for oid, its in pending.items():
            ok = wp_cached(outlets[oid], today)
            if ok is False:
                for it in its:       # no site search: the copy check above was this run's try
                    done(it, None, None)
                    stats["no_site_search"] += 1
            elif ok and oid not in down:
                searchable += its
        s.commit()

        # 3. site search, round-robin across sites
        errors = defaultdict(int)
        for it in _interleave(searchable)[:limit]:
            o = outlets[it.outlet_id]
            if o.id in down:
                continue
            if out_of_time():
                break
            try:
                url = wp_match(client, o, it.title, it.published_at)
            except Exception as e:  # noqa: BLE001 - the item is left for a later run, not counted as a try
                log.info("resolve %s via %s: %s", it.id, o.domain, e)
                errors[o.id] += SITE_ERRORS if getattr(e, "throttled", False) else 1   # 429: leave the site alone
                if errors[o.id] >= SITE_ERRORS:
                    down.add(o.id)
                    stats["site_down"] += 1
                continue
            stats["searched"] += 1
            stats["not_found"] += not url
            done(it, url, "wp_search")
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
                     detail=f"{st['candidates']} Google News links: {st['copy']} found from a copy, "
                            f"{st['wp_search']} of {st['searched']} by site search, {st['probed']} sites checked, "
                            f"{st['site_down']} sites not answering"
                            + (". Stopped at the time limit, the rest waits for the next run" if st["out_of_time"] else ""))
