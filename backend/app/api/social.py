"""Comments (threaded, on gaps / items / themes / outlets)."""
import re

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from .. import auth
from ..db import get_db
from ..models import Comment, Event, User
from ..i18n import tr

router = APIRouter(prefix="/api")
OBJECT_TYPES = {"gap", "item", "theme", "outlet"}
TAGS = {None, "agree", "disagree", "missing_context", "source_tip", "safety"}
PRIVATE_TAG = "safety"   # seen only by its author and admins, and replies to it only by those people and the replier


class CommentIn(BaseModel):
    object_type: str
    object_key: str = Field(max_length=60)
    body: str = Field(min_length=1, max_length=5000)
    parent_id: int | None = None
    tag: str | None = None


class CommentPatch(BaseModel):
    resolved: bool | None = None
    body: str | None = Field(default=None, max_length=5000)


def can_see(c: Comment, me: User, parents: dict) -> bool:
    """Safety comments (and the replies under them) are hidden from everyone but the people involved and
    admins. `parents` maps id -> Comment for the thread, so the root can be found."""
    if me.role == "admin":
        return True
    root, seen = c, set()
    while root.parent_id and root.parent_id in parents and root.id not in seen:
        seen.add(root.id)
        root = parents[root.parent_id]
    if root.tag != PRIVATE_TAG:
        return True
    return me.id in (c.user_id, root.user_id)


def counted():
    """SQL condition for comments that count in public tallies: not a safety comment or a direct reply to one."""
    from sqlalchemy import or_
    from sqlalchemy.orm import aliased
    parent = aliased(Comment)
    private = select(parent.id).where(parent.tag == PRIVATE_TAG)
    return and_(Comment.deleted.is_(False), or_(Comment.tag.is_(None), Comment.tag != PRIVATE_TAG),
                or_(Comment.parent_id.is_(None), Comment.parent_id.not_in(private)))


def _json(c: Comment, names: dict, me: User) -> dict:
    return {"id": c.id, "parent_id": c.parent_id, "user": names.get(c.user_id, "?") if not c.deleted else None,
            "mine": c.user_id == me.id, "body": c.body if not c.deleted else "", "tag": c.tag,
            "resolved": c.resolved, "deleted": c.deleted, "at": c.created_at.isoformat(),
            "mentions": re.findall(r"@([\w.\-]+)", c.body or "")}


@router.get("/comments")
def list_comments(object_type: str, object_key: str, s: Session = Depends(get_db), u: User = Depends(auth.current_user)):
    rows = s.scalars(select(Comment).where(Comment.object_type == object_type, Comment.object_key == object_key)
                     .order_by(Comment.created_at)).all()
    names = {x.id: x.display_name for x in s.scalars(select(User))}
    parents = {c.id: c for c in rows}
    return [_json(c, names, u) for c in rows if can_see(c, u, parents)]


@router.post("/comments")
def add_comment(body: CommentIn, s: Session = Depends(get_db), u: User = Depends(auth.require_contributor)):
    if body.object_type not in OBJECT_TYPES or body.tag not in TAGS:
        raise HTTPException(400, tr("Unknown object type or tag"))
    if body.parent_id:
        p = s.get(Comment, body.parent_id)
        thread = {x.id: x for x in s.scalars(select(Comment).where(Comment.object_key == body.object_key))}
        if not p or p.object_key != body.object_key or not can_see(p, u, thread):
            raise HTTPException(400, tr("Bad parent"))
    c = Comment(user_id=u.id, object_type=body.object_type, object_key=body.object_key, body=body.body.strip(),
                parent_id=body.parent_id, tag=body.tag)
    s.add(c)
    s.add(Event(pseudo_id=u.pseudo_id, type="comment", object_type=body.object_type, object_key=body.object_key,
                context={"reply": bool(body.parent_id)} if body.tag == PRIVATE_TAG else
                {"tag": body.tag, "reply": bool(body.parent_id)}))
    s.commit()
    return _json(c, {u.id: u.display_name}, u)


@router.patch("/comments/{cid}")
def patch_comment(cid: int, body: CommentPatch, s: Session = Depends(get_db), u: User = Depends(auth.current_user)):
    c = s.get(Comment, cid)
    if not c:
        raise HTTPException(404, tr("Unknown comment"))
    if body.body is not None:
        if c.user_id != u.id:
            raise HTTPException(403, tr("Only the author can edit"))
        c.body = body.body
    if body.resolved is not None:
        if c.user_id != u.id and u.role != "admin":
            raise HTTPException(403, tr("Only the author or an admin can resolve a comment"))
        c.resolved = body.resolved
    s.commit()
    return _json(c, {u.id: u.display_name}, u)


@router.delete("/comments/{cid}")
def delete_comment(cid: int, s: Session = Depends(get_db), u: User = Depends(auth.current_user)):
    c = s.get(Comment, cid)
    if not c:
        raise HTTPException(404, tr("Unknown comment"))
    if c.user_id != u.id and u.role != "admin":
        raise HTTPException(403, tr("Not allowed"))
    c.deleted, c.body = True, ""
    s.commit()
    return {"ok": True}


# ---------------------------------------------------------------- page feedback
class FeedbackIn(BaseModel):
    page: str = Field(min_length=1, max_length=80)
    kind: str
    body: str = Field(min_length=3, max_length=4000)


@router.post("/feedback")
def leave_feedback(body: FeedbackIn, s: Session = Depends(get_db), u: User = Depends(auth.current_user)):
    from ..models import Feedback
    if body.kind not in ("suggestion", "question", "problem"):
        raise HTTPException(400, tr("Kind must be suggestion, question or problem"))
    f = Feedback(user_id=u.id, page=body.page, kind=body.kind, body=body.body.strip())
    s.add(f)
    s.commit()
    return {"ok": True, "id": f.id}


@router.get("/feedback/mine")
def my_feedback(page: str | None = None, s: Session = Depends(get_db), u: User = Depends(auth.current_user)):
    from ..models import Feedback
    q = select(Feedback).where(Feedback.user_id == u.id).order_by(Feedback.created_at.desc())
    if page:
        q = q.where(Feedback.page == page)
    return [{"id": f.id, "page": f.page, "kind": f.kind, "body": f.body, "status": f.status, "reply": f.reply,
             "at": f.created_at.isoformat()} for f in s.scalars(q.limit(50))]
