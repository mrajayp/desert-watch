"""Google Trends search interest: the need side of the 'search' lens (national, weekly).

Google gives 0-100 integers, scaled to the biggest point in each request and rounded. So every
request holds one anchor (an everyday word that belongs to no theme) beside up to four theme word
lists, each sent as one OR slot ('a + b + c'). A list is stored in anchor units:

    value = 100 * list / anchor_ref

anchor_ref is the anchor's median over the surrounding weeks of the same request, so a one-week
spike in the anchor does not read as a dip in every theme (the verifier saw a 3x one-week spike in
«مستشفى»). Ratios to the anchor carry over between requests, which keeps history comparable.

Weeks: Trends weeks run Sunday-Saturday and Desert Watch weeks Monday-Sunday. A Trends week starting
on Sunday S is filed under Monday S+1 (they share six of seven days). Daily data (windows of up to
269 days) is summed into exact Monday weeks instead. The partial current week is dropped and the
last two complete weeks are marked provisional, because Google revises them.

Rows (one per list per week, JSONL): theme_slug, basket, anchor, week (Monday), value_raw,
anchor_raw, has_data, fetched_at, request_id, plus resolution, days, nodata_days, provisional, geo,
provider. Never fetch the unofficial endpoints from the server: see scripts/fetch_gtrends.py."""
import statistics
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

SOURCE = "gtrends"
MAX_SLOTS = 5               # Trends compares at most five items per request
DAILY_MAX_DAYS = 269        # longer custom ranges come back weekly
DAILY_MIN_DAYS = 7          # a week from daily data has data only when all 7 days do (else the weekly row is used)
PROVISIONAL_WEEKS = 2       # Google revises the latest two weeks
ANCHOR_SMOOTH_WEEKS = 13    # centred median window for the anchor (6 weeks either side: spans Ramadan)
# "An improvement to our data collection system was applied from 1/1/22" (axis note on every
# 5-year response). Earlier weeks are not comparable, so they are never imported.
DATA_BREAK = date(2022, 1, 3)


def week_start(d: date) -> date:
    return d - timedelta(days=d.weekday())


def slot(terms: list[str]) -> str:
    """One OR slot: Trends adds up searches for any of the words."""
    return " + ".join(t.strip() for t in terms)


def same_terms(a, b) -> bool:
    return sorted(t.strip() for t in a) == sorted(t.strip() for t in b)


def config(country_config: dict) -> dict | None:
    g = country_config.get("gtrends")
    if not g or not g.get("anchor") or not g.get("baskets"):
        return None
    return g


def check_baskets(g: dict, themes: dict[str, list[str]]) -> list[str]:
    """Problems with the config: every list word must be one of that theme's own ar_terms, and no
    word may sit in two lists (the same searches would then drive two themes)."""
    out, owner = [], {}
    for slug, terms in (g.get("baskets") or {}).items():
        if slug not in themes:
            out.append(f"{slug}: unknown theme")
            continue
        extra = [t for t in terms if t not in themes[slug]]
        if extra:
            out.append(f"{slug}: not in the theme's ar_terms: {', '.join(extra)}")
        shared = [t for t in terms if owner.setdefault(t, slug) != slug]
        if shared:
            out.append(f"{slug}: already in another list: {', '.join(f'{t} ({owner[t]})' for t in shared)}")
    return out


def groups(g: dict) -> list[list[str]]:
    """Which lists share a request. Big lists go together and small lists together, so a big
    list never rounds a small one down to zero."""
    baskets = g["baskets"]
    listed = [[s for s in grp if s in baskets] for grp in (g.get("groups") or [])]
    seen = {s for grp in listed for s in grp}
    listed.append([s for s in baskets if s not in seen])
    n = MAX_SLOTS - 1  # the anchor takes the fifth place
    return [grp[i:i + n] for grp in listed for i in range(0, len(grp), n)]


def parse_points(timeline: list[dict]) -> list[dict]:
    """Google's timelineData -> [{day, values, has_data, partial}]. `time` is UTC midnight of the
    first day of the point (a Sunday for weekly data)."""
    out = []
    for p in timeline:
        out.append({"day": datetime.fromtimestamp(int(p["time"]), tz=timezone.utc).date(),
                    "values": [int(v) for v in p["value"]], "has_data": [bool(h) for h in p["hasData"]],
                    "partial": bool(p.get("isPartial"))})
    return out


def _monday(d: date) -> date:
    return d + timedelta(days=1) if d.weekday() == 6 else week_start(d)


def build_rows(points: list[dict], slots: list[tuple[str, list[str]]], anchor: str, *, resolution: str,
               request_id: str, fetched_at: str, geo: str = "LY", provider: str = "widget") -> list[dict]:
    """Rows for one request. `slots` are the theme lists in request order; the anchor is the last
    item. Weekly points map Sunday S -> Monday S+1. Daily points are summed into complete Monday
    weeks (incomplete weeks at either end are dropped)."""
    a = len(slots)
    weeks: dict[date, dict] = {}
    if resolution == "week":
        for p in points:
            if p["partial"]:
                continue
            weeks[_monday(p["day"])] = {"days": 1, "values": p["values"],
                                        "nodata": [0 if h else 1 for h in p["has_data"]]}
    elif resolution == "day":
        for p in points:
            if p["partial"]:
                continue
            w = weeks.setdefault(week_start(p["day"]), {"days": 0, "values": [0] * (a + 1), "nodata": [0] * (a + 1)})
            w["days"] += 1
            for i in range(a + 1):
                w["values"][i] += p["values"][i]
                w["nodata"][i] += 0 if p["has_data"][i] else 1
        weeks = {k: v for k, v in weeks.items() if v["days"] == 7}
    else:
        raise ValueError(resolution)
    ordered = sorted(weeks)
    provisional = set(ordered[-PROVISIONAL_WEEKS:])
    rows = []
    for wk in ordered:
        w = weeks[wk]
        for i, (slug, terms) in enumerate(slots):
            if resolution == "day":
                missing = max(w["nodata"][i], w["nodata"][a])
                has = 7 - missing >= DAILY_MIN_DAYS and w["values"][a] > 0
                nodata_days = w["nodata"][i]
            else:
                has = not w["nodata"][i] and not w["nodata"][a]
                nodata_days = 7 * w["nodata"][i]
            rows.append({"theme_slug": slug, "basket": list(terms), "anchor": anchor, "week": wk.isoformat(),
                         "value_raw": w["values"][i], "anchor_raw": w["values"][a], "has_data": bool(has),
                         "fetched_at": fetched_at, "request_id": request_id, "resolution": resolution,
                         "nodata_days": nodata_days,
                         "provisional": wk in provisional, "geo": geo, "provider": provider})
    return rows


def anchor_refs(rows: list[dict]) -> dict[str, float]:
    """week -> centred median of the anchor over ANCHOR_SMOOTH_WEEKS weeks, for the rows of one
    request (weeks where the anchor had no data are left out of the median)."""
    return anchor_refs_by_week({r["week"]: r["anchor_raw"] for r in rows})


def anchor_refs_by_week(anchor_raw: dict[str, int]) -> dict[str, float]:
    """The same from one request's {week: anchor_raw}, so an import can stream its rows."""
    by_week = {wk: v for wk, v in anchor_raw.items() if v > 0}
    weeks = sorted(anchor_raw)
    half = ANCHOR_SMOOTH_WEEKS // 2
    out = {}
    for i, wk in enumerate(weeks):
        near = [by_week[w] for w in weeks[max(0, i - half):i + half + 1] if w in by_week]
        out[wk] = float(statistics.median(near)) if near else 0.0
    return out


# ---------------------------------------------------------------- the lens's data rule
def flag_missing_weeks(s: Session, country_id: int | None = None) -> int:
    """A search-lens cell is insufficient unless every week of its window has search data (a week
    Google held back, or one we have not fetched yet, counts as missing). Runs after scoring;
    returns how many cells it marked."""
    from . import settings
    from .models import CellWeek, Item, ItemTheme
    have = set()
    q = (select(ItemTheme.theme_id, Item.published_at, Item.extra)
         .join(ItemTheme, ItemTheme.item_id == Item.id)
         .where(Item.kind == "search", Item.source_key == SOURCE, Item.relevant.is_(True),
                Item.duplicate_of.is_(None), ItemTheme.active.is_(True)))
    if country_id is not None:
        q = q.where(Item.country_id == country_id)
    for tid, pub, extra in s.execute(q):
        if (extra or {}).get("has_data", True):
            have.add((tid, week_start(pub.date())))
    cq = select(CellWeek).where(CellWeek.lens == "search")
    if country_id is not None:
        cq = cq.where(CellWeek.country_id == country_id)
    n = 0
    for c in s.scalars(cq):
        missing = [(c.week_start - timedelta(weeks=i)).isoformat() for i in range(settings.WINDOW_WEEKS)
                   if (c.theme_id, c.week_start - timedelta(weeks=i)) not in have]
        if not missing:
            continue
        b = dict(c.breakdown or {})
        b["search_missing_weeks"] = missing
        c.breakdown = b
        if not c.insufficient or c.gap is not None:
            c.insufficient, c.gap = True, None
            n += 1
    s.commit()
    return n


def search_terms(s: Session, country_id: int, theme_slug: str, theme_group: str | None = None) -> dict:
    """What the gap panel shows for the search lens: the theme's words with English glosses, or
    why the theme is not measured (`unmeasured` by slug, then by theme group)."""
    from .models import Country
    c = s.get(Country, country_id)
    g = config(c.config or {}) if c else None
    if not g:
        return {"measured": False, "terms": [], "anchor": None, "unmeasured_reason": None}
    gloss = g.get("glosses") or {}
    terms = (g.get("baskets") or {}).get(theme_slug) or []
    why = g.get("unmeasured") or {}
    return {"measured": bool(terms), "version": g.get("version"),
            "terms": [{"ar": t, "en": gloss.get(t)} for t in terms],
            "anchor": {"ar": g["anchor"], "en": gloss.get(g["anchor"])},
            "unmeasured_reason": None if terms else why.get(theme_slug) or why.get(theme_group or "")}
