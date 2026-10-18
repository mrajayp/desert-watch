"""Gap scoring. One cell per (theme, region, week, lens) over a 4-week rolling window.

  C          = stories in the window, from comparable source|outlet pairs only (a story found by two
               routes counts once, and counts when any of its copies' pairs is comparable)
  E          = ref * need                                 # articles the reference expects
  gap        = ln((E + A) / (C + A))                      # > 0: fewer articles than expected
             = ln(ref / shrunk), shrunk = (C + A) / (need + A / ref)

A (settings.PRIOR_ARTICLES) is a prior in articles for every lens, so small cells are pulled
towards "as expected" by the same amount whatever the need unit. A cell is judged only when
E >= settings.MIN_EXPECTED_ARTICLES and, on a pooled lens, need >= settings.MIN_NEED_UNITS[lens]
(one report or event is not a pattern, and E built on it can be anything).

The reference depends on the lens:
  * pooled       - the coverage/need ratio of the comparison set (nationally: the themes with any
                   need in the window, each theme's articles against its own need; for a region:
                   the theme's national figure). Used for events/humanitarian/journalist.
  * own_history  - the cell's own ratio over the previous 12 weeks. Used for the audience
                   and search lenses, because pageview totals depend on which Wikipedia articles
                   were chosen (and search lists on which words) and are not comparable across themes.
Every cell without a gap says why in breakdown.reason: in_progress (the week, or its need data,
has not ended), building_baseline, no_need_data, too_little_need or too_few_expected. The search
lens adds no_search_data (gtrends.flag_missing_weeks).

The calibrated verdict (CellWeek.verdict; stats.py, dispersions, cell_evidence, judge) asks whether the
shortfall is larger than chance would explain. Weekly counts are overdispersed, Var = mu + alpha mu^2,
with alpha per theme and lens. breakdown keys:
  alpha, alpha_weeks   the theme's dispersion on this lens and the complete national weeks it rests on
                       (the last 52: this run's cells plus the stored ones before it); on every cell
  variance             V, the window count's variance if nothing had changed
  p_low, p_high        P(X <= C) and P(X >= C) under V (negative binomial; Poisson at the floor)
  se_g                 the standard error of gap; ratio_lo, ratio_hi: the 90% interval on exp(gap)
  chance               "1 in N" for the side the cell leans to (p_low when C <= E); null past p = 0.2
  new_short            short this week and not the week before (the digest's new gaps)
verdict: short | over | usual | possibly_short for a judged cell, decided per lens-week family
(national cells together, each district level its own family) by Benjamini-Hochberg at settings.FDR_Q
with the practical floor settings.MIN_SHORTFALL; unclear when E < MIN_EXPECTED_ARTICLES (reason
too_few_expected), alpha rests on fewer than ALPHA_UNCLEAR_WEEKS weeks, or the interval is wider than
MAX_INTERVAL_RATIO; null when there is nothing to judge (in_progress, no_need_data, ...). gap and
insufficient do not depend on the verdict.

Collection drift and basis honesty (settings DRIFT_*, BACKFILL_LAG_DAYS, DEPARTURE_WEEKS):
  baseline_backfilled  on every cell: an own-history cell whose 12 baseline weeks include a week that was
                       searched back for (backfilled_weeks: the median article first seen more than 14
                       days after publication). Such weeks hold fewer articles than live ones, so the
                       expected level runs low: the cell's SE_g gets drift_se added and its interval
                       widens. Pooled lenses compare themes within one window, so the flag is false there.
  drift_se             the widening (DRIFT_PER_WEEK x DRIFT_LAG_WEEKS, 0 when not backfilled); judged cells
  flag outlet_closed   a comparable pair belongs to an outlet an admin marked closed (Outlet.closed_on)
                       within the cell's compared span, and the cell counted its stories: the pair stays
                       in the basis (comparable_pairs), so the outlet's silence is a real drop, not a
                       retroactive change of outlet set. record_departures lists the pairs that did leave."""
import math
import statistics
from bisect import bisect_left
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

from sqlalchemy import and_, case, delete, func, select
from sqlalchemy.orm import Session

from . import settings
from .models import (BasisDeparture, CellWeek, Country, Item, ItemRegion, ItemTheme, Outlet, OutletCategory,
                     Region, Theme, utcnow)
from .stats import benjamini_hochberg, interval, nb_tail, one_in

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
    "search": {"kinds": ("search",), "reference": "own_history", "levels": ("national",),  # Google Trends, see gtrends.py
               "unit": "search index"},
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
# A week whose daily need data stops short of its last day waits this long past its end for the rest.
# After that it is judged on the days we have (coverage cut at the same day) and flagged need_incomplete,
# so a stalled collector cannot leave every later week 'still coming in'.
NEED_WAIT = timedelta(days=7)
NEED_TITLES_DAYS = 28                                 # titles read this recently decide where need data ends


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


def need_floor(lens: str) -> float:
    """The need a window must reach before a cell is judged. Pooled lenses only: their reference
    comes from other themes, so a cell resting on one report would read as many times short.
    Own-history lenses have no floor (the prior and the expected-articles rule do the job)."""
    return settings.MIN_NEED_UNITS.get(lens, 0) if LENSES[lens]["reference"] == "pooled" else 0


def score_cell(coverage: float, need: float, ref_ratio: float | None, *, prior: float | None = None,
               min_expected: float | None = None, min_need: float = 0) -> Score:
    prior = settings.PRIOR_ARTICLES if prior is None else prior
    min_expected = settings.MIN_EXPECTED_ARTICLES if min_expected is None else min_expected
    ratio = coverage / need if need else None
    if not need or ref_ratio is None:
        return Score(ratio, ref_ratio, None, True, None, "no_need_data")
    expected = ref_ratio * need
    if need < min_need:
        return Score(ratio, ref_ratio, None, True, expected, "too_little_need")
    if expected < min_expected:
        return Score(ratio, ref_ratio, None, True, expected, "too_few_expected")
    return Score(ratio, ref_ratio, math.log((expected + prior) / (coverage + prior)), False, expected)


# ---------------------------------------------------------------- calibrated verdict
VERDICTS = ("short", "over", "usual", "possibly_short", "unclear")
EVIDENCE_KEYS = ("variance", "p_low", "p_high", "se_g", "ratio_lo", "ratio_hi", "chance", "new_short", "drift_se")


def alpha_pair(b: dict | None) -> tuple[float, float] | None:
    """(stories counted, expectation) of one complete national week, for the dispersion estimate: the
    week's articles_week against the expected_week its own baseline gave it. None when the week is
    still coming in, predates collection, was cut at its last need day, or expects fewer than one
    article (a moment estimate on a mean below 1 is noise)."""
    if not b or b.get("in_progress") or b.get("building_baseline") or b.get("need_through"):
        return None
    mu = b.get("expected_week")
    if mu is None or mu < 1:
        return None
    return float(b.get("articles_week") or 0), float(mu)


def dispersion_hat(weeks) -> tuple[float | None, int]:
    """(alpha_hat, m): the moment estimate of a theme's dispersion from its (count, expectation) weeks,
    the mean of ((c - mu)^2 - mu) / mu^2 over the m weeks with mu >= 1, clipped to [ALPHA_MIN, ALPHA_MAX]."""
    used = [(c, mu) for c, mu in weeks if mu >= 1]
    if not used:
        return None, 0
    a = sum(((c - mu) ** 2 - mu) / (mu * mu) for c, mu in used) / len(used)
    return min(max(a, settings.ALPHA_MIN), settings.ALPHA_MAX), len(used)


def dispersions(by_theme: dict) -> tuple[dict, float]:
    """One lens: theme key -> (alpha, weeks used) from each theme's weeks, and the lens-wide alpha.
    The lens-wide alpha is the median of the estimates resting on ALPHA_MIN_WEEKS weeks or more
    (ALPHA_SEED until one does). A theme with enough weeks is shrunk to it with weight ALPHA_SHRINK_WEEKS,
    alpha = (m alpha_hat + 12 alpha_lens) / (m + 12); with fewer weeks it takes the lens-wide alpha."""
    hats = {k: dispersion_hat(w) for k, w in by_theme.items()}
    good = [a for a, m in hats.values() if a is not None and m >= settings.ALPHA_MIN_WEEKS]
    lens_alpha = statistics.median(good) if good else settings.ALPHA_SEED
    w = settings.ALPHA_SHRINK_WEEKS
    out = {}
    for k, (a, m) in hats.items():
        enough = a is not None and m >= settings.ALPHA_MIN_WEEKS
        out[k] = ((m * a + w * lens_alpha) / (m + w) if enough else lens_alpha, m)
    return out, lens_alpha


def cell_evidence(expected: float, stories: float, alpha: float, mu_weeks, baseline_counts, *,
                  prior: float | None = None, z: float | None = None, drift_se: float = 0.0) -> dict:
    """The tail probabilities and the interval of one judged cell, C stories against E expected:
      V      = E + alpha * sum_W mu_w^2 + E^2 * s_E^2    the window count's variance if nothing changed
      s_E^2  = (H + alpha * sum_B c_b^2) / H^2            the baseline ratio's relative variance, H = sum_B c_b
      p_low  = P(X <= C), p_high = P(X >= C)              stats.nb_tail under V
      SE_g^2 = 1 / (C + A) + alpha * sum_W mu_w^2 / E^2 + s_E^2 (E / (E + A))^2
                                                          delta method on g = ln((E + A) / (C + A)) under the
                                                          same variance model as V, so the interval and the
                                                          tail agree (the proposal wrote the middle term as
                                                          alpha, the weekly dispersion put on the 4-week sum)
      SE_g  += drift_se                                   a baseline on backfilled weeks (settings.DRIFT_*):
                                                          added, not in quadrature, since the drift is a bias
                                                          of known direction rather than noise; the stored
                                                          se_g is the widened one and drift_se says by how much
      ratio_lo, ratio_hi = exp(g -/+ z SE_g)              the 90% interval on exp(g), "N times fewer"
      chance = "1 in N" on the side the cell leans to (p_low when C <= E, else p_high); None past 0.2
    mu_weeks: the expectation of each window week (they sum to E). baseline_counts: the weekly stories
    the reference rests on (the cell's own 12 weeks; on a pooled lens the pool's window nationally, the
    theme's national window for a district). The tails (p_low, p_high) never move with drift_se: the
    verdict is the same, only the margin the page quotes is wider."""
    A = settings.PRIOR_ARTICLES if prior is None else prior
    z = settings.INTERVAL_Z if z is None else z
    E, C = float(expected), float(stories)
    H = float(sum(baseline_counts))
    s_e2 = (H + alpha * sum(c * c for c in baseline_counts)) / (H * H) if H > 0 else 0.0
    shape = sum(mu * mu for mu in mu_weeks)        # sum_W mu_w^2: E^2 / 4 when the window's weeks are alike
    V = E + alpha * shape + E * E * s_e2
    p_low, p_high = nb_tail(E, V, C)
    g = math.log((E + A) / (C + A))
    se = math.sqrt(1.0 / (C + A) + alpha * shape / (E * E) + s_e2 * (E / (E + A)) ** 2) + drift_se
    lo, hi = interval(g, se, z)
    return {"variance": round(V, 2), "p_low": round(p_low, 6), "p_high": round(p_high, 6), "se_g": round(se, 4),
            "ratio_lo": round(lo, 3), "ratio_hi": round(hi, 3), "chance": one_in(p_low if g >= 0 else p_high),
            "drift_se": round(drift_se, 4)}


def judge(cells, *, q: float | None = None, min_shortfall: float | None = None) -> list[str]:
    """Verdicts for one family: the judged cells of one lens, week and region level (national cells
    together; each district level its own family). Each cell maps gap, p_low, p_high, se_g, alpha_weeks.
      unclear         alpha rests on fewer than ALPHA_UNCLEAR_WEEKS weeks, or exp(z SE_g) > MAX_INTERVAL_RATIO
      short           p_low rejected by Benjamini-Hochberg at q across the clear cells, and exp(gap) >= MIN_SHORTFALL
      over            p_high rejected and exp(gap) <= 1 / MIN_SHORTFALL
      possibly_short  p_low < q but not rejected (a rejected cell below the floor reads usual)
      usual           everything else"""
    q = settings.FDR_Q if q is None else q
    floor = settings.MIN_SHORTFALL if min_shortfall is None else min_shortfall
    clear = [i for i, c in enumerate(cells)
             if (c.get("alpha_weeks") or 0) >= settings.ALPHA_UNCLEAR_WEEKS
             and math.exp(settings.INTERVAL_Z * c["se_g"]) <= settings.MAX_INTERVAL_RATIO]
    low = benjamini_hochberg([cells[i]["p_low"] for i in clear], q)
    high = benjamini_hochberg([cells[i]["p_high"] for i in clear], q)
    out = ["unclear"] * len(cells)
    for j, i in enumerate(clear):
        c = cells[i]
        ratio = math.exp(c["gap"])
        if low[j] and ratio >= floor:
            out[i] = "short"
        elif high[j] and ratio <= 1.0 / floor:
            out[i] = "over"
        elif c["p_low"] < q and not low[j]:
            out[i] = "possibly_short"
        else:
            out[i] = "usual"
    return out


@dataclass
class CoverageAgg:
    total: int = 0
    lang: Counter = field(default_factory=Counter)
    scope: Counter = field(default_factory=Counter)
    alignment: Counter = field(default_factory=Counter)
    source: Counter = field(default_factory=Counter)
    # (frozenset of the story's (source, outlet_id) pairs across its copies, lang) -> stories. A story
    # counts in a comparison when any copy's pair is comparable (see load_stories).
    pairs: Counter = field(default_factory=Counter)
    late: Counter = field(default_factory=Counter)    # same keys -> stories after the last need day
    unplaced: int = 0


def counted_in(pairs: Counter, keep: set | frozenset | None) -> int:
    """Stories in a CoverageAgg.pairs (or .late) counter whose pair set meets `keep` (None: every story)."""
    return sum(v for (ps, _), v in pairs.items() if keep is None or not keep.isdisjoint(ps))


def not_recurring():
    """SQL: the item is not a recurring post (recurring.mark_recurring sets extra.recurring on daily
    exchange rates, weather, prayer times...). Part of the counted-item predicate everywhere."""
    return func.coalesce(func.json_extract(Item.extra, "$.recurring"), 0) == 0


def counted_items(country_id: int):
    """The one predicate behind every count of coverage: relevant, the kept copy of its story, not a
    recurring post. Used by scoring, the Trends bars, the article lists and the digest."""
    return (Item.country_id == country_id, Item.relevant.is_(True), Item.duplicate_of.is_(None), not_recurring())


@dataclass(slots=True)
class StoryRow:
    """One counted story (or one need reading), dated and sourced by its kept copy. ids: every copy."""
    id: int
    kind: str
    published_at: datetime
    lang: str | None
    outlet_id: int | None
    source_key: str
    value: float
    themes: frozenset
    pairs: frozenset
    ids: tuple


COPY_MARGIN = timedelta(days=2)   # a duplicate copy is published within a day of the kept one (dedupe.py)


def load_stories(s: Session, country_id: int, start: date, end: date, *, kinds: tuple[str, ...] | None = None,
                 region_ids: list[int] | None = None) -> list[StoryRow]:
    """Counted items published in [start, end), one row per story. A story's theme links and
    source|outlet pairs are the union across its copies: the feed copy is kept (dedupe.py) while the
    Google News copy's pair may be the one that is comparable over time, and the story must count
    once whichever copy is kept. Items with no active theme link on any copy are left out. With
    region_ids, only stories any copy of which is tagged with one of them."""
    q = (select(Item.id, Item.kind, Item.published_at, Item.lang, Item.outlet_id, Item.source_key, Item.value,
                ItemTheme.theme_id)
         .outerjoin(ItemTheme, and_(ItemTheme.item_id == Item.id, ItemTheme.active.is_(True)))
         .where(*counted_items(country_id), Item.published_at >= _dt(start), Item.published_at < _dt(end)))
    if kinds:
        q = q.where(Item.kind.in_(kinds))
    stories: dict[int, list] = {}
    for r in s.execute(q):
        st = stories.get(r.id)
        if st is None:
            st = stories[r.id] = [r, set(), set(), [r.id]]   # row, themes, pairs, ids
        if r.theme_id is not None:
            st[1].add(r.theme_id)
    if stories:
        cq = (select(Item.id, Item.duplicate_of, Item.source_key, Item.outlet_id, ItemTheme.theme_id)
              .outerjoin(ItemTheme, and_(ItemTheme.item_id == Item.id, ItemTheme.active.is_(True)))
              .where(Item.country_id == country_id, Item.kind == "article", Item.relevant.is_(True),
                     Item.duplicate_of.is_not(None), Item.published_at >= _dt(start) - COPY_MARGIN,
                     Item.published_at < _dt(end) + COPY_MARGIN))
        for c in s.execute(cq):
            st = stories.get(c.duplicate_of)
            if st is None:
                continue
            if c.outlet_id is not None:
                st[2].add((c.source_key, c.outlet_id))
            if c.theme_id is not None:
                st[1].add(c.theme_id)
            if c.id not in st[3]:
                st[3].append(c.id)
    placed = None
    if region_ids is not None:
        ids = [i for st in stories.values() for i in st[3]]
        placed = set()
        for i in range(0, len(ids), 900):   # SQLite's variable limit
            placed.update(s.scalars(select(ItemRegion.item_id).where(
                ItemRegion.item_id.in_(ids[i:i + 900]), ItemRegion.region_id.in_(region_ids), ItemRegion.active.is_(True))))
    out = []
    for r, themes, pairs, ids in stories.values():
        if not themes or (placed is not None and placed.isdisjoint(ids)):
            continue
        if r.kind == "article" and r.outlet_id is not None:
            pairs.add((r.source_key, r.outlet_id))
        out.append(StoryRow(r.id, r.kind, r.published_at, r.lang, r.outlet_id, r.source_key, r.value,
                            frozenset(themes), frozenset(pairs), tuple(ids)))
    return out


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
    """First and last article day of every source|outlet pair that may count in comparisons over time.
    Every copy of a story counts here: a Google News pair whose recent copies are all duplicates of the
    outlet's feed is still collecting, and must not drop out of the whole basis."""
    return {(src, oid): (lo.date(), hi.date()) for src, oid, lo, hi in s.execute(
        select(Item.source_key, Item.outlet_id, func.min(Item.published_at), func.max(Item.published_at))
        .where(Item.country_id == country_id, Item.kind == "article", Item.relevant.is_(True),
               Item.outlet_id.is_not(None), Item.source_key.not_in(NOT_FOR_TRENDS))
        .group_by(Item.source_key, Item.outlet_id)).all()}


def closed_outlets(s: Session) -> dict[int, date]:
    """Outlet id -> the day an admin marked it closed (Outlet.closed_on)."""
    return dict(s.execute(select(Outlet.id, Outlet.closed_on).where(Outlet.closed_on.is_not(None))).all())


def comparable_pairs(s: Session | None, country_id: int | None, span_start: date, span_end_week: date,
                     spans: dict | None = None, closed: dict | None = None) -> set[tuple[str, int]]:
    """source|outlet pairs collecting across the whole span: first article on or before span_start, last
    article on or after span_end_week - 14 days (so a pair is not dropped for a quiet fortnight).
    The one rule behind the gap scores, the Trends bars and their article lists. An empty set means
    nothing qualifies yet, and callers then count every source.
    An outlet an admin marked closed (`closed`: outlet id -> closed_on, closed_outlets) keeps its pairs
    whatever its last article day: its stories count up to the closure and its silence after it is a
    real drop in the comparison (compute flags such cells outlet_closed), where a pair that simply
    stops is removed from every compared week and its loss never shows (record_departures lists those)."""
    spans = pair_spans(s, country_id) if spans is None else spans
    if closed is None:
        closed = closed_outlets(s) if s is not None else {}
    end = span_end_week - PAIR_END_GRACE
    return {k for k, (lo, hi) in spans.items() if lo <= span_start and (hi >= end or k[1] in closed)}


def backfilled_weeks(s: Session, country_id: int, start: date, end: date) -> set[date]:
    """Weeks in [start, end) that were searched back for rather than collected live: more than half of
    the week's counted articles (from the sources comparisons use) were first seen more than
    settings.BACKFILL_LAG_DAYS after publication, that is the week's median article came in late.
    Google News finds fewer articles for a week the older it is when asked (settings.DRIFT_PER_WEEK), so
    an expected level built on such weeks runs low; compute widens those cells' intervals. One grouped
    query, a row per day. A week with no article is not backfilled."""
    lag = func.julianday(Item.created_at) - func.julianday(Item.published_at)
    day = func.date(Item.published_at)
    rows = s.execute(select(day, func.sum(case((lag > settings.BACKFILL_LAG_DAYS, 1), else_=0)), func.count(Item.id))
                     .where(*counted_items(country_id), Item.kind == "article", Item.source_key.not_in(NOT_FOR_TRENDS),
                            Item.published_at >= _dt(start), Item.published_at < _dt(end))
                     .group_by(day)).all()
    late: Counter = Counter()
    total: Counter = Counter()
    for d, n_late, n in rows:
        wk = week_start(date.fromisoformat(str(d)[:10]))
        late[wk] += int(n_late or 0)
        total[wk] += int(n)
    return {wk for wk, n in total.items() if n and 2 * late[wk] > n}


def record_departures(s: Session, country_id: int | None = None, today: date | None = None) -> int:
    """Rewrite basis_departure (models.BasisDeparture) for each country: the source|outlet pairs that
    left the Trends basis in the last settings.DEPARTURE_WEEKS weeks. A pair leaves when its last article
    falls behind the grace fortnight before the last complete week (comparable_pairs); it is listed while
    that last article is within DEPARTURE_WEEKS weeks of the cut. Pairs that never qualified (first
    article after the span began) and closed outlets (kept in the basis) are not departures. Runs
    nightly (jobs.nightly); returns the number of pairs listed."""
    today = today or date.today()
    countries = [s.get(Country, country_id)] if country_id else list(s.scalars(select(Country)))
    closed = closed_outlets(s)
    n = 0
    for c in countries:
        s.execute(delete(BasisDeparture).where(BasisDeparture.country_id == c.id))
        _, end, span_start = trend_window(week_start(today), coverage_start(s, c.id))
        cut = end - PAIR_END_GRACE
        since = cut - timedelta(weeks=settings.DEPARTURE_WEEKS)
        rows = s.execute(select(Item.source_key, Item.outlet_id, func.min(Item.published_at), func.max(Item.published_at),
                                func.count(Item.id))
                         .where(Item.country_id == c.id, Item.kind == "article", Item.relevant.is_(True),
                                Item.outlet_id.is_not(None), Item.source_key.not_in(NOT_FOR_TRENDS))
                         .group_by(Item.source_key, Item.outlet_id)).all()
        for src, oid, lo, hi, cnt in rows:
            lo, hi = lo.date(), hi.date()
            if lo <= span_start and since <= hi < cut and oid not in closed:
                s.add(BasisDeparture(country_id=c.id, source_key=src, outlet_id=oid, first_day=lo, last_day=hi,
                                     articles=int(cnt), recorded_at=utcnow()))
                n += 1
    s.commit()
    return n


def coverage_start(s: Session, country_id: int) -> date | None:
    """First full week of coverage we can compare over time (cold start): from relevant articles counted
    once, of the sources trends use. Baselines never reach back before it."""
    first = s.scalar(select(func.min(Item.published_at)).where(
        *counted_items(country_id), Item.kind == "article", Item.source_key.not_in(NOT_FOR_TRENDS | {"user"})))
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


def need_end_day(s: Session, country_id: int, now: date) -> date | None:
    """The last day most Wikipedia titles have page views for, among titles read in the last 28 days.
    One title reaching a day does not end a week: on a night when only some titles came back, the rest
    would be missing their Sunday. Falls back to the latest day of any title after a long stall."""
    rows = s.execute(select(Item.dedupe_key, Item.published_at).where(
        Item.country_id == country_id, Item.kind == "pageview",
        Item.published_at >= _dt(now - timedelta(days=NEED_TITLES_DAYS)),
        Item.published_at < _dt(now + timedelta(days=1)))).all()
    last: dict[str, date] = {}
    for key, pub in rows:
        title = key.rsplit(":", 1)[0]
        last[title] = max(last.get(title, pub.date()), pub.date())
    if last:
        days = sorted(last.values())
        return days[(len(days) - 1) // 2]   # at least half the titles reach it
    latest = s.scalar(select(func.max(Item.published_at)).where(
        Item.country_id == country_id, Item.kind == "pageview", Item.published_at < _dt(now + timedelta(days=1))))
    return latest.date() if latest else None


def scored_articles(c: CellWeek) -> int:
    """The count a cell's gap was computed on: stories from comparable source|outlet pairs in its window
    (breakdown.articles_4w). Pages show it as `articles`, beside `articles_all` (every monitored source)."""
    b = c.breakdown or {}
    n = b.get("articles_4w", b.get("scored_coverage"))
    return int(c.coverage if n is None else n)


def latest_complete_week(s: Session, country_id: int, upto: date | None = None, *, reach: int = 12) -> date | None:
    """The latest scored week (on or before `upto`) whose national cells are all complete, none still
    coming in. Pages open on it and the weekly digest covers it."""
    q = select(CellWeek.week_start).where(CellWeek.country_id == country_id)
    if upto:
        q = q.where(CellWeek.week_start <= upto)
    weeks = s.scalars(q.distinct().order_by(CellWeek.week_start.desc()).limit(reach)).all()
    national = s.scalar(select(Region.id).where(Region.country_id == country_id, Region.level == "national"))
    for wk in weeks:
        cells = s.scalars(select(CellWeek.breakdown).where(CellWeek.country_id == country_id, CellWeek.week_start == wk,
                                                           CellWeek.region_id == national)).all()
        if cells and not any((b or {}).get("in_progress") for b in cells):
            return wk
    return None


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
    progress and get no gap (the latter for at most NEED_WAIT past the week's end)."""
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
    need_end = need_end_day(s, country_id, now)

    def need_short(wk: date, lens: str) -> bool:
        return bool(LENSES[lens].get("daily") and need_end and wk + timedelta(days=6) > need_end)

    def in_progress(wk: date, lens: str) -> bool:
        return wk >= current or (need_short(wk, lens) and now <= wk + timedelta(days=6) + NEED_WAIT)

    # Comparisons over time only count source|outlet pairs collecting across the whole compared span,
    # so adding Google Alerts or a feed (or Google News finding outlets only for recent weeks) does not
    # read as more coverage. Weeks the Trends page shows all use the page's own set, so its bars, the
    # usual level and the verdicts count the same outlets. Older weeks use their own 16-week span.
    spans = pair_spans(s, country_id)
    closed = closed_outlets(s)   # an admin's closure keeps the outlet's pairs in the basis (comparable_pairs)
    closed_pairs = {p: closed[p[1]] for p in spans if p[1] in closed}
    tw_first, tw_end, tw_from = trend_window(current, cov_start)
    trend_keep = comparable_pairs(None, None, tw_from, tw_end, spans=spans, closed=closed) or None
    keeps: dict[date, set | None] = {}

    def keep_for(wk: date) -> set | None:
        if wk >= tw_first:
            return trend_keep
        if wk not in keeps:
            lo = wk - timedelta(weeks=BASELINE_REACH)
            keeps[wk] = comparable_pairs(None, None, max(lo, cov_start) if cov_start else lo, wk, spans=spans,
                                         closed=closed) or None
        return keeps[wk]

    counted = counted_in
    themes = s.scalars(select(Theme).where(Theme.active.is_(True))).all()
    dims = _outlet_dims(s)
    capped = capped_pageviews(s, country_id, history_from, last + timedelta(days=7))
    # weeks searched back for (fewer articles than live weeks): a baseline resting on one gets a wider interval
    backfilled = backfilled_weeks(s, country_id, history_from, last + timedelta(days=7))
    drift = settings.DRIFT_PER_WEEK * settings.DRIFT_LAG_WEEKS

    # ---- load items once, one row per story: (week, theme, region) -> aggregates
    rows = load_stories(s, country_id, history_from, last + timedelta(days=7))
    # a place tag on any copy of a story places the story
    root_of = {i: r.id for r in rows for i in r.ids}
    item_regions: dict[int, set[int]] = defaultdict(set)
    for ir in s.scalars(select(ItemRegion).where(ItemRegion.active.is_(True))):
        root = root_of.get(ir.item_id)
        if root is not None:
            item_regions[root].add(ir.region_id)

    weekly_cov: dict[tuple, CoverageAgg] = defaultdict(CoverageAgg)
    weekly_need: dict[tuple, dict] = defaultdict(lambda: defaultdict(float))  # (wk,theme,region) -> lens -> value
    weekly_raw: dict[tuple, dict] = defaultdict(lambda: defaultdict(float))   # same, before the spike cap
    weekly_lang: dict[tuple, dict] = defaultdict(lambda: defaultdict(Counter))  # (wk,theme,region) -> lens -> lang
    for r in rows:
        day = r.published_at.date()
        wk = week_start(day)
        regs = {national.id}
        for rid in item_regions.get(r.id, ()):
            regs.update(ancestors(rid))
        if r.kind == "article":
            d = dims.get(r.outlet_id, {})
            lang = r.lang or "und"
            key = (r.pairs, lang)
            late = bool(need_end and day > need_end)
            for theme_id in r.themes:
                for reg in regs:
                    a = weekly_cov[(wk, theme_id, reg)]
                    a.total += 1
                    a.lang[lang] += 1
                    a.scope[d.get("scope", "unknown")] += 1
                    a.alignment[d.get("alignment", "unknown")] += 1
                    a.source[r.source_key] += 1
                    a.pairs[key] += 1
                    if late:
                        a.late[key] += 1
                    if reg == national.id and not item_regions.get(r.id):
                        a.unplaced += 1
        else:
            v = capped.get(r.id, r.value)
            for lens, cfg in LENSES.items():
                if r.kind in cfg["kinds"]:
                    for theme_id in r.themes:
                        for reg in regs:
                            k = (wk, theme_id, reg)
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
    region_ids = [r.id for r in by_id.values()]

    def weekly_counts(wk_end: date, theme_id, region_id, weeks: int, keep) -> list[int]:
        """Stories on the comparable pairs per week, over `weeks` weeks ending at wk_end, newest first."""
        out = []
        for i in range(weeks):
            c = weekly_cov.get((wk_end - timedelta(weeks=i), theme_id, region_id))
            out.append(counted(c.pairs, keep) if c else 0)
        return out

    def counted_closure(wk_end: date, theme_id, region_id, closing: set) -> bool:
        """Whether the cell counted a story from one of the closing pairs within its compared span (the
        window and the 12 weeks before it): then the outlet's silence is part of this cell's shortfall."""
        for i in range(BASELINE_REACH + 1):
            c = weekly_cov.get((wk_end - timedelta(weeks=i), theme_id, region_id))
            if c and any(not closing.isdisjoint(ps) for (ps, _) in c.pairs):
                return True
        return False

    # one record per cell: the CellWeek fields, plus the evidence inputs under keys starting with "_".
    # The rows are written after the verdicts, which need every cell of a lens-week and the dispersion
    # of every theme over the run (the session held the same objects before the commit as it does now).
    pending: list[dict] = []
    wk = first
    while wk <= last:
        keep = keep_for(wk)
        # comparable pairs of outlets that closed inside this week's compared span: their loss is real,
        # and the cells that counted them say so (flag outlet_closed)
        closing = {p for p, d in closed_pairs.items() if (keep is None or p in keep)
                   and wk - timedelta(weeks=BASELINE_REACH) <= d <= wk + timedelta(days=6)}
        cur = {(t.id, rid): window(wk, t.id, rid) for t in themes for rid in region_ids}
        prev = {(t.id, rid): window(wk - timedelta(weeks=settings.WINDOW_WEEKS), t.id, rid)
                for t in themes for rid in region_ids}
        for lens in lenses:
            cfg = LENSES[lens]
            ip = in_progress(wk, lens)
            cut = need_short(wk, lens)  # still waiting, or judged on the days we have after NEED_WAIT
            floor = need_floor(lens)
            # pooled reference for national cells: the themes with any need nationally in this window
            # (each theme's articles against its own need, so the gaps balance out across them). A
            # theme with no need adds no articles: 13 themes' coverage over one theme's report would
            # make that theme look many times short.
            pool_ids = [t.id for t in themes if cur[(t.id, national.id)][1][lens] > 0]
            pool = [cur[(tid, national.id)][:2] for tid in pool_ids]
            nat_cov = sum(counted(p_agg.pairs, keep) for p_agg, _ in pool)
            nat_need = sum(p_need[lens] for _, p_need in pool)
            pooled_nat = nat_cov / nat_need if nat_need else None
            # the pool's weekly stories: the baseline every national cell of a pooled lens rests on
            pool_weekly = [c for tid in pool_ids for c in weekly_counts(wk, tid, national.id, settings.WINDOW_WEEKS, keep)]
            for t in themes:
                theme_nat_agg, theme_nat_need, _ = cur[(t.id, national.id)]
                theme_ref = (counted(theme_nat_agg.pairs, keep) / theme_nat_need[lens]) if theme_nat_need[lens] else None
                theme_nat_weekly = None   # the theme's national window by week: a district cell's baseline
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
                    base_backfilled = False   # an own-history baseline resting on a week searched back for
                    if cfg["reference"] == "own_history":
                        hc = hn = 0.0
                        baseline_counts: list[int] = []
                        for i in range(1, 4):
                            w_end = wk - timedelta(weeks=settings.WINDOW_WEEKS * i)
                            if w_end - timedelta(weeks=settings.WINDOW_WEEKS - 1) < collection_start:
                                continue  # window starts before collection began
                            a2, n2, _ = window(w_end, t.id, rid)
                            hc += counted(a2.pairs, keep)
                            hn += n2[lens]
                            baseline_windows += 1
                            baseline_counts += weekly_counts(w_end, t.id, rid, settings.WINDOW_WEEKS, keep)
                            base_backfilled = base_backfilled or any(
                                w_end - timedelta(weeks=j) in backfilled for j in range(settings.WINDOW_WEEKS))
                        ref = hc / hn if hn else None
                    elif reg.level == "national":
                        ref, baseline_counts = pooled_nat, pool_weekly
                    else:
                        if theme_nat_weekly is None:
                            theme_nat_weekly = weekly_counts(wk, t.id, national.id, settings.WINDOW_WEEKS, keep)
                        ref, baseline_counts = theme_ref, theme_nat_weekly
                    partial = wk - timedelta(weeks=settings.WINDOW_WEEKS - 1) < collection_start
                    building = partial or (cfg["reference"] == "own_history" and baseline_windows == 0)
                    sc = score_cell(scored_cov, need[lens], ref, min_need=floor)
                    if ip or building:  # still coming in, or the window/baseline predates collection
                        sc = Score(sc.ratio, sc.ref_ratio, None, True, sc.expected,
                                   "in_progress" if ip else "building_baseline")
                    # coverage-drop flag: both windows counted on the same comparable pairs
                    prev_ok = (wk - timedelta(weeks=2 * settings.WINDOW_WEEKS - 1)) >= collection_start
                    prev_scored = counted(pagg.pairs, keep) if prev_ok else None
                    flags = coverage_flags(agg, prev_scored or 0, need[lens], pneed[lens], cur_comparable=scored_cov)
                    # the scored stories by language (the all-source split is breakdown.lang)
                    scored_lang: Counter = Counter()
                    for (ps, lg), v in agg.pairs.items():
                        if keep is None or not keep.isdisjoint(ps):
                            scored_lang[lg] += v
                    if cut:
                        for (ps, lg), v in agg.late.items():
                            if keep is None or not keep.isdisjoint(ps):
                                scored_lang[lg] -= v
                    if ip:  # a week still coming in always looks like a drop
                        flags = [f for f in flags if f != "coverage_drop"]
                    elif cut:  # judged although its need data never reached the week's end
                        flags.append("need_incomplete")
                    if closing and counted_closure(wk, t.id, rid, closing):
                        flags.append("outlet_closed")
                    k = (wk, t.id, rid)
                    need_week = weekly_need.get(k, {}).get(lens, 0.0)
                    wcov = weekly_cov.get(k)
                    used = {p for (ps, _) in agg.pairs for p in ps if keep is None or p in keep}
                    # the expectation of each window week: the variance of the window count needs them
                    mu_weeks = [ref * weekly_need.get((wk - timedelta(weeks=i), t.id, rid), {}).get(lens, 0.0)
                                for i in range(settings.WINDOW_WEEKS)] if ref is not None else None
                    pending.append(dict(
                        country_id=country_id, theme_id=t.id, region_id=rid, week_start=wk, lens=lens,
                        need=need[lens], coverage=agg.total, ratio=sc.ratio, ref_ratio=sc.ref_ratio, gap=sc.gap,
                        insufficient=sc.insufficient, verdict=None, flags=flags,
                        _mu_weeks=mu_weeks, _baseline=baseline_counts, _level=reg.level,
                        _drift=drift if base_backfilled else 0.0,
                        breakdown={"lang": dict(agg.lang), "scope": dict(agg.scope),
                                   "alignment": dict(agg.alignment), "source": dict(agg.source),
                                   "unplaced": agg.unplaced, "prev_coverage": pagg.total,
                                   # the previous window on the same comparable pairs (None when it
                                   # predates collection): what the digest compares articles_4w with
                                   "prev_scored_coverage": prev_scored,
                                   "scored_lang": {k: v for k, v in scored_lang.items() if v},
                                   "prev_need": pneed[lens], "reference": cfg["reference"],
                                   "baseline_windows": baseline_windows, "partial_window": partial,
                                   "building_baseline": building,
                                   # the baseline rests on a week searched back for: the interval is widened
                                   "baseline_backfilled": base_backfilled,
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
                                   "expected_week": need_week * ref if ref is not None and need[lens] else None}))
        wk += timedelta(weeks=1)

    # ---- calibrate: each theme's dispersion on each lens from its last 52 complete national weeks (this
    # run's cells and the stored ones before `first`, which the run keeps), then the evidence of every
    # judged cell and the verdicts per lens-week family
    alpha_from = last - timedelta(weeks=settings.ALPHA_HISTORY_WEEKS - 1)
    pairs_by: dict[tuple, list] = defaultdict(list)
    for tid, lens, b in s.execute(select(CellWeek.theme_id, CellWeek.lens, CellWeek.breakdown).where(
            CellWeek.country_id == country_id, CellWeek.region_id == national.id, CellWeek.lens.in_(lenses),
            CellWeek.week_start >= alpha_from, CellWeek.week_start < first)):
        pr = alpha_pair(b)
        if pr:
            pairs_by[(tid, lens)].append(pr)
    for rec in pending:
        if rec["region_id"] == national.id and rec["week_start"] >= alpha_from:
            pr = alpha_pair(rec["breakdown"])
            if pr:
                pairs_by[(rec["theme_id"], rec["lens"])].append(pr)
    alphas: dict[tuple, tuple[float, int]] = {}
    for lens in lenses:
        alphas.update(dispersions({(t.id, lens): pairs_by.get((t.id, lens), []) for t in themes})[0])
    families: dict[tuple, list[dict]] = defaultdict(list)   # (week, lens, level) -> the judged cells
    for rec in pending:
        b = rec["breakdown"]
        alpha, m = alphas[(rec["theme_id"], rec["lens"])]
        b["alpha"], b["alpha_weeks"] = round(alpha, 4), m
        if rec["gap"] is not None:
            b.update(cell_evidence(b["expected_4w"], b["articles_4w"], alpha, rec["_mu_weeks"], rec["_baseline"],
                                   drift_se=rec["_drift"]))
            families[(rec["week_start"], rec["lens"], rec["_level"])].append(rec)
        elif b["reason"] == "too_few_expected":
            rec["verdict"] = "unclear"
    for recs in families.values():
        for rec, v in zip(recs, judge([{**rec["breakdown"], "gap": rec["gap"]} for rec in recs])):
            rec["verdict"] = v
    # new_short: short this week and not the week before. The records run week by week, so each week
    # reads the one before it; the first reads the stored week before the run.
    prev_verdict = {(tid, rid, lens): v for tid, rid, lens, v in s.execute(
        select(CellWeek.theme_id, CellWeek.region_id, CellWeek.lens, CellWeek.verdict).where(
            CellWeek.country_id == country_id, CellWeek.week_start == first - timedelta(weeks=1),
            CellWeek.lens.in_(lenses)))}
    for rec in pending:
        k = (rec["theme_id"], rec["region_id"], rec["lens"])
        if rec["gap"] is not None:
            rec["breakdown"]["new_short"] = rec["verdict"] == "short" and prev_verdict.get(k) != "short"
        prev_verdict[k] = rec["verdict"]
    for rec in pending:
        s.add(CellWeek(**{k: v for k, v in rec.items() if not k.startswith("_")}, computed_at=utcnow()))
    s.commit()
    return len(pending)


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
