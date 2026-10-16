"""One story, counted once.

The same article often reaches us twice: Google News gives us its own redirect link, while the
outlet's feed, Google Alerts or the backfill give the outlet's real URL. URLs cannot match, so we
compare headlines instead: same outlet, published within a day of each other, and nearly the same
words (Jaccard >= DUP_JACCARD on normalised tokens). The copy we keep is the one with the outlet's
own link; the others get `duplicate_of` and are left out of every count.

"Same outlet" means the same outlet family: a website and the social accounts it links to
(outlet.external["parent"], set from config). A page's post and the same story on its website count
once, and the website copy is kept."""
from collections import defaultdict
from datetime import datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from .ingest import SOCIAL
from .models import Item, Outlet
from .network import jaccard, title_tokens

DUP_JACCARD = 0.8
# which copy to keep: lower is better (real outlet URLs first, Google redirect links last)
KEEP_ORDER = {"rss": 0, "backfill": 1, "galerts": 2, "official": 3, "user": 4, "gdelt": 5, "youtube": 6, "gnews": 9,
              "gnews_social": 10}


def outlet_families(s: Session) -> dict[int, tuple[int, bool]]:
    """outlet id -> (family id, is a social account). The family id is the parent website's outlet id
    when the account has one on record, else the outlet's own id."""
    rows = s.execute(select(Outlet.id, Outlet.domain, Outlet.external)).all()
    by_domain = {r.domain: r.id for r in rows}
    return {r.id: (by_domain.get((r.external or {}).get("parent"), r.id), r.domain.split("/", 1)[0] in SOCIAL)
            for r in rows}


def mark_duplicates(s: Session, since: datetime | None = None) -> int:
    """Marks duplicates among relevant articles published since `since` (all if None). Idempotent."""
    q = select(Item.id, Item.outlet_id, Item.published_at, Item.title, Item.source_key, Item.duplicate_of).where(
        Item.kind == "article", Item.outlet_id.is_not(None), Item.title.is_not(None))
    if since:
        q = q.where(Item.published_at >= since - timedelta(days=1))
    family = outlet_families(s)
    by_outlet_day = defaultdict(list)
    for r in s.execute(q):
        by_outlet_day[(family.get(r.outlet_id, (r.outlet_id,))[0], r.published_at.date())].append(r)
    marks: dict[int, int] = {}
    for (outlet, day), rows in by_outlet_day.items():
        # compare with the same outlet's previous day too (time zones, late feeds)
        pool = rows + by_outlet_day.get((outlet, day - timedelta(days=1)), [])
        if len(pool) < 2:
            continue
        toks = {r.id: title_tokens(r.title) for r in pool}
        # the website's copy before a social one, then by route
        ranked = sorted(pool, key=lambda r: (family.get(r.outlet_id, (0, False))[1], KEEP_ORDER.get(r.source_key, 5), r.id))
        kept: list = []
        for r in ranked:
            match = next((k for k in kept if len(toks[r.id]) >= 3 and jaccard(toks[r.id], toks[k.id]) >= DUP_JACCARD), None)
            if match is None:
                kept.append(r)
            elif r.duplicate_of != match.id and r.id not in marks:
                marks[r.id] = match.id
    for dup, keep in marks.items():
        s.execute(update(Item).where(Item.id == dup).values(duplicate_of=keep))
        s.execute(update(Item).where(Item.duplicate_of == dup).values(duplicate_of=keep))  # keep chains flat
    s.commit()
    return len(marks)
