"""Facebook link engagement for our articles (Graph API URL node).

GET https://graph.facebook.com/v26.0/?ids=<up to 50 URLs>&fields=engagement with the app token
"<app id>|<app secret>" in the Authorization header (never in the URL, which httpx logs) gives
engagement{reaction_count, comment_count, share_count} per URL. Facebook says the values are
"intentionally not precise". It needs a Meta app: until DW_FB_APP_ID and DW_FB_APP_SECRET are both
set, each run is recorded as awaiting key.

Counted articles from monitored outlets that have their own URL (direct, or resolved from a Google
News link) are read twice, at about 48 hours and at about 7 days, into item_engagement
(source 'fb_url', age bucket '48h' / '7d'). At most settings.FB_DAILY_URLS URLs in any 24 hours.
Rate-limit errors (codes 4, 17, 32), a transient Facebook error or a usage header near its cap stop
the run: the next scheduled run (6 hours later) carries on. A URL Facebook returns nothing for is
asked once more on a later run before its empty reading stands."""
import json
import logging
from datetime import datetime, timedelta
from urllib.parse import unquote, urlsplit

import httpx
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import settings
from ..engagement import SHORTENERS, outlet_url, upsert_readings
from ..models import Item, ItemEngagement, Outlet, utcnow
from .base import AwaitingKey, RunResult, http_client, polite_get

log = logging.getLogger("desert_watch.collectors.fb")

GRAPH = "https://graph.facebook.com/v26.0/"
BATCH = 50
# age windows per reading; 7 days is the one we trust most, so it goes first when the budget is short
BUCKETS = {"7d": (timedelta(days=7) - timedelta(hours=4), timedelta(days=10)),
           "48h": (timedelta(hours=44), timedelta(hours=96))}
SKIP_DOMAINS = {"lana.gov.ly"}   # no Facebook posts linking it in 2023-24: not worth the quota
RATE_LIMIT_CODES = {4, 17, 32}
USAGE_STOP = 75                  # percent of any X-App-Usage figure
MISSING_TRIES = 2                # lookups for a URL Facebook returned nothing for, then the empty reading stands
TOKEN_CODES = {102, 104, 190}    # no token, or a token Facebook does not accept


class _Stop(Exception):
    pass


def due(s: Session, now: datetime) -> list[tuple[Item, str, str, int]]:
    """(item, url, age bucket, lookups so far) still to read, 7-day readings first, newest first within
    a bucket. A reading with a value is final. An empty one is asked again until MISSING_TRIES."""
    out = []
    for bucket, (young, old) in BUCKETS.items():
        rows = s.execute(
            select(Item, Outlet.domain).join(Outlet, Outlet.id == Item.outlet_id)
            .where(Item.kind == "article", Item.relevant.is_(True), Item.duplicate_of.is_(None),
                   Item.published_at <= now - young, Item.published_at > now - old,
                   Outlet.monitored.is_not(False))
            .order_by(Item.published_at.desc())).all()
        ids = [it.id for it, _ in rows]
        tries = {}   # item id -> lookups so far (None when the reading has a value)
        for i in range(0, len(ids), 900):
            for iid, total, raw in s.execute(
                    select(ItemEngagement.item_id, ItemEngagement.total, ItemEngagement.raw)
                    .where(ItemEngagement.source == "fb_url", ItemEngagement.age_bucket == bucket,
                           ItemEngagement.item_id.in_(ids[i:i + 900]))):
                tries[iid] = None if total is not None else int((raw or {}).get("tries") or 1)
        for it, dom in rows:
            n = tries.get(it.id, 0)
            if n is None or n >= MISSING_TRIES or dom in SKIP_DOMAINS or dom in SHORTENERS or "/" in dom:
                continue
            url = outlet_url(it)
            if url and url.startswith(("http://", "https://")) and "," not in url:
                out.append((it, url, bucket, n))
    return out


def used_today(s: Session, now: datetime) -> int:
    return s.scalar(select(func.count()).select_from(ItemEngagement).where(
        ItemEngagement.source == "fb_url", ItemEngagement.measured_at >= now - timedelta(hours=24))) or 0


def url_key(url: str) -> str:
    """Graph may echo a URL with other escaping, scheme, www or a trailing slash: match on this form."""
    p = urlsplit(unquote(url.strip()))
    return f"{p.netloc.lower().removeprefix('www.')}{p.path.rstrip('/')}" + (f"?{p.query}" if p.query else "")


def _reading(node: dict | None, url: str, age_hours: float, tries: int = 1) -> dict:
    eng = (node or {}).get("engagement")
    if node is None or not isinstance(eng, dict):
        return {"total": None, "raw": {"url": url, "age_hours": age_hours, "missing": True, "tries": tries}}
    r, c, sh = (int(eng.get(k) or 0) for k in ("reaction_count", "comment_count", "share_count"))
    return {"reactions": r, "comments": c, "shares": sh, "total": float(r + c + sh),
            "raw": {"url": url, "age_hours": age_hours, "engagement": eng}}


def _usage_high(r: httpx.Response) -> bool:
    try:
        usage = json.loads(r.headers.get("x-app-usage") or "{}")
    except ValueError:
        return False
    return any(isinstance(v, (int, float)) and v >= USAGE_STOP for v in usage.values())


def _lookup(client: httpx.Client, urls: list[str], token: str) -> tuple[dict, bool]:
    """One Graph call. Returns ({url_key: node}, usage_high). Raises _Stop on errors that end the run."""
    try:
        r = polite_get(client, GRAPH, params={"ids": ",".join(urls), "fields": "engagement"},
                       headers={"Authorization": f"Bearer {token}"}, min_interval=1.0, retries=1)
        data = r.json()
    except Exception as e:  # noqa: BLE001 - an error message could quote the request: keep it out of the log
        raise _Stop(f"Facebook request failed ({type(e).__name__}).") from None
    err = data.get("error") if isinstance(data, dict) else None
    if err:
        code = err.get("code")
        if code == 100 and len(urls) > 1:
            raise ValueError("bad batch")
        if code in RATE_LIMIT_CODES or err.get("is_transient"):
            raise _Stop(f"Facebook rate limit or busy (code {code}). Stopped until the next run.")
        if code in TOKEN_CODES:
            raise _Stop(f"Facebook did not accept the app token (code {code}). "
                        "Check DW_FB_APP_ID and DW_FB_APP_SECRET.")
        if code == 100:
            return {url_key(urls[0]): {"error": code}}, _usage_high(r)
        raise _Stop(f"Facebook error code {code}: {str(err.get('message'))[:200]}")
    nodes = {}
    for key, node in (data or {}).items():
        if isinstance(node, dict):
            nodes[url_key(key)] = node
            if isinstance(node.get("id"), str):
                nodes.setdefault(url_key(node["id"]), node)
    return nodes, _usage_high(r)


def collect(s: Session, client: httpx.Client | None = None, now: datetime | None = None) -> RunResult:
    if not (settings.FB_APP_ID and settings.FB_APP_SECRET):
        raise AwaitingKey("Set DW_FB_APP_ID and DW_FB_APP_SECRET from a Meta developer app. "
                          "Link engagement needs no App Review.")
    token = f"{settings.FB_APP_ID}|{settings.FB_APP_SECRET}"
    now = now or utcnow()
    res = RunResult()
    budget = max(0, settings.FB_DAILY_URLS - used_today(s, now))
    todo = due(s, now)[:budget]
    own = client is None
    client = client or http_client(timeout=30)
    try:
        for i in range(0, len(todo), BATCH):
            chunk = todo[i:i + BATCH]
            urls = list(dict.fromkeys(u for _, u, _, _ in chunk))
            try:
                try:
                    nodes, high = _lookup(client, urls, token)
                except ValueError:   # one bad URL spoils a batch: read them one by one
                    nodes, high = {}, False
                    for u in urls:
                        n, h = _lookup(client, [u], token)
                        nodes.update(n)
                        high = high or h
            except _Stop as e:
                res.errors += 1
                res.detail = str(e)
                break
            by_bucket = {}
            for it, u, bucket, tries in chunk:
                age = round((now - it.published_at).total_seconds() / 3600, 1)
                by_bucket.setdefault(bucket, {})[it.id] = _reading(nodes.get(url_key(u)), u, age, tries + 1)
            for bucket, vals in by_bucket.items():
                res.rows += upsert_readings(s, "fb_url", bucket, vals)
            s.commit()
            if high:
                res.detail = "Facebook usage near its hourly cap. Stopped until the next run."
                break
    finally:
        if own:
            client.close()
    if not todo:
        res.detail = res.detail or ("Daily budget used." if budget == 0 else "Nothing due.")
    return res
