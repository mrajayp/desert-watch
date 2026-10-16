"""Engagement readings: shared helpers for story pickup, Facebook link engagement and outlet reach.

Readings live in item_engagement, one row per (item, source, age bucket):
  pickup  / now      distinct outlets that carried the same story (network.compute, every run)
  fb_url  / 48h, 7d  Facebook link engagement for the outlet's URL (collectors/fb_engagement.py)
Outlet reach lives in outlet.external['reach'] (reach.py). Counts are never compared raw across outlets."""
from datetime import datetime
from statistics import median
from urllib.parse import urlsplit

from sqlalchemy import select
from sqlalchemy.orm import Session, object_session

from .models import Item, ItemEngagement, Outlet, utcnow

# Link shorteners that turn up as "outlets" (Google News source links, scraped links). They are not
# publishers: left out of story clusters, link resolution and Facebook lookups.
SHORTENERS = frozenset({"t.co", "bit.ly", "ift.tt", "ow.ly", "buff.ly", "goo.gl", "tinyurl.com"})
GOOGLE_NEWS_HOST = "news.google.com"
FB_MIN_BASELINE = 20  # 7-day readings an outlet needs before we show its own median


def is_google_link(url: str | None) -> bool:
    return bool(url) and urlsplit(url).netloc.lower() == GOOGLE_NEWS_HOST


def outlet_url(item: Item) -> str | None:
    """The outlet's own link for an article: its URL, or the resolved one for a Google News link."""
    if item.url and not is_google_link(item.url):
        return item.url
    return (item.extra or {}).get("resolved_url")


def fresh_external(o: Outlet) -> dict:
    """outlet.external as stored now. Long runs re-read it before writing, so they never put back a
    stale copy over figures another job stored meanwhile (the column holds several sources' data).
    A change to o.external not yet flushed is dropped, so write it through set_external or commit first."""
    sess = object_session(o)
    if sess is not None and o.id is not None:
        sess.refresh(o, ["external"])
    return dict(o.external or {})


def set_external(o: Outlet, key: str, value) -> None:
    o.external = {**fresh_external(o), key: value}


def upsert_readings(s: Session, source: str, age_bucket: str, values: dict[int, dict]) -> int:
    """values: item_id -> column values. Writes only rows that changed. Returns rows written."""
    if not values:
        return 0
    have = {}
    ids = list(values)
    for i in range(0, len(ids), 900):
        for r in s.scalars(select(ItemEngagement).where(ItemEngagement.source == source,
                                                        ItemEngagement.age_bucket == age_bucket,
                                                        ItemEngagement.item_id.in_(ids[i:i + 900]))):
            have[r.item_id] = r
    now, n = utcnow(), 0
    for item_id, vals in values.items():
        row = have.get(item_id)
        if row is None:
            s.add(ItemEngagement(item_id=item_id, source=source, age_bucket=age_bucket, measured_at=now, **vals))
            n += 1
        elif any(getattr(row, k) != v for k, v in vals.items()):
            for k, v in vals.items():
                setattr(row, k, v)
            row.measured_at = now
            n += 1
    return n


def by_pickup(stmt):
    """Orders an item query by story pickup (most outlets first), then newest, then id (Google News items
    often share a timestamp, and paging needs a fixed order). 'Most picked up' sort."""
    from sqlalchemy import and_, func
    pk = and_(ItemEngagement.item_id == Item.id, ItemEngagement.source == "pickup", ItemEngagement.age_bucket == "now")
    return stmt.outerjoin(ItemEngagement, pk).order_by(func.coalesce(ItemEngagement.total, 0).desc(),
                                                      Item.published_at.desc(), Item.id.desc())


def attach_engagement(s: Session, items: list[dict]) -> list[dict]:
    """Adds 'engagement': {pickup, fb} to hydrated item dicts (see api/common.hydrate_items)."""
    ids = [it["id"] for it in items]
    pickup, best = {}, {}

    def rank(r):   # a reading with a value first, then the 7-day one, the reading we trust most
        return (r.total is not None, r.age_bucket == "7d")

    for i in range(0, len(ids), 900):
        for r in s.scalars(select(ItemEngagement).where(ItemEngagement.item_id.in_(ids[i:i + 900]),
                                                        ItemEngagement.source.in_(("pickup", "fb_url")))):
            if r.source == "pickup":
                pickup[r.item_id] = int(r.total) if r.total is not None else None
            elif r.item_id not in best or rank(r) > rank(best[r.item_id]):
                best[r.item_id] = r
    fb = {i: {"total": r.total, "reactions": r.reactions, "comments": r.comments, "shares": r.shares,
              "age_bucket": r.age_bucket, "measured_at": r.measured_at.isoformat()} for i, r in best.items()}
    for it in items:
        it["engagement"] = {"pickup": pickup.get(it["id"]), "fb": fb.get(it["id"])}
    return items


def outlet_reach(s: Session, o: Outlet, *, weeks: int = 8, now: datetime | None = None) -> dict:
    """Dated reach figures for one outlet: Tranco web rank, the 2023-24 scrape's Facebook figures
    (historical) and, once there are enough readings, the outlet's own recent Facebook median."""
    from datetime import timedelta
    ext = o.external or {}
    tranco = (ext.get("reach") or {}).get("tranco")
    scrape = ext.get("social_media_scrape") or {}
    hist = None
    if scrape.get("fb_engagement") is not None:
        arts = scrape.get("articles") or 0
        hist = {"fb_engagement": scrape.get("fb_engagement"), "fb_posts": scrape.get("fb_posts"),
                "articles": arts, "per_article": round(scrape["fb_engagement"] / arts, 1) if arts else None,
                "period": scrape.get("period"), "source": scrape.get("source"), "historical": True}
    now = now or utcnow()
    totals = [t for (t,) in s.execute(
        select(ItemEngagement.total).join(Item, Item.id == ItemEngagement.item_id)
        .where(Item.outlet_id == o.id, ItemEngagement.source == "fb_url", ItemEngagement.age_bucket == "7d",
               Item.published_at >= now - timedelta(weeks=weeks), ItemEngagement.total.is_not(None)))]
    recent = ({"median_7d": median(totals), "n": len(totals), "weeks": weeks}
              if len(totals) >= FB_MIN_BASELINE else None)
    return {"tranco": tranco, "facebook_historical": hist, "facebook_recent": recent}
