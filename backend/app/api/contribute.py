"""The Contribute page: short queues of things that need a person, plus your own tally.
Each queue is cheap to compute and capped; the page links each task to where it is done."""
from datetime import timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import and_, exists, func, not_, or_, select
from sqlalchemy.orm import Session

from .. import auth, settings
from ..db import get_db
from ..models import (ArticleAssessment, CellWeek, Comment, Event, GapClaim, GapVote, Item, ItemRegion, ItemTheme,
                      Outlet, OutletCategory, Suggestion, User, utcnow)
from ..scoring import counted_items, scored_articles
from .common import country_or_404, hydrate_items, outlet_categories

router = APIRouter(prefix="/api")

RECENT_DAYS = 14
GAP_MIN = settings.GAP_RED_FROM  # the one red threshold every page uses (/api/meta red_from)


@router.get("/contribute")
def contribute(country: str = "LY", s: Session = Depends(get_db), u: User = Depends(auth.current_user)):
    c = country_or_404(s, country)
    since = utcnow() - timedelta(days=RECENT_DAYS)
    recent = and_(*counted_items(c.id), Item.kind == "article", Item.published_at >= since, Item.added_by.is_(None))
    # correlated EXISTS uses the (item_id, ...) primary keys; IN (subquery) scanned whole tables
    has_theme = exists().where(ItemTheme.item_id == Item.id, ItemTheme.active.is_(True))
    has_region = exists().where(ItemRegion.item_id == Item.id, ItemRegion.active.is_(True))
    assessed = exists().where(ArticleAssessment.item_id == Item.id)

    # 1. Gaps nobody has judged yet: the biggest red gaps of the last 4 weeks, across lenses (a single
    #    week is often empty: the current one is partial, and coverage surges hide gaps). Red is the
    #    calibrated verdict `short` (the shortfall is larger than chance would explain); a cell scored
    #    before verdicts existed (no verdict yet) still qualifies by the old threshold, GAP_MIN.
    week = s.scalar(select(func.max(CellWeek.week_start)).where(CellWeek.country_id == c.id))
    gaps = []
    if week:
        first = week - timedelta(weeks=3)
        voted = {(v.theme_id, v.region_id, v.week_start) for v in s.scalars(select(GapVote).where(GapVote.week_start >= first))}
        red = or_(CellWeek.verdict == "short", and_(CellWeek.verdict.is_(None), CellWeek.gap >= GAP_MIN))
        for cell in s.scalars(select(CellWeek).where(
                CellWeek.country_id == c.id, CellWeek.week_start >= first, CellWeek.insufficient.is_(False),
                CellWeek.gap.is_not(None), red).order_by(CellWeek.gap.desc()).limit(200)):
            if (cell.theme_id, cell.region_id, cell.week_start) in voted or any(
                    g["theme_id"] == cell.theme_id and g["region_id"] == cell.region_id for g in gaps):
                continue
            # articles: the scored count the gap used; articles_all: every monitored source (= coverage,
            # kept for one release). The verdict fields are what the row's sentence is built from.
            b = cell.breakdown or {}
            gaps.append({"theme_id": cell.theme_id, "region_id": cell.region_id, "lens": cell.lens, "gap": cell.gap,
                         "week": cell.week_start.isoformat(), "articles": scored_articles(cell),
                         "articles_all": int(cell.coverage), "coverage": cell.coverage, "need": cell.need,
                         "flags": cell.flags, "verdict": cell.verdict, "expected_4w": b.get("expected_4w"),
                         "ratio_lo": b.get("ratio_lo"), "ratio_hi": b.get("ratio_hi"), "chance": b.get("chance"),
                         "baseline_backfilled": bool(b.get("baseline_backfilled"))})
            if len(gaps) == 6:
                break

    # 2. Recent articles the rules could not file: no topic, or no place
    untagged_q = select(Item).where(recent, not_(has_theme))
    unplaced_q = select(Item).where(recent, has_theme, not_(has_region))
    count = lambda q: s.scalar(select(func.count()).select_from(q.subquery()))  # noqa: E731
    untagged = s.scalars(untagged_q.order_by(Item.published_at.desc()).limit(6)).all()
    unplaced = s.scalars(unplaced_q.order_by(Item.published_at.desc()).limit(6)).all()

    # 3. Articles to rate: recent, filed, from the busiest outlets, not yet assessed by anyone
    busiest = select(Item.outlet_id).where(recent).group_by(Item.outlet_id).order_by(func.count().desc()).limit(15)
    to_assess = s.scalars(select(Item).where(recent, Item.outlet_id.in_(busiest), has_theme, not_(assessed))
                          .order_by(Item.published_at.desc()).limit(40)).all()
    seen, picked = set(), []
    for it in to_assess:  # one per outlet, so the ratings spread across outlets
        if it.outlet_id not in seen:
            seen.add(it.outlet_id)
            picked.append(it)
        if len(picked) == 5:
            break

    # 4. Outlets with real volume but no scope or alignment on record
    vol = dict(s.execute(select(Item.outlet_id, func.count()).where(
        Item.country_id == c.id, Item.kind == "article", Item.published_at >= utcnow() - timedelta(days=84))
        .group_by(Item.outlet_id).having(func.count() >= 5)).all())
    cats = outlet_categories(s, list(vol))
    need_cat = [oid for oid in vol if not {"scope", "alignment"} <= set(cats.get(oid, {}))]
    need_cat.sort(key=lambda oid: -vol[oid])
    outlets = {o.id: o for o in s.scalars(select(Outlet).where(Outlet.id.in_(need_cat[:8])))}
    outlet_rows = [{"id": oid, "name": outlets[oid].name, "domain": outlets[oid].domain, "articles": vol[oid],
                    "missing": [d for d in ("scope", "alignment") if d not in cats.get(oid, {})]}
                   for oid in need_cat[:8] if oid in outlets]

    # 5. Your tally, and the team's over the last 30 days
    month = utcnow() - timedelta(days=30)
    mine = {
        "votes": s.scalar(select(func.count()).where(GapVote.user_id == u.id)),
        "assessments": s.scalar(select(func.count()).where(ArticleAssessment.user_id == u.id)),
        "corrections": s.scalar(select(func.count()).where(Event.pseudo_id == u.pseudo_id, Event.type == "correction")),
        "added": s.scalar(select(func.count()).where(Item.added_by == u.id, Item.kind == "article")),
        "comments": s.scalar(select(func.count()).where(Comment.user_id == u.id, Comment.deleted.is_(False))),
        "suggestions": s.scalar(select(func.count()).where(Suggestion.user_id == u.id)),
        "claims": s.scalar(select(func.count()).where(GapClaim.user_id == u.id)),
    }
    team = {
        "votes": s.scalar(select(func.count()).where(GapVote.created_at >= month)),
        "assessments": s.scalar(select(func.count()).where(ArticleAssessment.created_at >= month)),
        "corrections": s.scalar(select(func.count()).where(Event.type == "correction", Event.ts >= month)),
        "added": s.scalar(select(func.count()).where(Item.added_by.is_not(None), Item.kind == "article",
                                                     Item.created_at >= month)),
        "contributors": len({x for (x,) in s.execute(select(GapVote.user_id).where(GapVote.created_at >= month))}
                            | {x for (x,) in s.execute(select(ArticleAssessment.user_id).where(ArticleAssessment.created_at >= month))}
                            | {x for (x,) in s.execute(select(Item.added_by).where(Item.added_by.is_not(None), Item.created_at >= month))}),
    }
    my_suggestions = [{"id": x.id, "kind": x.kind, "payload": x.payload, "status": x.status,
                       "at": x.created_at.isoformat()}
                      for x in s.scalars(select(Suggestion).where(Suggestion.user_id == u.id)
                                         .order_by(Suggestion.created_at.desc()).limit(10))]
    return {
        "can_contribute": u.role != "viewer",
        "week": week.isoformat() if week else None,
        "gaps": gaps,
        "untagged": {"total": count(untagged_q), "items": hydrate_items(s, untagged)},
        "unplaced": {"total": count(unplaced_q), "items": hydrate_items(s, unplaced)},
        "to_assess": hydrate_items(s, picked),
        "outlets": {"total": len(need_cat), "items": outlet_rows},
        "mine": mine, "team": team, "my_suggestions": my_suggestions,
    }
