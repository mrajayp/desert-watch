"""Theme labels folded into one vector per item, for training, gates and admin stats.

Sources (Label rows built by learning.build_labels or import-gold-labels):
  theme_set        full vector: listed themes = 1, every other theme it was asked about = 0
                   (libya False -> all 0)
  theme_relevance  one theme (single correction), or all 0 (item_relevant False), or the
                   themes a person picked when adding an article (listed = 1, rest unknown)
Later labels win per (item, theme); a person's label always wins over a silver one.
Plain Python: no numpy here."""
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Event, ItemTheme, Label, Theme

THEME_LABELS = ("theme_set", "theme_relevance")
_RANK = {"silver": 0, "implicit": 0}  # anything else (explicit) ranks 1


def libya_value(v) -> bool | None:
    """True / False, or None for 'unclear' (stored as a bool or 'yes' / 'no' / 'unclear')."""
    if isinstance(v, bool):
        return v
    if isinstance(v, str):
        return {"yes": True, "true": True, "no": False, "false": False}.get(v.lower())
    return None


def _cells(label_type: str, v: dict, slug2id: dict[str, int], all_ids: list[int]) -> dict[int, int]:
    def tid(x):
        if isinstance(x, bool):
            return None
        if isinstance(x, int) or (isinstance(x, str) and x.isdigit()):
            return int(x) if int(x) in all_ids else None
        return slug2id.get(x)

    scope = [t for t in (tid(x) for x in v.get("of", [])) if t] or all_ids
    if label_type == "theme_set":
        if libya_value(v.get("libya")) is False:
            return dict.fromkeys(scope, 0)
        listed = {t for t in (tid(x) for x in v.get("themes", [])) if t}
        return {t: int(t in listed) for t in set(scope) | listed}
    if v.get("item_relevant") is False:
        return dict.fromkeys(scope, 0)
    out = {}
    if v.get("theme_id") is not None and v.get("theme_relevant") is not None:
        t = tid(v["theme_id"])
        if t:
            out[t] = int(bool(v["theme_relevant"]))
    for x in v.get("themes", []) if v.get("relevant") else []:  # added article: picked themes only
        t = tid(x)
        if t:
            out[t] = 1
    return out


def item_vectors(s: Session, themes: list[Theme] | None = None) -> dict[int, dict]:
    """{item_id: {"y": {theme_id: 0|1}, "w": {theme_id: weight}, "origin": {...}}} for labelled items.
    Themes a label says nothing about are absent (unknown)."""
    themes = themes if themes is not None else s.scalars(select(Theme).where(Theme.active.is_(True))).all()
    slug2id = {t.slug: t.id for t in themes}
    all_ids = sorted(slug2id.values())
    rows = s.scalars(select(Label).where(Label.label_type.in_(THEME_LABELS), Label.object_type == "item")).all()
    rows = sorted(rows, key=lambda lb: (_RANK.get(lb.origin, 1), lb.created_at, lb.id))
    out: dict[int, dict] = {}
    for lb in rows:
        try:
            iid = int(lb.object_key)
        except (TypeError, ValueError):
            continue
        cells = _cells(lb.label_type, lb.value or {}, slug2id, all_ids)
        if not cells:
            continue
        d = out.setdefault(iid, {"y": {}, "w": {}, "origin": set()})
        for t, y in cells.items():
            d["y"][t] = y
            d["w"][t] = float(lb.weight if lb.weight is not None else 1.0)
        d["origin"].add(lb.origin)
    return out


def theme_stats(vectors: dict[int, dict], themes: list[Theme]) -> dict[str, dict]:
    """Per theme slug: labelled items and positives."""
    out = {t.slug: {"labelled": 0, "positives": 0} for t in themes}
    by_id = {t.id: t.slug for t in themes}
    for d in vectors.values():
        for tid, y in d["y"].items():
            if tid in by_id:
                out[by_id[tid]]["labelled"] += 1
                out[by_id[tid]]["positives"] += y
    return out


def labelled_item_ids(s: Session) -> set[int]:
    """Items someone already labelled, including corrections not yet turned into Label rows."""
    keys = set(s.scalars(select(Label.object_key).where(Label.label_type.in_(THEME_LABELS), Label.object_type == "item")))
    keys |= set(s.scalars(select(Event.object_key).where(Event.type == "correction", Event.object_type == "item")))
    ids = {int(k) for k in keys if k and str(k).isdigit()}
    ids |= set(s.scalars(select(ItemTheme.item_id).where(ItemTheme.method == "user").distinct()))
    return ids
