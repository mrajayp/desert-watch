from datetime import date

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import Country, Item, ItemRegion, ItemTheme, Outlet, OutletCategory, Region, Theme


def country_or_404(s: Session, iso2: str) -> Country:
    c = s.scalar(select(Country).where(Country.iso2 == iso2.upper()))
    if not c:
        raise HTTPException(404, "Unknown country")
    return c


def theme_or_404(s: Session, theme_id: int) -> Theme:
    t = s.get(Theme, theme_id)
    if not t:
        raise HTTPException(404, "Unknown theme")
    return t


def region_or_404(s: Session, region_id: int) -> Region:
    r = s.get(Region, region_id)
    if not r:
        raise HTTPException(404, "Unknown region")
    return r


def descendants(s: Session, region: Region) -> list[int]:
    out, frontier = [region.id], [region.id]
    while frontier:
        kids = s.scalars(select(Region.id).where(Region.parent_id.in_(frontier))).all()
        out += kids
        frontier = kids
    return out


def outlet_categories(s: Session, outlet_ids: list[int] | None = None) -> dict[int, dict]:
    q = select(OutletCategory).where(OutletCategory.status == "active", OutletCategory.valid_to.is_(None))
    if outlet_ids is not None:
        q = q.where(OutletCategory.outlet_id.in_(outlet_ids))
    out: dict[int, dict] = {}
    for c in s.scalars(q):
        out.setdefault(c.outlet_id, {})[c.dimension] = {
            "value": c.value, "confidence": c.confidence, "evidence_url": c.evidence_url, "id": c.id}
    return out


def item_json(it: Item, outlet: Outlet | None, themes: list[int], regions: list[int], cats: dict | None = None) -> dict:
    return {
        "id": it.id, "kind": it.kind, "url": it.url, "title": it.title, "snippet": it.snippet, "lang": it.lang,
        "published_at": it.published_at.isoformat(), "source": it.source_key, "value": it.value,
        "outlet": {"id": outlet.id, "name": outlet.name, "domain": outlet.domain,
                   "categories": {k: v["value"] for k, v in (cats or {}).items()}} if outlet else None,
        "theme_ids": themes, "region_ids": regions, "user_added": it.added_by is not None,
    }


def window_bounds(week: date, weeks: int):
    from datetime import datetime, timedelta
    end = datetime.combine(week + timedelta(days=7), datetime.min.time())
    start = end - timedelta(weeks=weeks)
    return start, end


def items_query(s: Session, *, country_id: int, theme_id: int | None, region: Region | None, start, end,
                kinds=("article",), limit=200, offset=0, outlet_id: int | None = None, q: str | None = None):
    stmt = select(Item).where(Item.country_id == country_id, Item.kind.in_(kinds), Item.relevant.is_(True),
                              Item.published_at >= start, Item.published_at < end)
    if theme_id:
        stmt = stmt.where(Item.id.in_(select(ItemTheme.item_id).where(ItemTheme.theme_id == theme_id,
                                                                      ItemTheme.active.is_(True))))
    if region is not None and region.level != "national":
        stmt = stmt.where(Item.id.in_(select(ItemRegion.item_id).where(
            ItemRegion.region_id.in_(descendants(s, region)), ItemRegion.active.is_(True))))
    if outlet_id:
        stmt = stmt.where(Item.outlet_id == outlet_id)
    if q:
        stmt = stmt.where(Item.title.ilike(f"%{q}%"))
    total = s.scalar(select(func.count()).select_from(stmt.subquery()))
    rows = s.scalars(stmt.order_by(Item.published_at.desc()).limit(limit).offset(offset)).all()
    return total, rows


def hydrate_items(s: Session, rows: list[Item]) -> list[dict]:
    ids = [r.id for r in rows]
    if not ids:
        return []
    th, rg = {}, {}
    for it in s.scalars(select(ItemTheme).where(ItemTheme.item_id.in_(ids), ItemTheme.active.is_(True))):
        th.setdefault(it.item_id, []).append(it.theme_id)
    for ir in s.scalars(select(ItemRegion).where(ItemRegion.item_id.in_(ids), ItemRegion.active.is_(True))):
        rg.setdefault(ir.item_id, []).append(ir.region_id)
    outlet_ids = list({r.outlet_id for r in rows if r.outlet_id})
    outlets = {o.id: o for o in s.scalars(select(Outlet).where(Outlet.id.in_(outlet_ids)))}
    cats = outlet_categories(s, outlet_ids)
    return [item_json(r, outlets.get(r.outlet_id), th.get(r.id, []), rg.get(r.id, []), cats.get(r.outlet_id))
            for r in rows]
