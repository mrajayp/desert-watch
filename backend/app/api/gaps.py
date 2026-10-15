from collections import Counter, defaultdict
from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from .. import auth, settings
from ..db import get_db
from ..ingest import load_rules, store_article
from ..models import (CellWeek, Comment, CoverageSeries, GapClaim, GapVote, Item, ItemRegion, ItemTheme, Region,
                      SourceRun, Suggestion, Theme, User, utcnow)
from ..scoring import LENSES, week_start
from .common import (country_or_404, hydrate_items, items_query, region_or_404, theme_or_404, window_bounds)

router = APIRouter(prefix="/api")

VOTES = {"real", "covered", "not_newsworthy"}


def gap_key(theme_id: int, region_id: int) -> str:
    return f"{theme_id}:{region_id}"


@router.get("/meta")
def meta(country: str = "LY", s: Session = Depends(get_db), _: User = Depends(auth.current_user)):
    c = country_or_404(s, country)
    regions = s.scalars(select(Region).where(Region.country_id == c.id)).all()
    themes = s.scalars(select(Theme).where(Theme.active.is_(True)).order_by(Theme.id)).all()
    latest = s.scalar(select(func.max(CellWeek.week_start)).where(CellWeek.country_id == c.id))
    weeks = s.scalars(select(CellWeek.week_start).where(CellWeek.country_id == c.id).distinct()
                      .order_by(CellWeek.week_start)).all()
    # a lens is "available" only when it has at least one scored (sufficient) cell
    available = {l for (l,) in s.execute(select(CellWeek.lens).where(
        CellWeek.country_id == c.id, CellWeek.insufficient.is_(False)).distinct())}
    return {
        "country": {"id": c.id, "iso2": c.iso2, "name_en": c.name_en, "name_ar": c.name_ar,
                    "boundaries": c.config.get("boundaries", {}), "district_geo": c.config.get("district_geo", {}),
                    "cities": c.config.get("cities", {})},
        "regions": [{"id": r.id, "slug": r.slug, "level": r.level, "parent_id": r.parent_id, "name_en": r.name_en,
                     "name_ar": r.name_ar, "lat": r.lat, "lon": r.lon} for r in regions],
        "themes": [{"id": t.id, "slug": t.slug, "group": t.group, "name_en": t.name_en, "name_ar": t.name_ar, "version": t.version}
                   for t in themes],
        "lenses": [{"key": k, "levels": v["levels"], "reference": v["reference"],
                    "min_need": settings.MIN_NEED_UNITS[k], "available": k in available} for k, v in LENSES.items()],
        "weeks": [w.isoformat() for w in weeks],
        "latest_week": latest.isoformat() if latest else None,
        "window_weeks": settings.WINDOW_WEEKS,
        "events": c.config.get("events", []),
    }


@router.get("/sources/health")
def sources_health(s: Session = Depends(get_db), _: User = Depends(auth.current_user)):
    from ..collectors import COLLECTORS, EXTRA_HEALTH
    out = []
    for key, label in [*((k, v[1]) for k, v in COLLECTORS.items()), *EXTRA_HEALTH.items()]:
        last = s.scalar(select(SourceRun).where(SourceRun.source_key == key).order_by(SourceRun.id.desc()).limit(1))
        last_ok = s.scalar(select(SourceRun).where(SourceRun.source_key == key, SourceRun.status.in_(("ok", "partial")))
                           .order_by(SourceRun.id.desc()).limit(1))
        stale = last_ok is None or (utcnow() - (last_ok.finished_at or last_ok.started_at)).total_seconds() > 48 * 3600
        out.append({"key": key, "label": label, "status": last.status if last else "never_run",
                    "last_run": last.started_at.isoformat() if last else None,
                    "last_ok": (last_ok.finished_at or last_ok.started_at).isoformat() if last_ok else None,
                    "rows": last.rows if last else 0, "error": (last.error or "")[:300] if last else None,
                    "stale": stale})
    return out


def _cell_json(c: CellWeek) -> dict:
    return {"theme_id": c.theme_id, "region_id": c.region_id, "week": c.week_start.isoformat(), "lens": c.lens,
            "need": c.need, "coverage": c.coverage, "ratio": c.ratio, "ref_ratio": c.ref_ratio, "gap": c.gap,
            "insufficient": c.insufficient, "flags": c.flags, "breakdown": c.breakdown}


def _feedback_summary(s: Session, theme_ids=None):
    votes = defaultdict(Counter)
    for v in s.scalars(select(GapVote)):
        votes[gap_key(v.theme_id, v.region_id)][v.vote] += 1
    comments = Counter(k for (k,) in s.execute(
        select(Comment.object_key).where(Comment.object_type == "gap", Comment.deleted.is_(False))))
    claims = defaultdict(Counter)
    for c in s.scalars(select(GapClaim).where(GapClaim.status != "dropped")):
        claims[gap_key(c.theme_id, c.region_id)][c.status] += 1
    return votes, comments, claims


@router.get("/cells")
def cells(country: str = "LY", lens: str = "audience", week: date | None = None, level: str | None = None,
          s: Session = Depends(get_db), _: User = Depends(auth.current_user)):
    c = country_or_404(s, country)
    if lens not in LENSES:
        raise HTTPException(400, "Unknown lens")
    week = week or s.scalar(select(func.max(CellWeek.week_start)).where(CellWeek.country_id == c.id))
    if not week:
        return {"week": None, "cells": []}
    q = select(CellWeek).where(CellWeek.country_id == c.id, CellWeek.lens == lens, CellWeek.week_start == week)
    if level:
        q = q.where(CellWeek.region_id.in_(select(Region.id).where(Region.level == level)))
    rows = s.scalars(q).all()
    votes, comments, claims = _feedback_summary(s)
    out = []
    for r in rows:
        j = _cell_json(r)
        k = gap_key(r.theme_id, r.region_id)
        j.update(votes=dict(votes.get(k, {})), comments=comments.get(k, 0), claims=dict(claims.get(k, {})))
        out.append(j)
    return {"week": week.isoformat(), "lens": lens, "cells": out}


@router.get("/cells/series")
def cell_series(theme_id: int, region_id: int, lens: str = "audience", s: Session = Depends(get_db),
                _: User = Depends(auth.current_user)):
    rows = s.scalars(select(CellWeek).where(CellWeek.theme_id == theme_id, CellWeek.region_id == region_id,
                                            CellWeek.lens == lens).order_by(CellWeek.week_start)).all()
    return [_cell_json(r) for r in rows]


@router.get("/cells/trends")
def all_series(country: str = "LY", lens: str = "audience", region_id: int | None = None,
               s: Session = Depends(get_db), _: User = Depends(auth.current_user)):
    """All themes' weekly series for one region (default national) — feeds small multiples."""
    c = country_or_404(s, country)
    if region_id is None:
        region_id = s.scalar(select(Region.id).where(Region.country_id == c.id, Region.level == "national"))
    rows = s.scalars(select(CellWeek).where(CellWeek.country_id == c.id, CellWeek.region_id == region_id,
                                            CellWeek.lens == lens).order_by(CellWeek.week_start)).all()
    out = defaultdict(list)
    for r in rows:
        out[r.theme_id].append(_cell_json(r))
    return {"region_id": region_id, "series": out}


@router.get("/coverage-history")
def coverage_history(theme_id: int, s: Session = Depends(get_db), _: User = Depends(auth.current_user)):
    rows = s.scalars(select(CoverageSeries).where(CoverageSeries.theme_id == theme_id).order_by(CoverageSeries.day)).all()
    out = defaultdict(list)
    for r in rows:
        out[r.series].append({"day": r.day.isoformat(), "value": r.value})
    return out


@router.get("/gap")
def gap_detail(theme_id: int, region_id: int, lens: str = "audience", week: date | None = None,
               source: str | None = None, s: Session = Depends(get_db), u: User = Depends(auth.current_user)):
    theme, region = theme_or_404(s, theme_id), region_or_404(s, region_id)
    week = week or s.scalar(select(func.max(CellWeek.week_start)).where(CellWeek.country_id == region.country_id))
    cell = s.scalar(select(CellWeek).where(CellWeek.theme_id == theme_id, CellWeek.region_id == region_id,
                                           CellWeek.lens == lens, CellWeek.week_start == week)) if week else None
    start, end = window_bounds(week or week_start(date.today()), settings.WINDOW_WEEKS)
    total, arts, by_source = items_query(s, country_id=region.country_id, theme_id=theme_id, region=region,
                                         start=start, end=end, limit=150, source=source, with_sources=True)
    need_kinds = LENSES[lens]["kinds"]
    need_total, need_items = items_query(s, country_id=region.country_id, theme_id=theme_id, region=region,
                                         start=start, end=end, kinds=need_kinds, limit=100)
    st_total, statements = items_query(s, country_id=region.country_id, theme_id=theme_id, region=region,
                                       start=start, end=end, kinds=("statement",), limit=30)
    k = gap_key(theme_id, region_id)
    votes = s.scalars(select(GapVote).where(GapVote.theme_id == theme_id, GapVote.region_id == region_id)
                      .order_by(GapVote.created_at.desc())).all()
    names = {x.id: x.display_name for x in s.scalars(select(User))}
    claims = s.scalars(select(GapClaim).where(GapClaim.theme_id == theme_id, GapClaim.region_id == region_id)).all()
    return {
        "theme": {"id": theme.id, "name_en": theme.name_en, "name_ar": theme.name_ar, "slug": theme.slug},
        "region": {"id": region.id, "name_en": region.name_en, "name_ar": region.name_ar, "level": region.level},
        "week": week.isoformat() if week else None, "window": [start.date().isoformat(), end.date().isoformat()],
        "cell": _cell_json(cell) if cell else None,
        "articles": {"total": total, "items": hydrate_items(s, arts), "by_source": by_source},
        "need_items": {"total": need_total, "items": hydrate_items(s, need_items)},
        "statements": {"total": st_total, "items": hydrate_items(s, statements)},
        "votes": [{"user": names.get(v.user_id), "mine": v.user_id == u.id, "vote": v.vote, "note": v.note,
                   "week": v.week_start.isoformat(), "covered_item_id": v.covered_item_id,
                   "at": v.created_at.isoformat()} for v in votes],
        "claims": [{"user": names.get(c.user_id), "mine": c.user_id == u.id, "status": c.status,
                    "published_url": c.published_url, "at": c.updated_at.isoformat()} for c in claims],
        "object_key": k,
    }


class VoteIn(BaseModel):
    theme_id: int
    region_id: int
    week: date
    lens: str
    vote: str
    covered_url: str | None = None
    note: str | None = Field(default=None, max_length=2000)


@router.post("/gap/vote")
def vote(body: VoteIn, s: Session = Depends(get_db), u: User = Depends(auth.require_contributor)):
    if body.vote not in VOTES:
        raise HTTPException(400, "vote must be real, covered or not_newsworthy")
    theme, region = theme_or_404(s, body.theme_id), region_or_404(s, body.region_id)
    covered_item_id = None
    if body.vote == "covered":
        if not body.covered_url:
            raise HTTPException(400, "Paste the link to the coverage.")
        from .items import add_article_core
        item = add_article_core(s, u, region.country_id, body.covered_url, theme_ids=[theme.id],
                                region_ids=[region.id] if region.level != "national" else [])
        covered_item_id = item.id
    v = s.scalar(select(GapVote).where(GapVote.user_id == u.id, GapVote.theme_id == theme.id,
                                       GapVote.region_id == region.id, GapVote.week_start == body.week))
    if not v:
        v = GapVote(user_id=u.id, theme_id=theme.id, region_id=region.id, week_start=body.week, lens=body.lens,
                    vote=body.vote)
        s.add(v)
    v.vote, v.lens, v.note, v.covered_item_id, v.created_at = body.vote, body.lens, body.note, covered_item_id, utcnow()
    s.commit()
    return {"ok": True, "covered_item_id": covered_item_id}


class ClaimIn(BaseModel):
    theme_id: int
    region_id: int
    status: str
    published_url: str | None = None


@router.post("/gap/claim")
def claim(body: ClaimIn, s: Session = Depends(get_db), u: User = Depends(auth.require_contributor)):
    if body.status not in ("working", "published", "dropped"):
        raise HTTPException(400, "Unknown status")
    region = region_or_404(s, body.region_id)
    theme_or_404(s, body.theme_id)
    c = s.scalar(select(GapClaim).where(GapClaim.user_id == u.id, GapClaim.theme_id == body.theme_id,
                                        GapClaim.region_id == body.region_id))
    if not c:
        c = GapClaim(user_id=u.id, theme_id=body.theme_id, region_id=body.region_id, status=body.status)
        s.add(c)
    c.status, c.published_url, c.updated_at = body.status, body.published_url, utcnow()
    if body.status == "published" and body.published_url:
        from .items import add_article_core
        add_article_core(s, u, region.country_id, body.published_url, theme_ids=[body.theme_id],
                         region_ids=[region.id] if region.level != "national" else [])
    s.commit()
    return {"ok": True}


class SuggestIn(BaseModel):
    kind: str
    payload: dict


@router.post("/suggestions")
def suggest(body: SuggestIn, s: Session = Depends(get_db), u: User = Depends(auth.require_contributor)):
    if body.kind not in ("gap", "keyword", "source", "alias", "outlet_category"):
        raise HTTPException(400, "Unknown suggestion kind")
    sug = Suggestion(user_id=u.id, kind=body.kind, payload=body.payload)
    s.add(sug)
    if body.kind == "gap":
        # A journalist-flagged gap is also a need unit for the 'journalist' lens.
        theme = theme_or_404(s, int(body.payload.get("theme_id", 0)))
        region = region_or_404(s, int(body.payload.get("region_id", 0)))
        it = Item(country_id=region.country_id, kind="suggestion", source_key="user",
                  dedupe_key=f"suggestion:{u.id}:{theme.id}:{region.id}:{utcnow().isoformat()}",
                  title=str(body.payload.get("note", ""))[:500] or f"Gap flagged: {theme.name_en}",
                  published_at=utcnow(), added_by=u.id)
        s.add(it)
        s.flush()
        s.add(ItemTheme(item_id=it.id, theme_id=theme.id, method="user"))
        if region.level != "national":
            s.add(ItemRegion(item_id=it.id, region_id=region.id, method="user"))
    s.commit()
    return {"ok": True, "id": sug.id}


@router.get("/coverage-monthly")
def coverage_monthly(theme_id: int, country: str = "LY", s: Session = Depends(get_db), _: User = Depends(auth.current_user)):
    """Monthly count of relevant collected articles for a theme, by language. Historical months
    come from backfill (Google News date-range search returns fewer items for older periods:
    compare shapes, not absolute levels across years)."""
    c = country_or_404(s, country)
    rows = s.execute(
        select(func.strftime("%Y-%m", Item.published_at), Item.lang, func.count(Item.id))
        .join(ItemTheme, ItemTheme.item_id == Item.id)
        .where(Item.country_id == c.id, Item.kind == "article", Item.relevant.is_(True), Item.duplicate_of.is_(None),
               ItemTheme.theme_id == theme_id, ItemTheme.active.is_(True))
        .group_by(func.strftime("%Y-%m", Item.published_at), Item.lang)).all()
    out = defaultdict(lambda: {"ar": 0, "en": 0, "other": 0})
    for m, lang, n in rows:
        out[m]["ar" if lang == "ar" else "en" if lang == "en" else "other"] += n
    if not out:
        return []
    # fill empty months so the time axis is continuous
    y, mo = map(int, min(out).split("-"))
    ly, lm = map(int, max(out).split("-"))
    months = []
    while (y, mo) <= (ly, lm):
        months.append(f"{y:04d}-{mo:02d}")
        y, mo = (y + 1, 1) if mo == 12 else (y, mo + 1)
    empty = {"ar": 0, "en": 0, "other": 0}
    return [{"month": m, **out.get(m, empty), "total": sum(out.get(m, empty).values())} for m in months]


@router.get("/digests")
def list_digests(country: str = "LY", s: Session = Depends(get_db), _: User = Depends(auth.current_user)):
    from ..models import Digest
    c = country_or_404(s, country)
    return [{"id": d.id, "week_start": d.week_start.isoformat(), "status": d.status, "model": d.model,
             "created_at": d.created_at.isoformat()}
            for d in s.scalars(select(Digest).where(Digest.country_id == c.id).order_by(Digest.week_start.desc()))]


@router.get("/digests/{did}")
def get_digest(did: int, s: Session = Depends(get_db), _: User = Depends(auth.current_user)):
    from ..models import Digest
    d = s.get(Digest, did)
    if not d:
        raise HTTPException(404, "Unknown digest")
    return {"id": d.id, "week_start": d.week_start.isoformat(), "status": d.status, "model": d.model,
            "created_at": d.created_at.isoformat(), "content_md": d.content_md, "facts": d.facts,
            "usage": d.usage, "error": d.error}


# ---------------------------------------------------------------- timeline
@router.get("/timeline")
def timeline(country: str = "LY", s: Session = Depends(get_db), _: User = Depends(auth.current_user)):
    """Monthly counts per theme (media articles), plus official statements and humanitarian
    reports as separate streams, and the dated key events to overlay."""
    from ..models import KeyEvent
    c = country_or_404(s, country)
    month = func.strftime("%Y-%m", Item.published_at)
    rows = s.execute(select(month, ItemTheme.theme_id, func.count(func.distinct(Item.id)))
                     .join(ItemTheme, and_(ItemTheme.item_id == Item.id, ItemTheme.active.is_(True)))
                     .where(Item.country_id == c.id, Item.relevant.is_(True), Item.duplicate_of.is_(None), Item.kind == "article")
                     .group_by(month, ItemTheme.theme_id)).all()
    streams = s.execute(select(month, Item.kind, func.count(Item.id))
                        .where(Item.country_id == c.id, Item.relevant.is_(True), Item.duplicate_of.is_(None), Item.kind.in_(("statement", "report")))
                        .group_by(month, Item.kind)).all()
    present = sorted({m for m, *_ in rows} | {m for m, *_ in streams})
    months = []
    if present:
        y, mo = map(int, present[0].split("-"))
        ly, lm = map(int, present[-1].split("-"))
        while (y, mo) <= (ly, lm):
            months.append(f"{y:04d}-{mo:02d}")
            y, mo = (y + 1, 1) if mo == 12 else (y, mo + 1)
    idx = {m: i for i, m in enumerate(months)}
    themes = defaultdict(lambda: [0] * len(months))
    official = {"statement": [0] * len(months), "report": [0] * len(months)}
    for m, tid, n in rows:
        themes[tid][idx[m]] += n
    for m, kind, n in streams:
        official[kind][idx[m]] += n
    names = {u.id: u.display_name for u in s.scalars(select(User))}
    events = [{"id": e.id, "day": e.day.isoformat(), "label": e.label, "theme_id": e.theme_id, "source_url": e.source_url,
               "origin": e.origin, "added_by": names.get(e.added_by)}
              for e in s.scalars(select(KeyEvent).where(KeyEvent.country_id == c.id).order_by(KeyEvent.day))]
    return {"months": months, "themes": themes, "statements": official["statement"], "reports": official["report"],
            "events": events}


@router.get("/official")
def official_items(country: str = "LY", kind: str = "statement", month: str | None = None, theme_id: int | None = None,
                   limit: int = 50, s: Session = Depends(get_db), _: User = Depends(auth.current_user)):
    c = country_or_404(s, country)
    q = select(Item).where(Item.country_id == c.id, Item.kind == kind, Item.relevant.is_(True), Item.duplicate_of.is_(None))
    if month:
        q = q.where(func.strftime("%Y-%m", Item.published_at) == month)
    if theme_id:
        q = q.where(Item.id.in_(select(ItemTheme.item_id).where(ItemTheme.theme_id == theme_id, ItemTheme.active.is_(True))))
    return hydrate_items(s, s.scalars(q.order_by(Item.published_at.desc()).limit(min(limit, 200))).all())


class KeyEventIn(BaseModel):
    day: date
    label: str = Field(min_length=3, max_length=200)
    theme_id: int | None = None
    source_url: str = Field(min_length=8, max_length=500)


@router.post("/key-events")
def add_key_event(body: KeyEventIn, country: str = "LY", s: Session = Depends(get_db),
                  u: User = Depends(auth.require_contributor)):
    from ..models import KeyEvent
    c = country_or_404(s, country)
    if not body.source_url.startswith(("http://", "https://")):
        raise HTTPException(400, "Add a source link for the event.")
    if body.theme_id:
        theme_or_404(s, body.theme_id)
    e = KeyEvent(country_id=c.id, day=body.day, label=body.label.strip(), theme_id=body.theme_id,
                 source_url=body.source_url, origin="user", added_by=u.id)
    s.add(e)
    s.commit()
    return {"id": e.id}


@router.delete("/key-events/{eid}")
def delete_key_event(eid: int, s: Session = Depends(get_db), u: User = Depends(auth.current_user)):
    from ..models import KeyEvent
    e = s.get(KeyEvent, eid)
    if not e:
        raise HTTPException(404, "Unknown event")
    if u.role != "admin" and e.added_by != u.id:
        raise HTTPException(403, "Only the person who added it, or an admin, can remove it")
    s.delete(e)
    s.commit()
    return {"ok": True}
