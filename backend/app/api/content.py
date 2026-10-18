"""Long-form content pages: GET /api/content/{name} -> {"markdown": ...} in the request's language.

The allow-list says who may read each page. `help` is for every signed-in user; the full method notes
(`how_the_numbers_work`) stay with admins. Each page has an Arabic twin next to it (content/<name>.ar.md,
chosen by i18n.content_path); tests/test_i18n.py fails when one is missing. Anything not listed is 404,
so the route can never read another file by name."""
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException

from .. import auth
from ..i18n import content_path, tr
from ..models import User

router = APIRouter(prefix="/api")

CONTENT_DIR = Path(__file__).resolve().parent.parent / "content"
# name -> the role it takes ("user": any signed-in account, "admin": admins only)
PAGES = {"help": "user", "how_the_numbers_work": "admin"}


@router.get("/content/{name}")
def content(name: str, u: User = Depends(auth.current_user)):
    who = PAGES.get(name)
    if who is None:
        raise HTTPException(404, tr("Unknown page"))
    if who == "admin" and u.role != "admin":
        raise HTTPException(403, tr("Admins only"))
    return {"name": name, "markdown": content_path(CONTENT_DIR, name).read_text(encoding="utf-8")}
