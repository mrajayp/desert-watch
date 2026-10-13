from datetime import date, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import auth
from ..db import get_db
from ..fetch_meta import FetchError, fetch_meta
from ..ingest import domain_of, load_rules, store_article
from ..models import ArticleAssessment, Comment, Event, Item, ItemRegion, ItemTheme, User, utcnow
from .common import country_or_404, hydrate_items, items_query, region_or_404, theme_or_404

router = APIRouter(prefix="/api")


def _parse_date(v: str | None) -> datetime:
    if v:
        for fmt in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S.%f%z", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%d"):
            try:
                d = datetime.strptime(v[:32], fmt)
                return d.replace(tzinfo=None) if d.tzinfo is None else d.astimezone().replace(tzinfo=None)
            except ValueError:
                continue
    return utcnow()


def add_article_core(s: Session, u: User, country_id: int, url: str, *, theme_ids: list[int],
                     region_ids: list[int], title: str | None = None, lang: str | None = None,
                     published: str | None = None) -> Item:
    """User-added coverage. Metadata is fetched server-side unless provided."""
    meta = {}
    if not title:
        try:
            meta = fetch_meta(url)
        except FetchError as e:
            raise HTTPException(400, str(e))
        except Exception:  # noqa: BLE001
            raise HTTPException(400, "Could not read that page. Add a title manually.")
    rules = load_rules(s, country_id)
    item, created = store_article(
        s, country_id, rules, url=meta.get("final_url") or url, title=title or meta.get("title") or url,
        snippet=meta.get("description"), published_at=_parse_date(published or meta.get("published")),
        source_key="user", lang=lang or meta.get("lang"), outlet_name=meta.get("site_name"),
        added_by=u.id, forced_theme_ids=tuple(theme_ids), extra={"user_themes": theme_ids})
    for rid in region_ids:
        if not s.get(ItemRegion, (item.id, rid)):
            s.add(ItemRegion(item_id=item.id, region_id=rid, method="user"))
    for tid in theme_ids:
        it = s.get(ItemTheme, (item.id, tid))
        if it:
            it.active, it.method = True, "user"
    if not created and item.added_by is None:
        item.extra = {**(item.extra or {}), "confirmed_by_user": u.id}
    s.add(Event(pseudo_id=u.pseudo_id, type="add_article", object_type="item", object_key=str(item.id),
                context={"theme_ids": theme_ids, "region_ids": region_ids, "created": created}))
    s.flush()
    return item


class PreviewIn(BaseModel):
    url: str


@router.post("/items/preview")
def preview(body: PreviewIn, _: User = Depends(auth.current_user)):
    try:
        m = fetch_meta(body.url)
    except FetchError as e:
        raise HTTPException(400, str(e))
    except Exception:  # noqa: BLE001
        raise HTTPException(400, "Could not read that page.")
    return {**m, "domain": domain_of(m["final_url"])}


class AddIn(BaseModel):
    country: str = "LY"
    url: str
    title: str | None = None
    lang: str | None = None
    published: str | None = None
    theme_ids: list[int] = Field(default_factory=list)
    region_ids: list[int] = Field(default_factory=list)


@router.post("/items")
def add_item(body: AddIn, s: Session = Depends(get_db), u: User = Depends(auth.current_user)):
    c = country_or_404(s, body.country)
    for t in body.theme_ids:
        theme_or_404(s, t)
    for r in body.region_ids:
        region_or_404(s, r)
    item = add_article_core(s, u, c.id, body.url, theme_ids=body.theme_ids, region_ids=body.region_ids,
                            title=body.title, lang=body.lang, published=body.published)
    s.commit()
    return hydrate_items(s, [item])[0]


@router.get("/items")
def list_items(country: str = "LY", theme_id: int | None = None, region_id: int | None = None,
               outlet_id: int | None = None, q: str | None = None, days: int = 28, kind: str = "article",
               limit: int = 50, offset: int = 0, s: Session = Depends(get_db), _: User = Depends(auth.current_user)):
    c = country_or_404(s, country)
    region = region_or_404(s, region_id) if region_id else None
    end = utcnow() + timedelta(days=1)
    total, rows = items_query(s, country_id=c.id, theme_id=theme_id, region=region, start=end - timedelta(days=days + 1),
                              end=end, kinds=(kind,), limit=min(limit, 200), offset=offset, outlet_id=outlet_id, q=q)
    return {"total": total, "items": hydrate_items(s, rows)}


@router.get("/items/{item_id}")
def item_detail(item_id: int, s: Session = Depends(get_db), u: User = Depends(auth.current_user)):
    it = s.get(Item, item_id)
    if not it:
        raise HTTPException(404, "Unknown item")
    out = hydrate_items(s, [it])[0]
    rows = s.scalars(select(ArticleAssessment).where(ArticleAssessment.item_id == item_id)).all()
    mine = next((a for a in rows if a.user_id == u.id), None)
    avg = lambda f: round(sum(getattr(a, f) for a in rows) / len(rows), 2) if rows else None  # noqa: E731
    out["assessments"] = {"count": len(rows), "accuracy": avg("accuracy"), "depth": avg("depth"),
                          "local_sourcing": avg("local_sourcing"),
                          "mine": {"accuracy": mine.accuracy, "depth": mine.depth, "local_sourcing": mine.local_sourcing,
                                   "note": mine.note} if mine else None}
    out["comment_count"] = s.scalar(select(func.count(Comment.id)).where(
        Comment.object_type == "item", Comment.object_key == str(item_id), Comment.deleted.is_(False)))
    return out


class CorrectionIn(BaseModel):
    theme_id: int | None = None
    theme_relevant: bool | None = None      # False = "not about this theme", True = "add this theme"
    region_id: int | None = None
    region_relevant: bool | None = None
    item_relevant: bool | None = None       # False = off-topic / junk for this country


@router.post("/items/{item_id}/correction")
def correct(item_id: int, body: CorrectionIn, s: Session = Depends(get_db), u: User = Depends(auth.current_user)):
    it = s.get(Item, item_id)
    if not it:
        raise HTTPException(404, "Unknown item")
    ctx = body.model_dump(exclude_none=True)
    if body.theme_id is not None and body.theme_relevant is not None:
        theme_or_404(s, body.theme_id)
        link = s.get(ItemTheme, (item_id, body.theme_id))
        if link:
            link.active, link.method = body.theme_relevant, "user"
        elif body.theme_relevant:
            s.add(ItemTheme(item_id=item_id, theme_id=body.theme_id, method="user"))
        ctx["label_type"] = "theme_relevance"
    if body.region_id is not None and body.region_relevant is not None:
        region_or_404(s, body.region_id)
        link = s.get(ItemRegion, (item_id, body.region_id))
        if link:
            link.active, link.method = body.region_relevant, "user"
        elif body.region_relevant:
            s.add(ItemRegion(item_id=item_id, region_id=body.region_id, method="user"))
        ctx.setdefault("label_type", "region")
    if body.item_relevant is not None:
        it.relevant = body.item_relevant
        it.extra = {**(it.extra or {}), "user_relevance": body.item_relevant}
        ctx.setdefault("label_type", "theme_relevance")
    ctx["title"] = (it.title or "")[:300]
    ctx["lang"] = it.lang
    s.add(Event(pseudo_id=u.pseudo_id, type="correction", object_type="item", object_key=str(item_id), context=ctx))
    s.commit()
    return hydrate_items(s, [it])[0]


class AssessIn(BaseModel):
    accuracy: int = Field(ge=1, le=3)
    depth: int = Field(ge=1, le=3)
    local_sourcing: int = Field(ge=1, le=3)
    note: str | None = Field(default=None, max_length=2000)


@router.post("/items/{item_id}/assessment")
def assess(item_id: int, body: AssessIn, s: Session = Depends(get_db), u: User = Depends(auth.current_user)):
    if not s.get(Item, item_id):
        raise HTTPException(404, "Unknown item")
    a = s.scalar(select(ArticleAssessment).where(ArticleAssessment.item_id == item_id,
                                                 ArticleAssessment.user_id == u.id))
    if not a:
        a = ArticleAssessment(item_id=item_id, user_id=u.id, accuracy=1, depth=1, local_sourcing=1)
        s.add(a)
    a.accuracy, a.depth, a.local_sourcing, a.note, a.created_at = (body.accuracy, body.depth, body.local_sourcing,
                                                                   body.note, utcnow())
    s.commit()
    return {"ok": True}
