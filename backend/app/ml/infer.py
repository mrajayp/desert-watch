"""Scoring articles with a theme model bundle and writing the result to item_theme.

Decision per theme:
  non-gender ('or')  counted = rule OR p >= t. The model adds links (method 'model') and takes back
                     the ones it added when p falls below t. Rule and user links are never touched.
  gender ('and')     the rules decide. Once the theme passed its label gate (bundle 'gates', decided
                     on people's labels only: bundle 'gates_from' == 'people') the model may veto a
                     rule link (active False, evidence.veto = p). Before that it only writes scores.
People's links (method 'user') are never changed, also when a person labels an article while a
batch is being scored. Imports numpy / scikit-learn (through features)."""
from collections import Counter
from datetime import datetime

import joblib
import numpy as np
from sqlalchemy import func, or_, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..models import Item, ItemTheme, Theme
from .features import Features, item_text

BATCH = 1000
NEAR = 0.5  # non-gender p at or above NEAR * t (and below t) is kept on the item as a near miss, for the review queue


def _sigmoid(z):
    return 1.0 / (1.0 + np.exp(-np.clip(z, -50, 50)))


def load_bundle(path) -> dict:
    return joblib.load(path)


class ThemeModel:
    def __init__(self, b: dict):
        self.b = b
        self.version = b.get("version")
        self.themes = list(b["themes"])
        k = len(self.themes)
        self.features = Features.from_bundle(b)
        self.coef, self.intercept = b["coef"], b["intercept"]
        self.has_base = np.asarray(b["has_model"], dtype=bool)
        self.small_coef, self.small_intercept = b.get("small_coef"), b.get("small_intercept")
        self.small_has = np.asarray(b.get("small_has", np.zeros(k, dtype=bool)), dtype=bool)
        self.a = float(b.get("blend_a", 0.5))
        self.policy = [b["policy"][t] for t in self.themes]
        self.th = np.array([b.get("thresholds", {}).get(t, 0.5) for t in self.themes], dtype=np.float64)
        # a gate counts only when it was decided on people's labels (bundles from before 2026-10-16
        # opened gates on the silver review labels: their veto stays off)
        people = b.get("gates_from") == "people"
        self.veto = np.array([people and bool(b.get("gates", {}).get(t)) for t in self.themes])

    @classmethod
    def load(cls, path) -> "ThemeModel":
        return cls(load_bundle(path))

    @property
    def has(self) -> np.ndarray:
        return self.has_base | self.small_has

    def vectorise(self, texts: list[str]):
        return self.features.transform(texts)

    def base_proba(self, X) -> np.ndarray:
        return _sigmoid(np.asarray(X @ self.coef.T) + self.intercept)

    def small_proba(self, X, coef=None, intercept=None) -> np.ndarray:
        coef = self.small_coef if coef is None else coef
        intercept = self.small_intercept if intercept is None else intercept
        return _sigmoid(np.asarray(X @ coef.T) + intercept)

    def blend(self, pb: np.ndarray, ps: np.ndarray | None, small_has: np.ndarray | None = None) -> np.ndarray:
        small_has = self.small_has if small_has is None else small_has
        p = pb if ps is None else np.where(small_has, (1 - self.a) * pb + self.a * ps, pb)
        p = np.array(p, dtype=np.float64)
        p[:, ~(self.has_base | small_has)] = 0.0
        return p

    def proba_x(self, X) -> np.ndarray:
        ps = self.small_proba(X) if self.small_coef is not None and self.small_has.any() else None
        return self.blend(self.base_proba(X), ps)

    def proba(self, texts: list[str]) -> np.ndarray:
        return self.proba_x(self.vectorise(texts))


def closeness(p: np.ndarray, t: np.ndarray, mask: np.ndarray | None = None) -> np.ndarray:
    """Binary entropy per cell after rescaling so each theme's threshold sits at 0.5: 1 at the
    threshold, near 0 far from it. mask: which cells count (where the model's answer can change a link)."""
    t = np.clip(t, 1e-3, 1 - 1e-3)
    q = np.where(p < t, p / (2 * t), 0.5 + (p - t) / (2 * (1 - t)))
    q = np.clip(q, 1e-6, 1 - 1e-6)
    h = -(q * np.log2(q) + (1 - q) * np.log2(1 - q))
    return h if mask is None else h * mask


def apply_link(s: Session, item_id: int, theme_id: int, theme_version: int, lk: ItemTheme | None, p: float, t: float,
               policy: str, veto_on: bool, version: str | None) -> str:
    """Write one score and apply the decision rule. Returns what happened:
    added | removed | vetoed | unvetoed | unchanged."""
    score = round(float(p), 4)
    if lk is not None:
        lk.score, lk.model_version = score, version
        if lk.method == "user":
            return "unchanged"
    if policy == "or":
        if lk is None:
            if p >= t:
                s.add(ItemTheme(item_id=item_id, theme_id=theme_id, method="model", active=True, theme_version=theme_version,
                                evidence={"model": score}, score=score, model_version=version))
                return "added"
            return "unchanged"
        ev = dict(lk.evidence or {})
        if lk.method == "model":
            ev["model"] = score
            if p >= t and not lk.active:
                lk.active, lk.evidence = True, ev
                return "added"
            if p < t and lk.active:
                if ev.get("was") in ("rule", "query"):  # give the link back to where it came from
                    lk.method = ev.pop("was")
                lk.active, lk.evidence = False, ev
                return "removed"
            lk.evidence = ev
            return "unchanged"
        if not lk.active and p >= t:  # an inactive rule or search link the model now supports
            lk.method, lk.active, lk.evidence = "model", True, {**ev, "model": score, "was": lk.method}
            return "added"
        return "unchanged"
    if lk is None or lk.method != "rule":
        return "unchanged"
    ev = dict(lk.evidence or {})
    if veto_on and lk.active and p < t:
        lk.active, lk.evidence = False, {**ev, "veto": score}
        return "vetoed"
    if not lk.active and "veto" in ev and (p >= t or not veto_on):
        ev.pop("veto")
        lk.active, lk.evidence = True, ev
        return "unvetoed"
    return "unchanged"


def _chunks(xs: list, n: int):
    for i in range(0, len(xs), n):
        yield xs[i:i + n]


def _take_write_lock(s: Session) -> None:
    """Start the write transaction now. On SQLite the first write takes the database's write lock, so
    nobody can commit between the re-read that follows and our commit. Writes nothing."""
    s.execute(text("UPDATE item_theme SET score = score WHERE 0"))


def _keep_peoples_changes(s: Session, chunk: list[int], links: dict, marks: dict) -> int:
    """Called with the write lock held, before flushing a batch. A person may have labelled one of these
    articles while the batch was being scored: their links (method 'user') and their relevance answer
    win. Returns how many of our pending link changes were dropped."""
    dropped = 0
    with s.no_autoflush:
        users = {(r[0], r[1]) for r in s.execute(select(ItemTheme.item_id, ItemTheme.theme_id).where(
            ItemTheme.item_id.in_(chunk), ItemTheme.method == "user"))}
        for obj in [o for o in s.new if isinstance(o, ItemTheme)]:
            if (obj.item_id, obj.theme_id) in users:
                s.expunge(obj)
                dropped += 1
        for key in users:
            lk = links.get(key)
            if lk is not None and lk.method != "user":
                s.refresh(lk)  # drops our change to it
                dropped += 1
        if marks:
            fresh = {r[0]: r[1] for r in s.execute(select(Item.id, Item.extra).where(Item.id.in_(list(marks))))}
            for it, mark in marks.values():
                it.extra = {**(fresh.get(it.id) or {}), "model": mark}
    return dropped


def classify_items(s: Session, model: ThemeModel, *, since: datetime | None = None, dry_run: bool = False,
                   batch: int = BATCH, log=None) -> dict:
    """Score relevant, counted articles (published or collected since `since`, or all) and apply the
    model. Commits per batch so memory and write locks stay small. Returns per-theme counts."""
    db_themes = {t.slug: t for t in s.scalars(select(Theme).where(Theme.active.is_(True)))}
    cols = [(k, db_themes[slug]) for k, slug in enumerate(model.themes) if slug in db_themes and model.has[k]]
    q = select(Item.id).where(Item.kind == "article", Item.relevant.is_(True), Item.duplicate_of.is_(None))
    if since is not None:
        q = q.where(or_(Item.published_at >= since, Item.created_at >= since))
    ids = s.scalars(q.order_by(Item.id)).all()
    counts = {t.slug: Counter() for _, t in cols}
    tids = [t.id for _, t in cols]
    ks = [k for k, _ in cols]
    n = kept = failed = 0
    for chunk in _chunks(ids, batch):
        items = s.scalars(select(Item).where(Item.id.in_(chunk)).order_by(Item.id)).all()
        P = model.proba([item_text(it.title, it.snippet, it.source_key) for it in items])
        links = {(lk.item_id, lk.theme_id): lk for lk in s.scalars(
            select(ItemTheme).where(ItemTheme.item_id.in_(chunk), ItemTheme.theme_id.in_(tids)))}
        # the model's answer matters for non-gender themes, and for gender themes only where it may veto a rule link
        mask = np.array([[model.policy[k] == "or" or (bool(model.veto[k]) and
                          getattr(links.get((it.id, th.id)), "method", None) == "rule")
                          for k, th in cols] for it in items], dtype=bool).reshape(len(items), len(cols))
        h = closeness(P[:, ks], model.th[ks], mask)
        marks = {}
        with s.no_autoflush:
            for i, it in enumerate(items):
                near = {}
                for k, th in cols:
                    p, t = float(P[i, k]), float(model.th[k])
                    lk = links.get((it.id, th.id))
                    what = apply_link(s, it.id, th.id, th.version, lk, p, t, model.policy[k], bool(model.veto[k]),
                                      model.version)
                    counts[th.slug][what] += 1
                    counts[th.slug]["above"] += p >= t
                    if lk is None and model.policy[k] == "or" and NEAR * t <= p < t:
                        near[th.slug] = round(p, 3)
                j = int(h[i].argmax()) if h.shape[1] else 0
                u = float(h[i, j]) if h.shape[1] else 0.0
                mark = {"v": model.version, "u": round(u, 3), "ut": cols[j][1].slug if u > 0 else None, "near": near}
                if (it.extra or {}).get("model") != mark:
                    marks[it.id] = (it, mark)
        n += len(items)
        if dry_run:
            s.rollback()
        else:
            try:
                with s.no_autoflush:  # nothing of ours may reach the database before the re-read
                    _take_write_lock(s)
                    kept += _keep_peoples_changes(s, chunk, links, marks)
                s.commit()
            except IntegrityError:  # should not happen under the lock; skip the batch, the next run scores it
                s.rollback()
                failed += len(items)
        s.expunge_all()
        if log:
            log(f"  {n}/{len(ids)} items")
    return {"items": n, "dry_run": dry_run, "version": model.version, "kept_for_people": kept,
            "failed_items": failed, "themes": {slug: dict(c) for slug, c in counts.items()}}


def reset_model_links(s: Session, chunk: int = 500) -> dict:
    """Undo everything a model wrote: model links go back to what they were (or off), vetoed rule
    links come back. Scores stay for the record. Used when no model should be live.
    Loads only model links and vetoed rule links, a few hundred articles at a time, committing each."""
    out = Counter()
    touched = or_(ItemTheme.method == "model",
                  (ItemTheme.method == "rule") & func.json_extract(ItemTheme.evidence, "$.veto").is_not(None))
    item_ids = s.scalars(select(ItemTheme.item_id).where(touched).distinct().order_by(ItemTheme.item_id)).all()
    for part in _chunks(item_ids, chunk):
        for lk in s.scalars(select(ItemTheme).where(ItemTheme.item_id.in_(part), touched)):
            ev = dict(lk.evidence or {})
            if lk.method == "model":
                if lk.active or "was" in ev:
                    out["model_links_off"] += 1
                lk.method = ev.pop("was", "model")
                lk.active, lk.evidence = False, ev
            elif "veto" in ev:
                ev.pop("veto")
                lk.active, lk.evidence = True, ev
                out["vetoes_lifted"] += 1
        s.commit()
        s.expunge_all()
    return dict(out)
