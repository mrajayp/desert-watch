from collections import Counter
from datetime import timedelta

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import auth
from ..classify import ThemeRule, classify_item, clean_snippet
from ..db import SessionLocal, get_db
from ..models import (Event, GapVote, Invite, Item, Label, Suggestion, Theme, User, utcnow)
from ..textnorm import normalise

router = APIRouter(prefix="/api")


# ---------------------------------------------------------------- themes (any user can read, admins edit)
class ThemeIn(BaseModel):
    group: str | None = Field(default=None, max_length=40)
    cooc: list[list[str]] = Field(default_factory=list)
    strict: bool = False
    name_en: str = Field(min_length=2, max_length=120)
    name_ar: str = Field(default="", max_length=120)
    en_terms: list[str] = Field(default_factory=list)
    ar_terms: list[str] = Field(default_factory=list)
    exclude: list[str] = Field(default_factory=list)
    veto: list[dict] | None = None   # None keeps the stored value (the Admin form does not edit these yet)
    mask: list[str] | None = None
    acled_event_types: list[str] = Field(default_factory=list)
    reliefweb_themes: list[str] = Field(default_factory=list)
    active: bool = True


def _theme_json(t: Theme) -> dict:
    return {c.name: getattr(t, c.name) for c in Theme.__table__.columns if c.name != "updated_at"} | {
        "updated_at": t.updated_at.isoformat()}


@router.get("/themes")
def list_themes(s: Session = Depends(get_db), _: User = Depends(auth.current_user)):
    return [_theme_json(t) for t in s.scalars(select(Theme).order_by(Theme.id))]


@router.post("/themes/preview")
def preview_theme(body: ThemeIn, days: int = 30, tid: int | None = None, s: Session = Depends(get_db),
                  _: User = Depends(auth.current_user)):
    """What would these terms match over recent articles? Includes user labels so admins
    can see precision against human judgement before saving. Fields the form does not send
    (pairs, vetoes, masks) come from the stored theme (`tid`, or the theme with this name)."""
    stored = s.get(Theme, tid) if tid else s.scalar(select(Theme).where(Theme.name_en == body.name_en))

    def pick(k):
        v = getattr(body, k)
        return getattr(stored, k) if stored and (k not in body.model_fields_set or v is None) else v

    rule = ThemeRule.build(0, "preview", 0, body.en_terms, body.ar_terms, body.exclude, pick("cooc"), pick("strict"),
                           veto=pick("veto"), mask=pick("mask"))
    since = utcnow() - timedelta(days=days)
    rows = s.scalars(select(Item).where(Item.kind == "article", Item.published_at >= since)
                     .order_by(Item.published_at.desc()).limit(5000)).all()
    matched = []
    for it in rows:
        m = classify_item(it.title, clean_snippet(it.source_key, it.title, it.snippet), [rule]).get(0)
        if m:
            matched.append((it, m[1]))
    term_counts = Counter(h for _, hs in matched for h in hs)
    return {"scanned": len(rows), "matched": len(matched),
            "top_terms": term_counts.most_common(20),
            "samples": [{"id": it.id, "title": it.title, "lang": it.lang, "hits": hs, "relevant": it.relevant}
                        for it, hs in matched[:40]]}


def _retag_theme(theme_id: int, recompute: bool = True, classify: bool | None = None):
    """Re-run rule tagging for one theme over all articles. Rule links follow the rules, query
    links count only when the rules confirm them, user and model links are kept (retag.py).
    With a model live the model then re-scores every article (classify_all, as after Activate), before
    the recompute. classify defaults to recompute: sync-themes retags several themes without either
    and is told to run classify-items --all once at the end."""
    from ..jobs import JOBS
    from ..ml.registry import active
    from ..retag import retag_theme
    from ..scoring import compute_all
    classify = recompute if classify is None else classify
    with SessionLocal() as s:
        retag_theme(s, theme_id)
        live = active(s)
    if live and classify:
        JOBS["classify_all"]()
    elif live:
        print(f"A theme model is live ({live.version}): run classify-items --all after the themes are retagged.")
    if recompute:
        with SessionLocal() as s:
            compute_all(s)
            from ..gtrends import flag_missing_weeks
            flag_missing_weeks(s)  # search lens: the same rule as jobs.recompute


@router.post("/themes")
def create_theme(body: ThemeIn, bg: BackgroundTasks, s: Session = Depends(get_db), u: User = Depends(auth.require_admin)):
    slug = normalise(body.name_en).strip().replace(" ", "_")[:60]
    if s.scalar(select(Theme).where(Theme.slug == slug)):
        raise HTTPException(400, "A theme with that name exists")
    t = Theme(slug=slug, **body.model_dump(exclude_none=True))
    s.add(t)
    s.commit()
    bg.add_task(_retag_theme, t.id)
    return _theme_json(t)


@router.put("/themes/{tid}")
def update_theme(tid: int, body: ThemeIn, bg: BackgroundTasks, s: Session = Depends(get_db),
                 u: User = Depends(auth.require_admin)):
    t = s.get(Theme, tid)
    if not t:
        raise HTTPException(404, "Unknown theme")
    # fields the form does not send (cooc, strict, group, veto, mask) keep their stored values
    for k, v in body.model_dump(exclude_unset=True).items():
        if v is not None or k not in ("veto", "mask"):
            setattr(t, k, v)
    t.version += 1
    t.updated_at = utcnow()
    s.commit()
    bg.add_task(_retag_theme, t.id)
    return _theme_json(t)


# ---------------------------------------------------------------- invites / users
class InviteIn(BaseModel):
    email: str
    role: str = "journalist"


@router.post("/admin/invites")
def invite(body: InviteIn, s: Session = Depends(get_db), u: User = Depends(auth.require_admin)):
    if body.role not in ("journalist", "admin"):
        raise HTTPException(400, "Unknown role")
    token = auth.create_invite(s, body.email, body.role, u.id)
    s.commit()
    return {"invite_path": f"/invite/{token}", "expires_days": 7}


def _user_json(x: User, names: dict) -> dict:
    return {"id": x.id, "email": x.email, "display_name": x.display_name, "role": x.role, "active": x.active,
            "status": x.status or "active", "organisation": x.organisation, "note": x.signup_note,
            "approved_by": names.get(x.approved_by), "created_at": x.created_at.isoformat()}


@router.get("/admin/users")
def users(s: Session = Depends(get_db), _: User = Depends(auth.require_admin)):
    rows = s.scalars(select(User).order_by(User.created_at.desc())).all()
    names = {x.id: x.display_name for x in rows}
    return [_user_json(x, names) for x in rows if not x.email.startswith("deleted-")]


class UserPatch(BaseModel):
    role: str | None = None
    status: str | None = None  # active | rejected | disabled


@router.patch("/admin/users/{uid}")
def patch_user(uid: int, body: UserPatch, s: Session = Depends(get_db), me: User = Depends(auth.require_admin)):
    """Approve / reject access requests, change roles, disable or re-enable accounts.
    Admins cannot demote or disable themselves (prevents locking everyone out)."""
    from ..models import AuthSession
    from sqlalchemy import delete
    u = s.get(User, uid)
    if not u:
        raise HTTPException(404, "Unknown user")
    if body.role is not None:
        if body.role not in auth.ROLES:
            raise HTTPException(400, "Role must be admin, journalist or viewer")
        if u.id == me.id and body.role != "admin":
            raise HTTPException(400, "You cannot remove your own admin role")
        u.role = body.role
    if body.status is not None:
        if body.status not in ("active", "rejected", "disabled"):
            raise HTTPException(400, "Status must be active, rejected or disabled")
        if u.id == me.id and body.status != "active":
            raise HTTPException(400, "You cannot disable your own account")
        if body.status == "active" and (u.status or "active") == "pending":
            u.approved_by = me.id
        u.status = body.status
        u.active = body.status == "active"
        if body.status != "active":
            s.execute(delete(AuthSession).where(AuthSession.user_id == u.id))  # sign them out everywhere
    s.commit()
    names = {x.id: x.display_name for x in s.scalars(select(User))}
    return _user_json(u, names)


# ---------------------------------------------------------------- suggestions queue
@router.get("/admin/suggestions")
def suggestions(status: str = "pending", s: Session = Depends(get_db), _: User = Depends(auth.require_admin)):
    names = {x.id: x.display_name for x in s.scalars(select(User))}
    return [{"id": g.id, "kind": g.kind, "payload": g.payload, "status": g.status, "origin": g.origin,
             "user": names.get(g.user_id), "at": g.created_at.isoformat()}
            for g in s.scalars(select(Suggestion).where(Suggestion.status == status).order_by(Suggestion.id.desc()))]


class ReviewIn(BaseModel):
    accept: bool


@router.post("/admin/suggestions/{sid}")
def review_suggestion(sid: int, body: ReviewIn, s: Session = Depends(get_db), u: User = Depends(auth.require_admin)):
    g = s.get(Suggestion, sid)
    if not g:
        raise HTTPException(404, "Unknown suggestion")
    g.status, g.reviewed_by = ("accepted" if body.accept else "rejected"), u.id
    if body.accept and g.kind == "keyword":
        t = s.get(Theme, int(g.payload.get("theme_id", 0)))
        term, lang = g.payload.get("term"), g.payload.get("lang", "en")
        if t and term:
            attr = "ar_terms" if lang == "ar" else "en_terms"
            setattr(t, attr, [*getattr(t, attr), term])
            t.version += 1
    s.commit()
    return {"ok": True}


# ---------------------------------------------------------------- jobs
@router.post("/admin/run/{job}")
def run_job(job: str, bg: BackgroundTasks, _: User = Depends(auth.require_admin)):
    from ..jobs import JOBS
    if job not in JOBS:
        raise HTTPException(404, "Unknown job")
    bg.add_task(JOBS[job])
    return {"queued": job}


# ---------------------------------------------------------------- learning overview
@router.get("/admin/learning")
def learning(s: Session = Depends(get_db), _: User = Depends(auth.require_admin)):
    labels = dict(s.execute(select(Label.label_type, func.count(Label.id)).group_by(Label.label_type)).all())
    by_origin = dict(s.execute(select(Label.origin, func.count(Label.id)).group_by(Label.origin)).all())
    events = dict(s.execute(select(Event.type, func.count(Event.id)).group_by(Event.type)).all())
    # agreement on gap votes: share of gaps (with >=2 votes) where all votes agree
    votes: dict = {}
    for v in s.scalars(select(GapVote)):
        votes.setdefault((v.theme_id, v.region_id, v.week_start), []).append(v.vote)
    multi = [vs for vs in votes.values() if len(vs) >= 2]
    agree = sum(1 for vs in multi if len(set(vs)) == 1)
    weekly = s.execute(select(func.strftime("%Y-%W", Label.created_at), func.count(Label.id))
                       .group_by(func.strftime("%Y-%W", Label.created_at)).order_by(func.strftime("%Y-%W", Label.created_at))).all()
    # Precision proxy: share of search-sourced items whose query theme is confirmed by the rules.
    from ..ingest import item_hits, load_rules
    from ..models import Country
    confirm = {}
    country = s.scalar(select(Country))
    if country:
        rules = load_rules(s, country.id)
        slug2id = {t.slug: t.id for t in s.scalars(select(Theme))}
        tot, hit = Counter(), Counter()
        since = utcnow() - timedelta(days=28)
        for it in s.scalars(select(Item).where(Item.kind == "article", Item.source_key.in_(("gnews", "gdelt")),
                                               Item.relevant.is_(True), Item.duplicate_of.is_(None), Item.published_at >= since)):
            q = (it.extra or {}).get("query_theme")
            if q in slug2id:
                k = f"{q}/{it.lang}"
                tot[k] += 1
                hit[k] += slug2id[q] in item_hits(rules, it)
        confirm = {k: {"n": tot[k], "confirmed": round(hit[k] / tot[k], 2)} for k in sorted(tot)}
    from ..jobs import THRESHOLDS
    from ..ml.registry import summary as model_summary
    models = model_summary(s)
    return {"labels": labels, "by_origin": by_origin, "events": events,
            "vote_agreement": {"gaps_with_multiple_votes": len(multi), "unanimous": agree},
            "labels_per_week": [{"week": w, "n": n} for w, n in weekly],
            "thresholds": THRESHOLDS, "rule_confirmation": confirm,
            "models": models, "note": None if any(m["active"] for m in models) else "No theme model is live yet."}


# ---------------------------------------------------------------- Google Alerts
class AlertFeedsIn(BaseModel):
    lines: str = Field(max_length=100_000)


@router.get("/admin/alerts")
def list_alerts(s: Session = Depends(get_db), _: User = Depends(auth.require_admin)):
    from ..alerts import SETTINGS
    from ..models import AlertFeed
    rows = s.scalars(select(AlertFeed).order_by(AlertFeed.key)).all()
    return {"settings": SETTINGS, "alerts": [
        {"key": a.key, "label": a.label, "lang": a.lang, "query": a.query, "feed_url": a.feed_url, "active": a.active,
         "last_ok_at": a.last_ok_at.isoformat() if a.last_ok_at else None, "last_items": a.last_items,
         "last_error": a.last_error} for a in rows]}


@router.post("/admin/alerts")
def attach_alerts(body: AlertFeedsIn, s: Session = Depends(get_db), _: User = Depends(auth.require_admin)):
    from ..alerts import attach_feeds
    return attach_feeds(s, body.lines)


# ---------------------------------------------------------------- page feedback (admin side)
@router.get("/admin/feedback")
def feedback_queue(status: str | None = None, s: Session = Depends(get_db), _: User = Depends(auth.require_admin)):
    from ..models import Feedback
    names = {x.id: x.display_name for x in s.scalars(select(User))}
    q = select(Feedback).order_by(Feedback.created_at.desc())
    if status:
        q = q.where(Feedback.status == status)
    return [{"id": f.id, "page": f.page, "kind": f.kind, "body": f.body, "status": f.status, "reply": f.reply,
             "user": names.get(f.user_id), "replied_by": names.get(f.replied_by), "at": f.created_at.isoformat()}
            for f in s.scalars(q.limit(300))]


class FeedbackReply(BaseModel):
    status: str | None = None
    reply: str | None = Field(default=None, max_length=4000)


@router.patch("/admin/feedback/{fid}")
def answer_feedback(fid: int, body: FeedbackReply, s: Session = Depends(get_db), me: User = Depends(auth.require_admin)):
    from ..models import Feedback
    f = s.get(Feedback, fid)
    if not f:
        raise HTTPException(404, "Unknown feedback")
    if body.status:
        if body.status not in ("new", "answered", "planned", "done", "closed"):
            raise HTTPException(400, "Unknown status")
        f.status = body.status
    if body.reply is not None:
        f.reply, f.replied_by = body.reply.strip() or None, me.id
        if f.reply and f.status == "new":
            f.status = "answered"
    f.updated_at = utcnow()
    s.commit()
    return {"ok": True}


@router.get("/admin/methods")
def methods(_: User = Depends(auth.require_admin)):
    """'How the numbers work': plain-language description of every calculation, for admins."""
    from pathlib import Path
    return {"markdown": (Path(__file__).resolve().parent.parent / "content" / "how_the_numbers_work.md").read_text(encoding="utf-8")}
