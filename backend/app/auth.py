"""Invite-only accounts: scrypt password hashes, opaque session cookie (hash stored)."""
import hashlib
import hmac
import secrets
from datetime import timedelta

from fastapi import Cookie, Depends, HTTPException, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import settings
from .db import get_db
from .models import AuthSession, Invite, User, utcnow

COOKIE = "dw_session"
SESSION_DAYS = 14


def hash_password(pw: str) -> str:
    salt = secrets.token_bytes(16)
    dk = hashlib.scrypt(pw.encode(), salt=salt, n=2**14, r=8, p=1, dklen=32)
    return f"scrypt$16384$8$1${salt.hex()}${dk.hex()}"


def verify_password(pw: str, stored: str) -> bool:
    try:
        _, n, r, p, salt, dk = stored.split("$")
        got = hashlib.scrypt(pw.encode(), salt=bytes.fromhex(salt), n=int(n), r=int(r), p=int(p), dklen=32)
        return hmac.compare_digest(got.hex(), dk)
    except Exception:  # noqa: BLE001
        return False


def sha(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def create_user(s: Session, email: str, password: str, display_name: str, role: str = "journalist") -> User:
    if len(password) < 10:
        raise ValueError("Password must be at least 10 characters.")
    u = User(email=email.strip().lower(), display_name=display_name.strip()[:100] or email.split("@")[0],
             pw_hash=hash_password(password), role=role, pseudo_id=secrets.token_hex(8))
    s.add(u)
    s.flush()
    return u


def create_invite(s: Session, email: str, role: str, created_by: int | None, days: int = 7) -> str:
    token = secrets.token_urlsafe(24)
    s.add(Invite(token_hash=sha(token), email=email.strip().lower(), role=role, created_by=created_by,
                 expires_at=utcnow() + timedelta(days=days)))
    s.flush()
    return token


def start_session(s: Session, user: User, response: Response) -> None:
    token = secrets.token_urlsafe(32)
    s.add(AuthSession(token_hash=sha(token), user_id=user.id, expires_at=utcnow() + timedelta(days=SESSION_DAYS)))
    s.commit()
    response.set_cookie(COOKIE, token, httponly=True, samesite="lax", secure=settings.COOKIE_SECURE,
                        max_age=SESSION_DAYS * 86400, path="/")


def end_session(s: Session, token: str | None, response: Response) -> None:
    if token:
        sess = s.get(AuthSession, sha(token))
        if sess:
            s.delete(sess)
            s.commit()
    response.delete_cookie(COOKIE, path="/")


def current_user(dw_session: str | None = Cookie(default=None), s: Session = Depends(get_db)) -> User:
    if not dw_session:
        raise HTTPException(401, "Not signed in")
    sess = s.get(AuthSession, sha(dw_session))
    if not sess or sess.expires_at < utcnow():
        raise HTTPException(401, "Session expired")
    u = s.get(User, sess.user_id)
    if not u or not u.active:
        raise HTTPException(401, "Account disabled")
    return u


def require_admin(u: User = Depends(current_user)) -> User:
    if u.role != "admin":
        raise HTTPException(403, "Admins only")
    return u


def accept_invite(s: Session, token: str, password: str, display_name: str) -> User:
    inv = s.scalar(select(Invite).where(Invite.token_hash == sha(token)))
    if not inv or inv.used_at or inv.expires_at < utcnow():
        raise ValueError("Invite is invalid or expired.")
    if s.scalar(select(User).where(User.email == inv.email)):
        raise ValueError("An account with this email already exists.")
    u = create_user(s, inv.email, password, display_name, inv.role)
    inv.used_at = utcnow()
    return u
