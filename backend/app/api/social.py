"""Comments (threaded, on gaps / items / themes / outlets)."""
import re

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import auth
from ..db import get_db
from ..models import Comment, Event, User

router = APIRouter(prefix="/api")
OBJECT_TYPES = {"gap", "item", "theme", "outlet"}
TAGS = {None, "agree", "disagree", "missing_context", "source_tip", "safety"}


class CommentIn(BaseModel):
    object_type: str
    object_key: str = Field(max_length=60)
    body: str = Field(min_length=1, max_length=5000)
    parent_id: int | None = None
    tag: str | None = None


class CommentPatch(BaseModel):
    resolved: bool | None = None
    body: str | None = Field(default=None, max_length=5000)


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
    return [_json(c, names, u) for c in rows]


@router.post("/comments")
def add_comment(body: CommentIn, s: Session = Depends(get_db), u: User = Depends(auth.current_user)):
    if body.object_type not in OBJECT_TYPES or body.tag not in TAGS:
        raise HTTPException(400, "Unknown object type or tag")
    if body.parent_id:
        p = s.get(Comment, body.parent_id)
        if not p or p.object_key != body.object_key:
            raise HTTPException(400, "Bad parent")
    c = Comment(user_id=u.id, object_type=body.object_type, object_key=body.object_key, body=body.body.strip(),
                parent_id=body.parent_id, tag=body.tag)
    s.add(c)
    s.add(Event(pseudo_id=u.pseudo_id, type="comment", object_type=body.object_type, object_key=body.object_key,
                context={"tag": body.tag, "reply": bool(body.parent_id)}))
    s.commit()
    return _json(c, {u.id: u.display_name}, u)


@router.patch("/comments/{cid}")
def patch_comment(cid: int, body: CommentPatch, s: Session = Depends(get_db), u: User = Depends(auth.current_user)):
    c = s.get(Comment, cid)
    if not c:
        raise HTTPException(404, "Unknown comment")
    if body.body is not None:
        if c.user_id != u.id:
            raise HTTPException(403, "Only the author can edit")
        c.body = body.body
    if body.resolved is not None:
        c.resolved = body.resolved
    s.commit()
    return _json(c, {u.id: u.display_name}, u)


@router.delete("/comments/{cid}")
def delete_comment(cid: int, s: Session = Depends(get_db), u: User = Depends(auth.current_user)):
    c = s.get(Comment, cid)
    if not c:
        raise HTTPException(404, "Unknown comment")
    if c.user_id != u.id and u.role != "admin":
        raise HTTPException(403, "Not allowed")
    c.deleted, c.body = True, ""
    s.commit()
    return {"ok": True}
