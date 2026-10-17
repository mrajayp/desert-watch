import secrets

from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, Response
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import auth
from ..db import get_db
from ..learning import record_events
from ..models import (ArticleAssessment, AuthSession, Comment, Event, Feedback, GapClaim, GapVote, Item, KeyEvent, Label,
                      OutletCategory, Suggestion, User, utcnow)

router = APIRouter(prefix="/api")


class SignupIn(BaseModel):
    email: str
    password: str
    display_name: str
    organisation: str | None = None
    note: str | None = None


_SIGNUPS: dict[str, list[float]] = {}


def _rate_limited(key: str, limit: int = 5, per_seconds: int = 3600) -> bool:
    import time
    now = time.time()
    hits = [t for t in _SIGNUPS.get(key, []) if now - t < per_seconds]
    _SIGNUPS[key] = hits + [now]
    return len(hits) >= limit


class LoginIn(BaseModel):
    email: str
    password: str


class InviteAcceptIn(BaseModel):
    token: str
    password: str
    display_name: str


class MePatch(BaseModel):
    ack_tracking_notice: bool | None = None
    display_name: str | None = None


class EventsIn(BaseModel):
    session_id: str | None = None
    events: list[dict]


def me_json(u: User) -> dict:
    return {"id": u.id, "email": u.email, "display_name": u.display_name, "role": u.role, "status": u.status or "active",
            "tracking_notice_ack": u.tracking_notice_ack_at is not None}


@router.post("/auth/login")
def login(body: LoginIn, response: Response, s: Session = Depends(get_db)):
    u = s.scalar(select(User).where(User.email == body.email.strip().lower()))
    if not u or not auth.verify_password(body.password, u.pw_hash):
        raise HTTPException(401, "Email or password is wrong.")
    status = u.status or "active"
    if status == "pending":
        raise HTTPException(403, "Your access request is waiting for an admin to approve it.")
    if status == "rejected" or status == "disabled" or not u.active:
        raise HTTPException(403, "This account is not active. Contact an admin.")
    auth.start_session(s, u, response)
    return me_json(u)


@router.post("/auth/signup")
def signup(body: SignupIn, request: Request, s: Session = Depends(get_db)):
    """Self-service access request. Creates a pending account; an admin approves it and picks
    the role. No session is started until approval."""
    ip = request.client.host if request.client else "?"
    if _rate_limited(ip):
        raise HTTPException(429, "Too many requests from this address. Try again later.")
    email = body.email.strip().lower()
    if "@" not in email or "." not in email.split("@")[-1] or len(email) > 200:
        raise HTTPException(400, "Enter a valid email address.")
    if s.scalar(select(User).where(User.email == email)):
        # same answer whether or not the email exists, so the form can't be used to probe accounts
        return {"ok": True, "message": "Request received. An admin will review it."}
    try:
        u = auth.create_user(s, email, body.password, body.display_name, role="viewer")
    except ValueError as e:
        raise HTTPException(400, str(e))
    u.status, u.active = "pending", True
    u.organisation = (body.organisation or "").strip()[:200] or None
    u.signup_note = (body.note or "").strip()[:2000] or None
    s.commit()
    return {"ok": True, "message": "Request received. An admin will review it."}


@router.post("/auth/logout")
def logout(response: Response, dw_session: str | None = Cookie(default=None), s: Session = Depends(get_db)):
    auth.end_session(s, dw_session, response)
    return {"ok": True}


@router.post("/auth/accept-invite")
def accept_invite(body: InviteAcceptIn, response: Response, s: Session = Depends(get_db)):
    try:
        u = auth.accept_invite(s, body.token, body.password, body.display_name)
        u.status = "active"
    except ValueError as e:
        raise HTTPException(400, str(e))
    s.commit()
    auth.start_session(s, u, response)
    return me_json(u)


@router.get("/me")
def me(u: User = Depends(auth.current_user)):
    return me_json(u)


@router.patch("/me")
def patch_me(body: MePatch, u: User = Depends(auth.current_user), s: Session = Depends(get_db)):
    u = s.merge(u)
    if body.ack_tracking_notice:
        u.tracking_notice_ack_at = utcnow()
    if body.display_name:
        u.display_name = body.display_name.strip()[:100]
    s.commit()
    return me_json(u)


@router.get("/me/export")
def export_me(u: User = Depends(auth.current_user), s: Session = Depends(get_db)):
    """Everything stored against this account."""
    def rows(model, col, value=None):
        return [{c.name: getattr(r, c.name) for c in model.__table__.columns}
                for r in s.scalars(select(model).where(col == (u.id if value is None else value)))]
    added = [{"id": i.id, "kind": i.kind, "url": i.url, "title": i.title, "created_at": i.created_at}
             for i in s.scalars(select(Item).where(Item.added_by == u.id))]
    return {"user": {**me_json(u), "organisation": u.organisation, "signup_note": u.signup_note, "created_at": u.created_at},
            "votes": rows(GapVote, GapVote.user_id), "claims": rows(GapClaim, GapClaim.user_id),
            "comments": rows(Comment, Comment.user_id), "assessments": rows(ArticleAssessment, ArticleAssessment.user_id),
            "suggestions": rows(Suggestion, Suggestion.user_id), "feedback": rows(Feedback, Feedback.user_id),
            "added_items": added, "key_events": rows(KeyEvent, KeyEvent.added_by),
            "outlet_labels": rows(OutletCategory, OutletCategory.set_by),
            "events": rows(Event, Event.pseudo_id, u.pseudo_id), "labels": rows(Label, Label.pseudo_id, u.pseudo_id)}


FREE_TEXT = ("note", "notes", "reason", "comment", "why", "body", "text")   # suggestion payload keys holding the user's own words


@router.delete("/me")
def delete_me(response: Response, u: User = Depends(auth.current_user), s: Session = Depends(get_db),
              dw_session: str | None = Cookie(default=None)):
    """Deletes the account and everything attributable to it. What the team still needs (votes, ratings,
    added articles, outlet labels, key events) is kept without the person or their words; labels are kept
    without the pseudo_id. Every session of the account ends."""
    u = s.merge(u)
    for e in s.scalars(select(Event).where(Event.pseudo_id == u.pseudo_id)):
        s.delete(e)
    for lb in s.scalars(select(Label).where(Label.pseudo_id == u.pseudo_id)):
        lb.pseudo_id = None
    for c in s.scalars(select(Comment).where(Comment.user_id == u.id)):
        c.body, c.deleted = "", True
    for v in s.scalars(select(GapVote).where(GapVote.user_id == u.id)):
        v.note = None
    for a in s.scalars(select(ArticleAssessment).where(ArticleAssessment.user_id == u.id)):
        a.note = None
    for c in s.scalars(select(GapClaim).where(GapClaim.user_id == u.id)):
        s.delete(c)
    for sug in s.scalars(select(Suggestion).where(Suggestion.user_id == u.id)):
        sug.user_id = None
        sug.payload = {k: v for k, v in (sug.payload or {}).items() if k not in FREE_TEXT}
    for f in s.scalars(select(Feedback).where(Feedback.user_id == u.id)):
        f.user_id, f.body = None, ""
    for it in s.scalars(select(Item).where(Item.added_by == u.id)):
        if it.kind == "suggestion":     # a flagged gap: its title was the person's own note
            it.title = "Gap flagged"
        it.added_by = None
    for oc in s.scalars(select(OutletCategory).where(OutletCategory.set_by == u.id)):
        oc.set_by = None
    for ke in s.scalars(select(KeyEvent).where(KeyEvent.added_by == u.id)):
        ke.added_by = None
    auth.end_session(s, dw_session, response)
    for sess in s.scalars(select(AuthSession).where(AuthSession.user_id == u.id)):
        s.delete(sess)
    u.active, u.email, u.display_name, u.pw_hash = False, f"deleted-{u.id}@invalid", "Deleted user", "!"
    u.organisation, u.signup_note, u.status = None, None, "disabled"
    u.pseudo_id = secrets.token_hex(8)
    s.commit()
    return {"ok": True}


@router.post("/events")
def post_events(body: EventsIn, u: User = Depends(auth.current_user), s: Session = Depends(get_db)):
    return {"stored": record_events(s, u, body.session_id, body.events)}
