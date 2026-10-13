"""Behaviour logging and label building.

Explicit actions (votes, corrections, assessments, added articles) always become
labels. Implicit events (impressions, clicks, dwell) are only stored for users who
have not opted out, and only feed 'interest' labels."""
from datetime import timedelta

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from . import settings
from .models import ArticleAssessment, Event, GapVote, Item, Label, User, utcnow

IMPLICIT = {"impression", "click", "dwell", "dismiss", "save", "filter", "search", "view"}
EXPLICIT = {"vote", "comment", "correction", "assessment", "add_article", "suggestion", "claim"}
ALLOWED = IMPLICIT | EXPLICIT
MAX_BATCH = 200


def record_events(s: Session, user: User, session_id: str | None, events: list[dict]) -> int:
    n = 0
    for e in events[:MAX_BATCH]:
        t = str(e.get("type", ""))[:24]
        if t not in ALLOWED:
            continue
        if t in IMPLICIT and user.tracking_opt_out:
            continue
        ctx = e.get("context") or {}
        if not isinstance(ctx, dict) or len(str(ctx)) > 2000:
            ctx = {}
        s.add(Event(pseudo_id=user.pseudo_id, session_id=(session_id or "")[:40] or None, type=t,
                    object_type=(e.get("object_type") or None) and str(e["object_type"])[:10],
                    object_key=(e.get("object_key") or None) and str(e["object_key"])[:60], context=ctx))
        n += 1
    s.commit()
    return n


def _add_label(s: Session, ref: str, **kw) -> bool:
    if s.scalar(select(Label.id).where(Label.source_ref == ref)):
        return False
    s.add(Label(source_ref=ref, **kw))
    return True


def build_labels(s: Session) -> int:
    """Idempotent: each source row/event yields at most one label (keyed by source_ref)."""
    n = 0
    pseudo = {u.id: u.pseudo_id for u in s.scalars(select(User))}
    for v in s.scalars(select(GapVote)):
        n += _add_label(s, f"gap_vote:{v.id}:{v.vote}", label_type="gap_real", object_type="gap",
                        object_key=f"{v.theme_id}:{v.region_id}:{v.week_start.isoformat()}",
                        value={"vote": v.vote, "lens": v.lens}, pseudo_id=pseudo.get(v.user_id), origin="explicit")
    for a in s.scalars(select(ArticleAssessment)):
        n += _add_label(s, f"assessment:{a.id}:{a.accuracy}{a.depth}{a.local_sourcing}", label_type="article_quality",
                        object_type="item", object_key=str(a.item_id),
                        value={"accuracy": a.accuracy, "depth": a.depth, "local_sourcing": a.local_sourcing},
                        pseudo_id=pseudo.get(a.user_id), origin="explicit")
    for it in s.scalars(select(Item).where(Item.added_by.is_not(None))):
        n += _add_label(s, f"added:{it.id}", label_type="theme_relevance", object_type="item", object_key=str(it.id),
                        value={"themes": it.extra.get("user_themes", []), "relevant": True},
                        pseudo_id=pseudo.get(it.added_by), origin="explicit")
    for e in s.scalars(select(Event).where(Event.type == "correction")):
        n += _add_label(s, f"event:{e.id}", label_type=e.context.get("label_type", "theme_relevance"),
                        object_type=e.object_type or "item", object_key=e.object_key or "",
                        value=e.context, pseudo_id=e.pseudo_id, origin="explicit")
    # implicit interest: long dwell on a gap (>= 20 s) = weak positive
    for e in s.scalars(select(Event).where(Event.type == "dwell", Event.object_type == "gap")):
        if float(e.context.get("seconds", 0)) >= 20:
            n += _add_label(s, f"event:{e.id}", label_type="interest", object_type="gap", object_key=e.object_key or "",
                            value={"seconds": e.context.get("seconds"), "position": e.context.get("position")},
                            pseudo_id=e.pseudo_id, origin="implicit", weight=0.2)
    s.commit()
    return n


def purge_old_events(s: Session) -> int:
    cutoff = utcnow() - timedelta(days=settings.RAW_EVENT_RETENTION_DAYS)
    r = s.execute(delete(Event).where(Event.ts < cutoff))
    s.commit()
    return r.rowcount or 0
