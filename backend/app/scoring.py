"""Gap scoring. One cell per (theme, region, week, lens) over a 4-week rolling window.

  C          = articles in the window, from comparable source|outlet pairs only
  E          = ref * need                                 # articles the reference expects
  gap        = ln((E + A) / (C + A))                      # > 0: fewer articles than expected
             = ln(ref / shrunk), shrunk = (C + A) / (need + A / ref)

A (settings.PRIOR_ARTICLES) is a prior in articles for every lens, so small cells are pulled
towards "as expected" by the same amount whatever the need unit. A cell is judged only when
E >= settings.MIN_EXPECTED_ARTICLES.

The reference depends on the lens:
  * pooled       - the coverage/need ratio of the comparison set (all themes nationally,
                   or the theme's national figure for a region). Used for events/humanitarian/journalist.
  * own_history  - the cell's own ratio over the previous 12 weeks. Used for the audience
                   lens, because pageview totals depend on which Wikipedia articles were chosen
                   and are not comparable across themes.
Every cell without a gap says why in breakdown.reason: in_progress (the week, or its need data,
has not ended), building_baseline, no_need_data or too_few_expected."""
import math
import statistics
from bisect import bisect_left
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

from sqlalchemy import and_, delete, func, select
from sqlalchemy.orm import Session

from . import settings
from .models import (CellWeek, Country, Item, ItemRegion, ItemTheme, OutletCategory, Region, Theme,
                     utcnow)

# daily: need arrives as one reading per day, so a week counts as complete only once its need
# data reaches the week's last day.
LENSES = {
    "audience": {"kinds": ("pageview",), "reference": "own_history", "levels": ("national",),
                 "unit": "pageviews", "daily": True},
    "events": {"kinds": ("event",), "reference": "pooled", "levels": ("national", "macro", "district"),
               "unit": "events"},
    "humanitarian": {"kinds": ("report",), "reference": "pooled", "levels": ("national", "macro", "district"),
                     "unit": "reports"},
    "journalist": {"kinds": ("suggestion",), "reference": "pooled", "levels": ("national", "macro", "district"),
                   "unit": "flags"},
}
PARTISAN = {"tripoli_gnu_aligned", "east_lna_aligned", "islamist_leaning", "tribal_local"}
# Sources whose weekly volume reflects someone else's selection, not how much was published:
# the backfill follows what a monitoring review chose to cite, which grew month by month.
# They count in what pages show, never in comparisons over time.
NOT_FOR_TRENDS = {"backfill"}
TREND_WEEKS = 52                                      # complete weeks on the Trends page
BASELINE_REACH = 4 * settings.WINDOW_WEEKS - 1        # weeks back to the start of a cell's own-history baseline
PAIR_END_GRACE = timedelta(days=14)                   # a quiet fortnight at the end of a span is not a stop
SPIKE_DAYS, SPIKE_MIN_DAYS = 28, 7                    # trailing window for the pageview spike cap


def week_start(d: date) -> date:
    return d - timedelta(days=d.weekday())


def _dt(d: date) -> datetime:
    return datetime.combine(d, datetime.min.time())


@dataclass
class Score:
    ratio: float | None
    ref_ratio: float | None
    gap: float | None
    insufficient: bool
    expected: float | None = None
    reason: str | None = None


def score_cell(coverage: float, need: float, ref_ratio: float | None, *, prior: float | None = None,
               min_expected: float | None = None) -> Score:
    prior = settings.PRIOR_ARTICLES if prior is None else prior
    min_expected = settings.MIN_EXPECTED_ARTICLES if min_expected is None else min_expected
    ratio = coverage / need if need else None
    if not need or ref_ratio is None:
        return Score(ratio, ref_ratio, None, True, None, "no_need_data")
    expected = ref_ratio * need
    if expected < min_expected:
        return Score(ratio, ref_ratio, None, True, expected, "too_few_expected")
    return Score(ratio, ref_ratio, math.log((expected + prior) / (coverage + prior)), False, expected)


@dataclass
class CoverageAgg:
    total: int = 0
    lang: Counter = field(default_factory=Counter)
    scope: Counter = field(default_factory=Counter)
    alignment: Counter = field(default_factory=Counter)
    source: Counter = field(default_factory=Counter)
    pairs: Counter = field(default_factory=Counter)   # (source, outlet_id) -> articles
    late: Counter = field(default_factory=Counter)    # (source, outlet_id) -> articles after the last need day
    unplaced: int = 0


def coverage_flags(cur: CoverageAgg, prev_cov: float, need: float, prev_need: float,
                   cur_comparable: float | None = None) -> list[str]:
    """prev_cov / cur_comparable count the same sources in both windows (see comparable_pairs)."""
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


# ---------------------------------------------------------------- comparable sources
def pair_spans(s: Session, country_id: int) -> dict[tuple[str, int], tuple[date, date]]:
    """First and last article day of every source|outlet pair that may count in comparisons over time."""
    return {(src, oid): (lo.date(), hi.date()) for src, oid, lo, hi in s.execute(
        select(Item.source_key, Item.outlet_id, func.min(Item.published_at), func.max(Item.published_at))
        .where(Item.country_id == country_id, Item.kind == "article", Item.relevant.is_(True),
               Item.duplicate_of.is_(None), Item.outlet_id.is_not(None), Item.source_key.not_in(NOT_FOR_TRENDS))
        .group_by(Item.source_key, Item.outlet_id)).all()}


def comparable_pairs(s: Session | None, country_id: int | None, span_start: date, span_end_week: date,
                     spans: dict | None = None) -> set[tuple[str, int]]:
    """source|outlet pairs collecting across the whole span: first article on or before span_start, last
    article on or after span_end_week - 14 days (so a pair is not dropped for a quiet fortnight).
    The one rule behind the gap scores, the Trends bars and their article lists. An empty set means
    nothing qualifies yet, and callers then count every source."""
    spans = pair_spans(s, country_id) if spans is None else spans
    end = span_end_week - PAIR_END_GRACE
    return {k for k, (lo, hi) in spans.items() if lo <= span_start and hi >= end}


def coverage_start(s: Session, country_id: int) -> date | None:
    """First full week of coverage we can compare over time (cold start): from relevant articles counted
    once, of the sources trends use. Baselines never reach back before it."""
    first = s.scalar(select(func.min(Item.published_at)).where(
        Item.country_id == country_id, Item.kind == "article", Item.relevant.is_(True), Item.duplicate_of.is_(None),
        Item.source_key.not_in(NOT_FOR_TRENDS | {"user"})))
    return week_start(first.date()) + timedelta(weeks=1) if first else None


def trend_window(current_week: date, start_floor: date | None = None) -> tuple[date, date, date]:
    """(first shown week, last shown complete week, span start) of the Trends page. current_week holds
    today. The span reaches back to the first shown week's baseline, never before collection began."""
    end = current_week - timedelta(weeks=1)
    first = end - timedelta(weeks=TREND_WEEKS - 1)
    span_start = first - timedelta(weeks=BASELINE_REACH)
    return first, end, max(span_start, start_floor) if start_floor else span_start


_BASIS_CACHE: dict[int, tuple] = {}


def trend_basis(s: Session, country_id: int, current_week: date | None = None):
    """((first, end, span_start), pairs) for the Trends page. current_week defaults to the latest scored
    week, so the page, its article lists and the stored scores count the same outlets. Kept until the
    next recompute: the bars and the article list behind a bar then always use the same set."""
    current_week = current_week or s.scalar(select(func.max(CellWeek.week_start)).where(
        CellWeek.country_id == country_id)) or week_start(date.today())
    stamp = s.scalar(select(CellWeek.computed_at).where(CellWeek.country_id == country_id)
                     .order_by(CellWeek.id.desc()).limit(1))
    key = (current_week, stamp)
    hit = _BASIS_CACHE.get(country_id)
    if stamp and hit and hit[0] == key:
        return hit[1]
    window = trend_window(current_week, coverage_start(s, country_id))
    out = (window, frozenset(comparable_pairs(s, country_id, window[2], window[1])))
    if stamp:
        _BASIS_CACHE[country_id] = (key, out)
    return out


def capped_pageviews(s: Session, country_id: int, start: date, end: date) -> dict[int, float]:
    """Pageview item id -> views counted, for the days a title spiked: a day counts at most
    PAGEVIEW_SPIKE_CAP times the median of the title's previous 28 days (when 7 of them exist), so a
    one-day burst of automated traffic does not read as interest. Item.value keeps the raw count."""
    rows = s.execute(select(Item.id, Item.dedupe_key, Item.published_at, Item.value).where(
        Item.country_id == country_id, Item.kind == "pageview",
        Item.published_at >= _dt(start - timedelta(days=SPIKE_DAYS)), Item.published_at < _dt(end))).all()
    series = defaultdict(list)
    for iid, key, pub, v in rows:
        series[key.rsplit(":", 1)[0]].append((pub.date(), v or 0.0, iid))
    out = {}
    for pts in series.values():
        pts.sort()
        days = [p[0] for p in pts]
        for i, (d, v, iid) in enumerate(pts):
            prev = [p[1] for p in pts[bisect_left(days, d - timedelta(days=SPIKE_DAYS)):i]]
            if len(prev) >= SPIKE_MIN_DAYS:
                cap = settings.PAGEVIEW_SPIKE_CAP * max(statistics.median(prev), 1.0)
                if v > cap:
                    out[iid] = cap
    return out


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
            lenses: tuple[str, ...] | None = None, now: date | None = None) -> int:
    """Score `weeks` weeks ending with the week of `today`. `now` (default today) is the real date:
    weeks from its week on, and weeks whose daily need data has not reached their last day, are in
    progress and get no gap."""
    today = today or date.today()
    now = now or today
    last = week_start(today)
    first = last - timedelta(weeks=weeks - 1)
    history_from = first - timedelta(weeks=settings.WINDOW_WEEKS + 12)
    by_id, ancestors = _region_tree(s, country_id)
    # Coverage history only exists from the first collected article: baselines must not
    # reach back before it (cold start), or every theme looks over-covered.
    cov_start = coverage_start(s, country_id)
    collection_start = cov_start or today
    national = next(r for r in by_id.values() if r.level == "national")
    current = week_start(now)
    # Daily need (pageviews) lags coverage by a day or two: a week counts as complete once its need
    # data reaches the week's last day. Until then coverage is also cut at that day.
    last_need = s.scalar(select(func.max(Item.published_at)).where(
        Item.country_id == country_id, Item.kind == "pageview", Item.published_at < _dt(now + timedelta(days=1))))
    need_end = last_need.date() if last_need else None

    def in_progress(wk: date, lens: str) -> bool:
        return wk >= current or bool(LENSES[lens].get("daily") and need_end and wk + timedelta(days=6) > need_end)

    # Comparisons over time only count source|outlet pairs collecting across the whole compared span,
    # so adding Google Alerts or a feed (or Google News finding outlets only for recent weeks) does not
    # read as more coverage. Weeks the Trends page shows all use the page's own set, so its bars, the
    # usual level and the verdicts count the same outlets. Older weeks use their own 16-week span.
    spans = pair_spans(s, country_id)
    tw_first, tw_end, tw_from = trend_window(current, cov_start)
    trend_keep = comparable_pairs(None, None, tw_from, tw_end, spans=spans) or None
    keeps: dict[date, set | None] = {}

    def keep_for(wk: date) -> set | None:
        if wk >= tw_first:
            return trend_keep
        if wk not in keeps:
            lo = wk - timedelta(weeks=BASELINE_REACH)
            keeps[wk] = comparable_pairs(None, None, max(lo, cov_start) if cov_start else lo, wk, spans=spans) or None
        return keeps[wk]

    def counted(pairs: Counter, keep: set | None) -> int:
        return sum(v for k, v in pairs.items() if keep is None or k in keep)
    themes = s.scalars(select(Theme).where(Theme.active.is_(True))).all()
    dims = _outlet_dims(s)
    capped = capped_pageviews(s, country_id, history_from, last + timedelta(days=7))

    # ---- load items once: (week, theme, region) -> aggregates
    rows = s.execute(
        select(Item.id, Item.kind, Item.published_at, Item.lang, Item.outlet_id, Item.source_key, Item.value,
               ItemTheme.theme_id)
        .join(ItemTheme, and_(ItemTheme.item_id == Item.id, ItemTheme.active.is_(True)))
        .where(Item.country_id == country_id, Item.relevant.is_(True), Item.duplicate_of.is_(None),
               Item.published_at >= _dt(history_from), Item.published_at < _dt(last + timedelta(days=7)))
    ).all()
    item_regions: dict[int, list[int]] = defaultdict(list)
    ids = {r.id for r in rows}
    for ir in s.scalars(select(ItemRegion).where(ItemRegion.active.is_(True))):
        if ir.item_id in ids:
            item_regions[ir.item_id].append(ir.region_id)

    weekly_cov: dict[tuple, CoverageAgg] = defaultdict(CoverageAgg)
    weekly_need: dict[tuple, dict] = defaultdict(lambda: defaultdict(float))  # (wk,theme,region) -> lens -> value
    weekly_raw: dict[tuple, dict] = defaultdict(lambda: defaultdict(float))   # same, before the spike cap
    weekly_lang: dict[tuple, dict] = defaultdict(lambda: defaultdict(Counter))  # (wk,theme,region) -> lens -> lang
    for r in rows:
        day = r.published_at.date()
        wk = week_start(day)
        regs = {national.id}
        for rid in item_regions.get(r.id, []):
            regs.update(ancestors(rid))
        if r.kind == "article":
            d = dims.get(r.outlet_id, {})
            pair = (r.source_key, r.outlet_id)
            for reg in regs:
                a = weekly_cov[(wk, r.theme_id, reg)]
                a.total += 1
                a.lang[r.lang or "und"] += 1
                a.scope[d.get("scope", "unknown")] += 1
                a.alignment[d.get("alignment", "unknown")] += 1
                a.source[r.source_key] += 1
                a.pairs[pair] += 1
                if need_end and day > need_end:
                    a.late[pair] += 1
                if reg == national.id and not item_regions.get(r.id):
                    a.unplaced += 1
        else:
            v = capped.get(r.id, r.value)
            for lens, cfg in LENSES.items():
                if r.kind in cfg["kinds"]:
                    for reg in regs:
                        k = (wk, r.theme_id, reg)
                        weekly_need[k][lens] += v
                        weekly_raw[k][lens] += r.value
                        weekly_lang[k][lens][r.lang or "und"] += v

    def window(wk_end: date, theme_id, region_id):
        agg, need, raw = CoverageAgg(), defaultdict(float), defaultdict(float)
        for i in range(settings.WINDOW_WEEKS):
            k = (wk_end - timedelta(weeks=i), theme_id, region_id)
            c = weekly_cov.get(k)
            if c:
                agg.total += c.total
                agg.lang.update(c.lang)
                agg.scope.update(c.scope)
                agg.alignment.update(c.alignment)
                agg.source.update(c.source)
                agg.pairs.update(c.pairs)
                agg.late.update(c.late)
                agg.unplaced += c.unplaced
            for lens, v in weekly_need.get(k, {}).items():
                need[lens] += v
            for lens, v in weekly_raw.get(k, {}).items():
                raw[lens] += v
        return agg, need, raw

    lenses = lenses or tuple(LENSES)
    s.execute(delete(CellWeek).where(CellWeek.country_id == country_id, CellWeek.week_start >= first,
                                     CellWeek.week_start <= last, CellWeek.lens.in_(lenses)))
    n = 0
    region_ids = [r.id for r in by_id.values()]
    wk = first
    while wk <= last:
        keep = keep_for(wk)
        cur = {(t.id, rid): window(wk, t.id, rid) for t in themes for rid in region_ids}
        prev = {(t.id, rid): window(wk - timedelta(weeks=settings.WINDOW_WEEKS), t.id, rid)
                for t in themes for rid in region_ids}
        for lens in lenses:
            cfg = LENSES[lens]
            ip = in_progress(wk, lens)
            cut = ip and cfg.get("daily") and need_end is not None
            # pooled reference for national cells: all themes nationally (each theme's articles
            # against each theme's need, so the gaps balance out across themes)
            nat_cov = sum(counted(cur[(t.id, national.id)][0].pairs, keep) for t in themes)
            nat_need = sum(cur[(t.id, national.id)][1][lens] for t in themes)
            pooled_nat = nat_cov / nat_need if nat_need else None
            for t in themes:
                theme_nat_agg, theme_nat_need, _ = cur[(t.id, national.id)]
                theme_ref = (counted(theme_nat_agg.pairs, keep) / theme_nat_need[lens]) if theme_nat_need[lens] else None
                for rid in region_ids:
                    reg = by_id[rid]
                    if reg.level not in cfg["levels"]:
                        continue
                    agg, need, raw = cur[(t.id, rid)]
                    pagg, pneed, _ = prev[(t.id, rid)]
                    if need[lens] == 0 and agg.total == 0 and reg.level != "national":
                        continue  # keep the table small: empty regional cells are implicit
                    scored_cov = counted(agg.pairs, keep) - (counted(agg.late, keep) if cut else 0)
                    baseline_windows = 0
                    if cfg["reference"] == "own_history":
                        hc = hn = 0.0
                        for i in range(1, 4):
                            w_end = wk - timedelta(weeks=settings.WINDOW_WEEKS * i)
                            if w_end - timedelta(weeks=settings.WINDOW_WEEKS - 1) < collection_start:
                                continue  # window starts before collection began
                            a2, n2, _ = window(w_end, t.id, rid)
                            hc += counted(a2.pairs, keep)
                            hn += n2[lens]
                            baseline_windows += 1
                        ref = hc / hn if hn else None
                    else:
                        ref = pooled_nat if reg.level == "national" else theme_ref
                    partial = wk - timedelta(weeks=settings.WINDOW_WEEKS - 1) < collection_start
                    building = partial or (cfg["reference"] == "own_history" and baseline_windows == 0)
                    sc = score_cell(scored_cov, need[lens], ref)
                    if ip or building:  # still coming in, or the window/baseline predates collection
                        sc = Score(sc.ratio, sc.ref_ratio, None, True, sc.expected,
                                   "in_progress" if ip else "building_baseline")
                    # coverage-drop flag: both windows counted on the same comparable pairs
                    prev_ok = (wk - timedelta(weeks=2 * settings.WINDOW_WEEKS - 1)) >= collection_start
                    flags = coverage_flags(agg, counted(pagg.pairs, keep) if prev_ok else 0, need[lens], pneed[lens],
                                           cur_comparable=scored_cov)
                    if ip:  # a week still coming in always looks like a drop
                        flags = [f for f in flags if f != "coverage_drop"]
                    k = (wk, t.id, rid)
                    need_week = weekly_need.get(k, {}).get(lens, 0.0)
                    wcov = weekly_cov.get(k)
                    used = {p for p in agg.pairs if keep is None or p in keep}
                    s.add(CellWeek(
                        country_id=country_id, theme_id=t.id, region_id=rid, week_start=wk, lens=lens,
                        need=need[lens], coverage=agg.total, ratio=sc.ratio, ref_ratio=sc.ref_ratio, gap=sc.gap,
                        insufficient=sc.insufficient, flags=flags,
                        breakdown={"lang": dict(agg.lang), "scope": dict(agg.scope),
                                   "alignment": dict(agg.alignment), "source": dict(agg.source),
                                   "unplaced": agg.unplaced, "prev_coverage": pagg.total,
                                   "prev_need": pneed[lens], "reference": cfg["reference"],
                                   "baseline_windows": baseline_windows, "partial_window": partial,
                                   "building_baseline": building,
                                   "in_progress": ip, "reason": sc.reason,
                                   "need_through": need_end.isoformat() if cut else None,
                                   "scored_coverage": scored_cov,
                                   "scored_sources": sorted({p[0] for p in used}),
                                   "scored_outlets": len(used),
                                   # the Trends chart reads these: articles in comparable pairs and
                                   # the articles the reference expects, per week and per window
                                   "articles_week": counted(wcov.pairs, keep) if wcov else 0,
                                   "articles_4w": scored_cov, "expected_4w": sc.expected,
                                   "need_week": need_week,
                                   "need_week_raw": weekly_raw.get(k, {}).get(lens, 0.0),
                                   "need_raw": raw[lens],
                                   "need_lang_week": dict(weekly_lang.get(k, {}).get(lens, {})),
                                   "expected_week": need_week * ref if ref is not None and need[lens] else None},
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
    kw.setdefault("now", today)  # every chunk judges 'in progress' against the real date
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
