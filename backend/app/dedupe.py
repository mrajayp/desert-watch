"""One story, counted once.

The same article often reaches us twice: Google News gives us its own redirect link, while the
outlet's feed, Google Alerts or the backfill give the outlet's real URL. URLs cannot match, so we
compare headlines instead: same outlet, published within a day of each other, and nearly the same
words (Jaccard >= DUP_JACCARD on normalised tokens). The copy we keep is the one with the outlet's
own link; the others get `duplicate_of` and are left out of every count."""
from collections import defaultdict
from datetime import datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from .models import Item
from .network import jaccard, title_tokens

DUP_JACCARD = 0.8
# which copy to keep: lower is better (real outlet URLs first, Google redirect links last)
KEEP_ORDER = {"rss": 0, "backfill": 1, "galerts": 2, "official": 3, "user": 4, "gdelt": 5, "gnews": 9}


def mark_duplicates(s: Session, since: datetime | None = None) -> int:
    """Marks duplicates among relevant articles published since `since` (all if None). Idempotent."""
    q = select(Item.id, Item.outlet_id, Item.published_at, Item.title, Item.source_key, Item.duplicate_of).where(
        Item.kind == "article", Item.outlet_id.is_not(None), Item.title.is_not(None))
    if since:
        q = q.where(Item.published_at >= since - timedelta(days=1))
    by_outlet_day = defaultdict(list)
    for r in s.execute(q):
        by_outlet_day[(r.outlet_id, r.published_at.date())].append(r)
    marks: dict[int, int] = {}
    for (outlet, day), rows in by_outlet_day.items():
        # compare with the same outlet's previous day too (time zones, late feeds)
        pool = rows + by_outlet_day.get((outlet, day - timedelta(days=1)), [])
        if len(pool) < 2:
            continue
        toks = {r.id: title_tokens(r.title) for r in pool}
        ranked = sorted(pool, key=lambda r: (KEEP_ORDER.get(r.source_key, 5), r.id))
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
