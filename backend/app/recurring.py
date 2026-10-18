"""Recurring posts are not stories.

Daily exchange rates, weather, prayer times and the like reach us as one article a day with the
same headline except for a number or a weekday. Counted as articles they would make a theme look
covered when nothing was reported. Once a night mark_recurring judges the articles of the last
RECUR_DAYS days: an article is recurring when its outlet family (dedupe.outlet_families: a website
and its social accounts) published the same headline, by recurrence key (the normalised title with
digits and weekday names removed, the pattern resolve.py uses to tell daily posts apart), in
RECUR_MIN or more distinct stories within some RECUR_DAYS-day span that includes it. It sets
extra.recurring = true on every copy of those articles, and scoring, the Trends bars, the article
lists and the digest skip them (scoring.counted_items). The verdict depends on the headline's own
dates, never on the day the job runs, so it does not change as the window moves on; it is removed
again when a re-run finds fewer repeats (an article deleted or moved to another outlet). Articles
older than the evaluated range keep their verdict; `since` evaluates history in one pass (the
rebuild step after this module ships).

Recurrence counts stories, not copies: the Google News copy and the feed copy of one day's post
are one occurrence (coalesce(duplicate_of, id)).

item.extra is written one key at a time in SQL (json_set / json_remove), as resolve.py does: a user's
relevance decision may land in the same column while the job runs."""
import logging
from bisect import bisect_left, bisect_right
from collections import defaultdict
from datetime import datetime, timedelta

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from .dedupe import outlet_families
from .models import Item, utcnow
from .resolve import _DIGITS, _WEEKDAYS, clean_title
from .textnorm import normalise

log = logging.getLogger("desert_watch.recurring")

RECUR_DAYS = 30     # the window a headline must recur in
RECUR_MIN = 3       # ... this many times (distinct stories) at one outlet family

_EXTRA = "CASE json_type(extra) WHEN 'object' THEN extra ELSE '{}' END"
_MARK = text(f"UPDATE item SET extra = json_set({_EXTRA}, '$.recurring', json('true')) WHERE id = :id")
_UNMARK = text(f"UPDATE item SET extra = json_remove({_EXTRA}, '$.recurring') WHERE id = :id")


def recurrence_key(title: str | None) -> str:
    """The headline with its digits and weekday names removed, normalised (textnorm.normalise):
    'أسعار صرف الدينار اليوم الخميس 8 أكتوبر' and '... الجمعة 9 أكتوبر' share one key."""
    norm = _DIGITS.sub(" ", normalise(clean_title(title)))
    return " ".join(w for w in norm.split() if w not in _WEEKDAYS)


def mark_recurring(s: Session, *, now: datetime | None = None, days: int = RECUR_DAYS,
                   min_repeats: int = RECUR_MIN, since: datetime | None = None) -> dict:
    """Judges the articles published since `since` (default: the last `days` days) and sets or clears
    their mark. Articles up to `days` before `since` are read as well, so an article at the start of
    the range sees the repeats before it. Idempotent. Returns counts."""
    now = now or utcnow()
    since = since or now - timedelta(days=days)
    span = timedelta(days=days)
    family = outlet_families(s)
    rows = s.execute(select(Item.id, Item.outlet_id, Item.title, Item.duplicate_of, Item.extra, Item.published_at).where(
        Item.kind == "article", Item.outlet_id.is_not(None), Item.title.is_not(None),
        Item.published_at >= since - span, Item.published_at < now + timedelta(days=1))).all()
    groups: dict[tuple, list] = defaultdict(list)
    for r in rows:
        key = recurrence_key(r.title)
        if key:
            groups[(family.get(r.outlet_id, (r.outlet_id,))[0], key)].append(r)
    marked = cleared = recurring = judged = 0
    for members in groups.values():
        story_day: dict[int, datetime] = {}          # story root -> its earliest copy's date
        for r in members:
            root = r.duplicate_of or r.id
            story_day[root] = min(story_day.get(root, r.published_at), r.published_at)
        dates = sorted(story_day.values())
        hit = False
        for r in members:
            if r.published_at < since:
                continue                              # context only: keeps the verdict it has
            judged += 1
            d = story_day[r.duplicate_of or r.id]
            # the most distinct stories in any `days`-day span that includes this one
            lo = bisect_left(dates, d - span)
            best = max((bisect_right(dates, a + span) - i for i, a in enumerate(dates[lo:], lo) if a <= d), default=0)
            recurs = best >= min_repeats
            hit = hit or recurs
            was = bool(r.extra.get("recurring")) if isinstance(r.extra, dict) else False
            if recurs and not was:
                s.execute(_MARK, {"id": r.id})
                marked += 1
            elif was and not recurs:
                s.execute(_UNMARK, {"id": r.id})
                cleared += 1
        recurring += hit
    s.commit()
    out = {"headlines": recurring, "marked": marked, "cleared": cleared, "articles": judged, "days": days,
           "since": since.date().isoformat()}
    log.info("recurring: %s", out)
    return out


def collect(s: Session, **kw) -> "RunResult":
    """mark_recurring as a recorded job (source_run 'recurring', for the source-health strip)."""
    from .collectors.base import RunResult
    st = mark_recurring(s, **kw)
    return RunResult(rows=st["marked"],
                     detail=f"{st['headlines']} recurring headlines in {st['days']} days: {st['marked']} articles "
                            f"marked, {st['cleared']} cleared")
