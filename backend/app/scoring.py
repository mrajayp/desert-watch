"""Gap scoring. One cell per (theme, region, week, lens) over a 4-week rolling window.

  ratio      = coverage / need
  shrunk     = (coverage + m * ref) / (need + m)          # small cells pulled to the reference
  gap        = ln(ref / shrunk)                           # > 0: less coverage than expected

The reference depends on the lens:
  * pooled       - the coverage/need ratio of the comparison set (all themes nationally,
                   or the theme's national figure for a region). Used for events/humanitarian/journalist.
  * own_history  - the cell's own ratio over the previous 12 weeks. Used for the audience
                   lens, because pageview totals depend on which Wikipedia articles were chosen
                   and are not comparable across themes.
Cells with need below the lens minimum are marked insufficient and get no gap."""
import math
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

from sqlalchemy import and_, delete, func, select
from sqlalchemy.orm import Session

from . import settings
from .models import (CellWeek, Country, Item, ItemRegion, ItemTheme, OutletCategory, Region, Theme,
                     utcnow)

LENSES = {
    "audience": {"kinds": ("pageview",), "reference": "own_history", "levels": ("national",)},
    "events": {"kinds": ("event",), "reference": "pooled", "levels": ("national", "macro", "district")},
    "humanitarian": {"kinds": ("report",), "reference": "pooled", "levels": ("national", "macro", "district")},
    "journalist": {"kinds": ("suggestion",), "reference": "pooled", "levels": ("national", "macro", "district")},
}
PARTISAN = {"tripoli_gnu_aligned", "east_lna_aligned", "islamist_leaning", "tribal_local"}
# Sources whose weekly volume reflects someone else's selection, not how much was published:
# the backfill follows what a monitoring review chose to cite, which grew month by month.
# They count in what pages show, never in comparisons over time.
NOT_FOR_TRENDS = {"backfill"}


def week_start(d: date) -> date:
    return d - timedelta(days=d.weekday())


@dataclass
class Score:
    ratio: float | None
    ref_ratio: float | None
    gap: float | None
    insufficient: bool


def score_cell(coverage: float, need: float, ref_ratio: float | None, *, min_need: float,
               shrink: float) -> Score:
    if need < min_need or ref_ratio is None or ref_ratio <= 0:
        return Score(coverage / need if need else None, ref_ratio, None, True)
    shrunk = (coverage + shrink * ref_ratio) / (need + shrink)
    shrunk = max(shrunk, 1e-9)
    return Score(coverage / need, ref_ratio, math.log(ref_ratio / shrunk), False)


@dataclass
class CoverageAgg:
    total: int = 0
    lang: Counter = field(default_factory=Counter)
    scope: Counter = field(default_factory=Counter)
    alignment: Counter = field(default_factory=Counter)
    source: Counter = field(default_factory=Counter)
    unplaced: int = 0


def coverage_flags(cur: CoverageAgg, prev_cov: float, need: float, prev_need: float,
                   cur_comparable: float | None = None) -> list[str]:
    """prev_cov / cur_comparable count the same sources in both windows (see stable_sources)."""
    flags = []
    now = cur.total if cur_comparable is None else cur_comparable
    if prev_cov >= 4 and now < 0.5 * prev_cov and need >= 0.75 * prev_need and need > 0:
        flags.append("coverage_drop")
    if cur.total >= 5 and cur.lang.get("ar", 0) / cur.total < 0.2:
        flags.append("little_arabic")
    if cur.total >= 3 and cur.scope.get("libyan", 0) == 0 and (cur.scope.get("international", 0) + cur.scope.get("diaspora", 0)) > 0:
        flags.append("outside_only")
    partisan = {k: v for k, v in cur.alignment.items() if k in PARTISAN}
    if sum(partisan.values()) >= 3 and len(partisan) == 1 and cur.alignment.get("independent", 0) == 0:
        flags.append("partisan_only:" + next(iter(partisan)))
    if cur.total >= 5 and cur.unplaced / cur.total > 0.8:
        flags.append("mostly_unplaced")
    return flags


def _outlet_dims(s: Session, dims=("scope", "alignment")) -> dict[int, dict[str, str]]:
    out: dict[int, dict[str, str]] = defaultdict(dict)
    q = select(OutletCategory).where(OutletCategory.dimension.in_(dims), OutletCategory.status == "active",
                                     OutletCategory.valid_to.is_(None))
    for c in s.scalars(q):
        out[c.outlet_id][c.dimension] = c.value
    return out


def _region_tree(s: Session, country_id: int):
    regions = s.scalars(select(Region).where(Region.country_id == country_id)).all()
    by_id = {r.id: r for r in regions}

    def ancestors(rid):
        out = []
        while rid is not None:
            out.append(rid)
            rid = by_id[rid].parent_id
        return out
    return by_id, ancestors


def compute(s: Session, country_id: int, *, weeks: int = 12, today: date | None = None,
            lenses: tuple[str, ...] | None = None) -> int:
    today = today or date.today()
    last = week_start(today)
    first = last - timedelta(weeks=weeks - 1)
    history_from = first - timedelta(weeks=settings.WINDOW_WEEKS + 12)
    by_id, ancestors = _region_tree(s, country_id)
    # Coverage history only exists from the first collected article: baselines must not
    # reach back before it (cold start), or every theme looks over-covered.
    first_article = s.scalar(select(func.min(Item.published_at)).where(
        Item.country_id == country_id, Item.kind == "article", Item.source_key != "user"))
    coverage_start = week_start(first_article.date()) + timedelta(weeks=1) if first_article else today
    national = next(r for r in by_id.values() if r.level == "national")
    # When each source was collecting (first/last article). Comparisons over time only count
    # sources present across the whole compared span, so adding Google Alerts or the backfill
    # (or the backfill ending) does not read as a change in coverage.
    spans = {k: (lo.date(), hi.date()) for k, lo, hi in s.execute(
        select(Item.source_key, func.min(Item.published_at), func.max(Item.published_at))
        .where(Item.country_id == country_id, Item.kind == "article", Item.relevant.is_(True),
               Item.duplicate_of.is_(None)).group_by(Item.source_key)).all()}

    def stable_sources(span_start: date, span_end_week: date) -> set[str]:
        return {k for k, (lo, hi) in spans.items()
                if lo <= span_start and hi >= span_end_week and k not in NOT_FOR_TRENDS}

    def counted(agg: "CoverageAgg", keep: set[str]) -> int:
        return sum(v for k, v in agg.source.items() if k in keep) if keep else agg.total
    themes = s.scalars(select(Theme).where(Theme.active.is_(True))).all()
    dims = _outlet_dims(s)

    # ---- load items once: (week, theme, region) -> aggregates
    rows = s.execute(
        select(Item.id, Item.kind, Item.published_at, Item.lang, Item.outlet_id, Item.source_key, Item.value,
               ItemTheme.theme_id)
        .join(ItemTheme, and_(ItemTheme.item_id == Item.id, ItemTheme.active.is_(True)))
        .where(Item.country_id == country_id, Item.relevant.is_(True), Item.duplicate_of.is_(None),
               Item.published_at >= datetime.combine(history_from, datetime.min.time()),
               Item.published_at < datetime.combine(last + timedelta(days=7), datetime.min.time()))
    ).all()
    item_regions: dict[int, list[int]] = defaultdict(list)
    ids = {r.id for r in rows}
    for ir in s.scalars(select(ItemRegion).where(ItemRegion.active.is_(True))):
        if ir.item_id in ids:
            item_regions[ir.item_id].append(ir.region_id)

    weekly_cov: dict[tuple, CoverageAgg] = defaultdict(CoverageAgg)
    weekly_need: dict[tuple, dict] = defaultdict(lambda: defaultdict(float))  # (wk,theme,region) -> lens -> value
    for r in rows:
        wk = week_start(r.published_at.date())
        regs = {national.id}
        for rid in item_regions.get(r.id, []):
            regs.update(ancestors(rid))
        if r.kind == "article":
            d = dims.get(r.outlet_id, {})
            for reg in regs:
                a = weekly_cov[(wk, r.theme_id, reg)]
                a.total += 1
                a.lang[r.lang or "und"] += 1
                a.scope[d.get("scope", "unknown")] += 1
                a.alignment[d.get("alignment", "unknown")] += 1
                a.source[r.source_key] += 1
                if reg == national.id and not item_regions.get(r.id):
                    a.unplaced += 1
        else:
            for lens, cfg in LENSES.items():
                if r.kind in cfg["kinds"]:
                    for reg in regs:
                        weekly_need[(wk, r.theme_id, reg)][lens] += r.value

    def window(wk_end: date, theme_id, region_id):
        agg, need = CoverageAgg(), defaultdict(float)
        for i in range(settings.WINDOW_WEEKS):
            k = (wk_end - timedelta(weeks=i), theme_id, region_id)
            c = weekly_cov.get(k)
            if c:
                agg.total += c.total
                agg.lang.update(c.lang)
                agg.scope.update(c.scope)
                agg.alignment.update(c.alignment)
                agg.source.update(c.source)
                agg.unplaced += c.unplaced
            for lens, v in weekly_need.get(k, {}).items():
                need[lens] += v
        return agg, need

    lenses = lenses or tuple(LENSES)
    s.execute(delete(CellWeek).where(CellWeek.country_id == country_id, CellWeek.week_start >= first,
                                     CellWeek.week_start <= last, CellWeek.lens.in_(lenses)))
    n = 0
    region_ids = [r.id for r in by_id.values()]
    wk = first
    while wk <= last:
        cur = {(t.id, rid): window(wk, t.id, rid) for t in themes for rid in region_ids}
        prev = {(t.id, rid): window(wk - timedelta(weeks=settings.WINDOW_WEEKS), t.id, rid)
                for t in themes for rid in region_ids}
        for lens in lenses:
            cfg = LENSES[lens]
            min_need, m = settings.MIN_NEED_UNITS[lens], settings.SHRINK_STRENGTH[lens]
            # pooled reference for national cells: all themes nationally
            nat_cov = sum(cur[(t.id, national.id)][0].total for t in themes)
            nat_need = sum(cur[(t.id, national.id)][1][lens] for t in themes)
            pooled_nat = nat_cov / nat_need if nat_need else None
            for t in themes:
                theme_nat_agg, theme_nat_need = cur[(t.id, national.id)]
                theme_ref = (theme_nat_agg.total / theme_nat_need[lens]) if theme_nat_need[lens] else None
                for rid in region_ids:
                    reg = by_id[rid]
                    if reg.level not in cfg["levels"]:
                        continue
                    agg, need = cur[(t.id, rid)]
                    pagg, pneed = prev[(t.id, rid)]
                    baseline_windows = 0
                    scored_cov, keep = agg.total, None
                    if cfg["reference"] == "own_history":
                        hc = hn = 0.0
                        keep = stable_sources(wk - timedelta(weeks=4 * settings.WINDOW_WEEKS - 1), wk)
                        scored_cov = counted(agg, keep)
                        for i in range(1, 4):
                            w_end = wk - timedelta(weeks=settings.WINDOW_WEEKS * i)
                            if w_end - timedelta(weeks=settings.WINDOW_WEEKS - 1) < coverage_start:
                                continue  # window starts before collection began
                            a2, n2 = window(w_end, t.id, rid)
                            hc += counted(a2, keep)
                            hn += n2[lens]
                            baseline_windows += 1
                        ref = hc / hn if hn else None
                    else:
                        ref = pooled_nat if reg.level == "national" else theme_ref
                    partial = wk - timedelta(weeks=settings.WINDOW_WEEKS - 1) < coverage_start
                    sc = score_cell(scored_cov, need[lens], ref, min_need=min_need, shrink=m)
                    if partial:  # window reaches back before collection began: coverage undercounted
                        sc = Score(sc.ratio, sc.ref_ratio, None, True)
                    if need[lens] == 0 and agg.total == 0 and reg.level != "national":
                        continue  # keep the table small: empty regional cells are implicit
                    # coverage-drop flag: compare the two windows on the sources present across both
                    keep2 = stable_sources(wk - timedelta(weeks=2 * settings.WINDOW_WEEKS - 1), wk)
                    prev_ok = (wk - timedelta(weeks=2 * settings.WINDOW_WEEKS - 1)) >= coverage_start
                    s.add(CellWeek(
                        country_id=country_id, theme_id=t.id, region_id=rid, week_start=wk, lens=lens,
                        need=need[lens], coverage=agg.total, ratio=sc.ratio, ref_ratio=sc.ref_ratio, gap=sc.gap,
                        insufficient=sc.insufficient,
                        flags=coverage_flags(agg, counted(pagg, keep2) if prev_ok else 0, need[lens], pneed[lens],
                                             cur_comparable=counted(agg, keep2)),
                        breakdown={"lang": dict(agg.lang), "scope": dict(agg.scope),
                                   "alignment": dict(agg.alignment), "source": dict(agg.source),
                                   "unplaced": agg.unplaced, "prev_coverage": pagg.total,
                                   "prev_need": pneed[lens], "reference": cfg["reference"],
                                   "baseline_windows": baseline_windows, "partial_window": partial,
                                   "building_baseline": cfg["reference"] == "own_history" and baseline_windows == 0,
                                   "scored_coverage": scored_cov,
                                   "scored_sources": sorted(keep) if keep is not None else None},
                        computed_at=utcnow()))
                    n += 1
        wk += timedelta(weeks=1)
    s.commit()
    return n


CHUNK_WEEKS = 26  # long recomputes run in chunks so memory stays bounded (512 MB machine)


def compute_chunked(s: Session, country_id: int, *, weeks: int = 12, today: date | None = None, **kw) -> int:
    """Score `weeks` weeks ending at `today` in CHUNK_WEEKS-sized pieces, oldest first. Each piece
    loads only the items its windows need (its weeks plus baseline history)."""
    today = today or date.today()
    last = week_start(today)
    n, done = 0, 0
    while done < weeks:
        size = min(CHUNK_WEEKS, weeks - done)
        chunk_end = last - timedelta(weeks=weeks - done - size)
        n += compute(s, country_id, weeks=size, today=chunk_end, **kw)
        s.expunge_all()
        done += size
    return n


def compute_all(s: Session, **kw) -> int:
    return sum(compute_chunked(s, c.id, **kw) for c in s.scalars(select(Country)))
