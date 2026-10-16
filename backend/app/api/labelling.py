"""Labelling for the theme model: full theme-set labels on an article, the review queue that picks
what to label next, and the model registry for admins. No scikit-learn here: scores come from
item_theme and from item.extra['model'], which classify-items writes."""
import random
import re
from datetime import timedelta

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import exists, func, not_, select
from sqlalchemy.orm import Session

from .. import auth
from ..classify import classify_themes
from ..db import get_db
from ..ml import labels as L
from ..ml import registry
from ..models import Event, Item, ItemTheme, Label, ModelRegistry, Theme, User, utcnow
from ..textnorm import term_variants
from .common import country_or_404, duplicate_cluster, hydrate_items

router = APIRouter(prefix="/api")

QUEUE_DAYS = 120
WOMEN_WORDS = ["women", "woman", "girl", "نساء", "امرأة", "فتاة", "سيدة", "المرأة"]
GENERIC_TERMS = ["minister", "وزير", "killed", "مقتل", "المياه"]
GENERIC = {v for t in GENERIC_TERMS for v in term_variants(t)}
_WOMEN_RE = re.compile("|".join(map(re.escape, WOMEN_WORDS)), re.I)
_GENERIC_RE = re.compile("|".join(map(re.escape, GENERIC_TERMS)), re.I)


# ---------------------------------------------------------------- full theme-set labels
class LabelsIn(BaseModel):
    themes: list[int] = Field(default_factory=list)  # every theme the article is about; the rest are "no"
    libya: bool                                      # is it about Libya at all


def _set_link(s: Session, item_id: int, theme: Theme, on: bool) -> None:
    lk = s.get(ItemTheme, (item_id, theme.id))
    if lk is None:
        s.add(ItemTheme(item_id=item_id, theme_id=theme.id, method="user", active=on, theme_version=theme.version))
        return
    if lk.method != "user":
        lk.evidence = {**(lk.evidence or {}), "was": lk.method}
    lk.method, lk.active = "user", on


@router.post("/items/{item_id}/labels")
def label_item(item_id: int, body: LabelsIn, s: Session = Depends(get_db), u: User = Depends(auth.require_contributor)):
    it = s.get(Item, item_id)
    if not it:
        raise HTTPException(404, "Unknown item")
    active = s.scalars(select(Theme).where(Theme.active.is_(True)).order_by(Theme.id)).all()
    by_id = {t.id: t for t in active}
    if any(t not in by_id for t in body.themes):
        raise HTTPException(400, "Unknown or switched-off theme")
    chosen = set(body.themes) if body.libya else set()  # not about the country: no theme counts
    cluster = duplicate_cluster(s, it)
    for x in cluster:
        for t in active:
            _set_link(s, x.id, t, t.id in chosen)
        x.relevant = body.libya
        x.extra = {**(x.extra or {}), "user_relevance": body.libya}
    s.add(Event(pseudo_id=u.pseudo_id, type="correction", object_type="item", object_key=str(item_id),
                context={"label_type": "theme_set", "themes": [by_id[t].slug for t in sorted(chosen)],
                         "libya": body.libya, "of": [t.slug for t in active], "title": (it.title or "")[:300],
                         "lang": it.lang, "copies": len(cluster)}))
    s.commit()
    return hydrate_items(s, [it])[0]


# ---------------------------------------------------------------- review queue
def _generic_only(text: str, rules) -> str | None:
    """The generic term when every rule hit on this text is that one generic word, else None."""
    hits = classify_themes(text, rules)
    terms = {h for hs in hits.values() for h in hs}
    if hits and all(len(hs) == 1 for hs in hits.values()) and len(terms) == 1 and terms <= GENERIC:
        return next(iter(terms))
    return None


@router.get("/review-queue")
def review_queue(n: int = 10, country: str = "LY", s: Session = Depends(get_db),
                 u: User = Depends(auth.require_contributor)):
    """Unlabelled recent articles worth a person's look: where the model is least sure, possible
    gender stories the rules missed, and links that rest on one generic word."""
    from ..ingest import load_rules
    n = max(1, min(n, 50))
    c = country_or_404(s, country)
    live = registry.active(s)
    done = L.labelled_item_ids(s)
    themes = s.scalars(select(Theme).where(Theme.active.is_(True))).all()
    # one pass over the window (each extra scan of item costs about half a second on the production data)
    unsure = func.json_extract(Item.extra, "$.model.u")
    rows = [r for r in s.execute(select(Item.id, Item.title, Item.snippet, unsure).where(
        Item.country_id == c.id, Item.kind == "article", Item.relevant.is_(True), Item.duplicate_of.is_(None),
        Item.published_at >= utcnow() - timedelta(days=QUEUE_DAYS),
        not_(exists().where(ItemTheme.item_id == Item.id, ItemTheme.method == "user")))
        .order_by(Item.published_at.desc())).all() if r[0] not in done]
    text = {r[0]: f"{r[1] or ''} {r[2] or ''}" for r in rows}

    def linked(ids: list[int], *conds) -> set[int]:
        return set(s.scalars(select(ItemTheme.item_id).where(ItemTheme.item_id.in_(ids), ItemTheme.active.is_(True),
                                                             *conds))) if ids else set()

    queues: list[tuple[str, list[int]]] = []
    if live:  # u: how close the score nearest to its bar is (1 = right at it); shuffled within the top 3n
        top = [r[0] for r in sorted((r for r in rows if r[3]), key=lambda r: -r[3])[:n * 3]]
        queues.append(("uncertain", random.sample(top, min(n, len(top)))))
    women = [r[0] for r in rows if _WOMEN_RE.search(text[r[0]])][:n * 20]
    has_gender = linked(women, ItemTheme.theme_id.in_([t.id for t in themes if t.group == "gender"]))
    queues.append(("gender_candidate", [i for i in women if i not in has_gender][:n]))
    generic = [r for r in rows if _GENERIC_RE.search(text[r[0]])][:300]
    has_rule = linked([r[0] for r in generic], ItemTheme.method == "rule")
    rules = load_rules(s, c.id).themes
    generic_terms: dict[int, str] = {}
    for iid, title, snip, _ in generic:
        term = _generic_only(" ".join(x for x in (title, snip) if x), rules) if iid in has_rule else None
        if term:
            generic_terms[iid] = term
        if len(generic_terms) >= n:
            break
    queues.append(("generic_term", list(generic_terms)))

    picks: dict[int, str] = {}
    for i in range(n):  # take turns between the queues
        for reason, ids in queues:
            if i < len(ids) and ids[i] not in picks and len(picks) < n:
                picks[ids[i]] = reason
    rows = {r.id: r for r in s.scalars(select(Item).where(Item.id.in_(list(picks))))}
    out = hydrate_items(s, [rows[i] for i in picks if i in rows])
    slug2id = {t.slug: t.id for t in themes}
    for d in out:
        mark = (rows[d["id"]].extra or {}).get("model") or {}
        scores = {str(x["theme_id"]): x["score"] for x in d["theme_detail"] if x["score"] is not None}
        scores |= {str(slug2id[sl]): p for sl, p in (mark.get("near") or {}).items() if sl in slug2id}
        d.update(reason=picks[d["id"]], scores=scores, uncertainty=mark.get("u"), closest=mark.get("ut"),
                 generic_term=generic_terms.get(d["id"]))
    return {"items": out, "model": live.version if live else None, "labelled": len(done)}


# ---------------------------------------------------------------- model registry (admin)
@router.get("/admin/models")
def models(s: Session = Depends(get_db), _: User = Depends(auth.require_admin)):
    themes = s.scalars(select(Theme).where(Theme.active.is_(True)).order_by(Theme.id)).all()
    vectors = L.item_vectors(s, themes)
    stats = L.theme_stats(vectors, themes)
    people = L.theme_stats(vectors, themes, people_only=True)
    live = registry.active(s)
    m = (live.metrics or {}).get("themes", {}) if live else {}
    rows = s.scalars(select(ModelRegistry).order_by(ModelRegistry.id.desc())).all()
    by = s.execute(select(Label.origin, Label.label_type, func.count()).group_by(Label.origin, Label.label_type)).all()
    return {
        "active": live.version if live else None,
        "pinned": registry.is_pinned(live),
        "models": [registry.row_json(r) for r in rows],
        "labels": {"by_origin": {o: sum(n for oo, _, n in by if oo == o) for o in {o for o, _, _ in by}},
                   "by_type": {t: sum(n for _, tt, n in by if tt == t) for t in {t for _, t, _ in by}},
                   "by_origin_and_type": [{"origin": o, "label_type": t, "n": n} for o, t, n in by]},
        "themes": [{"id": t.id, "slug": t.slug, "group": t.group, **stats[t.slug],
                    "people_labelled": people[t.slug]["labelled"], "people_positives": people[t.slug]["positives"],
                    "threshold": (live.thresholds or {}).get(t.slug) if live else None,
                    # a gate opened on silver labels (bundles without the people block) does nothing
                    "gate": (bool(m[t.slug]["gate"]) and "people" in m[t.slug]) if "gate" in m.get(t.slug, {}) else None}
                   for t in themes],
        "links": {"model": s.scalar(select(func.count()).where(ItemTheme.method == "model", ItemTheme.active.is_(True))),
                  "vetoed": s.scalar(select(func.count()).where(ItemTheme.method == "rule", ItemTheme.active.is_(False),
                                                                func.json_extract(ItemTheme.evidence, "$.veto").is_not(None)))},
    }


@router.post("/admin/models/{version}/activate")
def activate_model(version: str, bg: BackgroundTasks, pin: bool = True, s: Session = Depends(get_db),
                   _: User = Depends(auth.require_admin)):
    """Make a version live (also how to roll back), then re-score every article with it. A version made
    live here is pinned: nightly retraining keeps new versions inactive until an admin activates one.
    pin=false on the live version lets nightly retraining replace it again (no re-score)."""
    from ..jobs import JOBS
    was = registry.active(s)
    try:
        row = registry.activate(s, version, by_hand=pin)
    except ValueError:
        raise HTTPException(404, "Unknown model version")
    except FileNotFoundError:
        raise HTTPException(409, "This version's file was removed to save space. Pick a newer one.")
    s.commit()
    if not (was and was.id == row.id):
        bg.add_task(JOBS["classify_all"])
    return registry.row_json(row)
