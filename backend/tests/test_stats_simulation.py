"""Calibration of the verdict on simulated data: 13 themes x 104 weeks of negative-binomial weekly
counts (alpha in {0.05, 0.3, 1}) against a mild seasonal need series, scored by the functions compute()
uses (scoring.dispersions, cell_evidence, judge) on an own-history lens, the reference being the 12
weeks before the 4-week window. Marked `simulation`; the whole file runs in well under a minute."""
import math
import random
import time
from collections import defaultdict

import pytest

from app import scoring, settings

pytestmark = pytest.mark.simulation

THEMES, WEEKS = 13, 104
ALPHAS = (0.05, 0.3, 1.0)
# (alpha, articles a theme expects per 4-week window) of the 13 themes
PARAMS = ((0.05, 4), (0.05, 8), (0.05, 30), (0.05, 60), (0.05, 120), (0.05, 250),
          (0.3, 8), (0.3, 30), (0.3, 120), (0.3, 500),
          (1.0, 15), (1.0, 60), (1.0, 250))
W, B = settings.WINDOW_WEEKS, 3 * settings.WINDOW_WEEKS
FIRST = W + B - 1                                # the first week with a full baseline behind it
NEED = 1000.0
A = settings.PRIOR_ARTICLES


def poisson(rng, lam):
    if lam <= 0:
        return 0
    if lam > 400:   # a sum of smaller draws keeps exp(-lam) in range
        k = math.ceil(lam / 400)
        return sum(poisson(rng, lam / k) for _ in range(k))
    L, n, p = math.exp(-lam), 0, rng.random()
    while p > L:
        n += 1
        p *= rng.random()
    return n


def negbin(rng, mu, alpha):
    """Mean mu, variance mu + alpha mu^2: a Poisson whose rate is Gamma(1 / alpha, alpha mu)."""
    return poisson(rng, rng.gammavariate(1.0 / alpha, alpha * mu))


def need(w):
    return NEED * (1 + 0.15 * math.sin(2 * math.pi * w / 52))


def theme_params(t):
    """(alpha, articles per need unit) of theme t."""
    alpha, expected = PARAMS[t]
    return alpha, expected / (W * NEED)


def simulate(seed):
    rng = random.Random(seed)
    return [[negbin(rng, theme_params(t)[1] * need(w), theme_params(t)[0]) for w in range(WEEKS)]
            for t in range(THEMES)]


def cell(counts_t, w):
    """One theme's cell for the window ending at week w: (E, C, mu_weeks, baseline_counts)."""
    base = range(w - W - B + 1, w - W + 1)
    win = range(w - W + 1, w + 1)
    ref = sum(counts_t[i] for i in base) / sum(need(i) for i in base)
    mu = [ref * need(i) for i in win]
    return sum(mu), sum(counts_t[i] for i in win), mu, [counts_t[i] for i in base]


def expectations(counts):
    """expected_week per theme and week, as compute() stores it: the week's need at the reference the
    cell ending that week had."""
    return [[cell(counts[t], w)[2][-1] if w >= FIRST else None for w in range(WEEKS)] for t in range(THEMES)]


def score_week(counts, expect, w):
    """theme -> verdict for week w, the way compute() decides it: each theme's alpha from its last 52
    complete weeks, the evidence of every judged cell, then the family of the week."""
    lo = max(FIRST, w - settings.ALPHA_HISTORY_WEEKS + 1)
    alphas, _ = scoring.dispersions({t: [(counts[t][v], expect[t][v]) for v in range(lo, w + 1)] for t in range(THEMES)})
    judged, idx = [], []
    for t in range(THEMES):
        E, C, mu, base = cell(counts[t], w)
        if E < settings.MIN_EXPECTED_ARTICLES:
            continue
        ev = scoring.cell_evidence(E, C, alphas[t][0], mu, base)
        ev.update(gap=math.log((E + A) / (C + A)), alpha_weeks=alphas[t][1])
        judged.append(ev)
        idx.append(t)
    return dict(zip(idx, scoring.judge(judged)))


SEEDS = range(12)
JUDGED_FROM = FIRST + settings.ALPHA_MIN_WEEKS   # alpha rests on at least 12 weeks from here on


def test_false_short_rate_on_steady_data_stays_near_q():
    t0 = time.perf_counter()
    weeks = cells = weeks_with_short = short = possibly = 0
    for seed in SEEDS:
        counts = simulate(seed)
        expect = expectations(counts)
        for w in range(JUDGED_FROM, WEEKS):
            verdicts = score_week(counts, expect, w)
            weeks += 1
            cells += len(verdicts)
            n_short = sum(v == "short" for v in verdicts.values())
            short += n_short
            possibly += sum(v == "possibly_short" for v in verdicts.values())
            weeks_with_short += n_short > 0
            assert not any(v is None for v in verdicts.values())
    rate_weeks, rate_cells = weeks_with_short / weeks, short / cells
    print(f"\nsteady data: {weeks} lens-weeks, {cells} cells; a false short in {rate_weeks:.3f} of weeks, "
          f"{rate_cells:.4f} of cells; possibly_short on {possibly / cells:.3f} of cells; {time.perf_counter() - t0:.1f}s")
    assert rate_weeks <= 1.5 * settings.FDR_Q
    assert rate_cells <= settings.FDR_Q
    assert time.perf_counter() - t0 < 60


DROP_WEEKS = (30, 45, 60, 75, 90, 103)


def test_power_for_a_two_fold_drop_over_four_weeks():
    t0 = time.perf_counter()
    hits, trials = defaultdict(int), defaultdict(int)
    for seed in SEEDS:
        counts = simulate(seed)
        expect = expectations(counts)
        rng = random.Random(1000 + seed)
        for t in range(THEMES):
            alpha, rho = theme_params(t)
            E = PARAMS[t][1]
            if E < 30:
                continue
            for d in DROP_WEEKS:
                dropped = [row[:] for row in counts]
                for w in range(d - W + 1, d + 1):   # the drop halves the mean for the window's 4 weeks
                    dropped[t][w] = negbin(rng, rho * need(w) / 2, alpha)
                # the expectations of weeks up to d rest on weeks before the drop: unchanged
                v = score_week(dropped, expect, d).get(t)
                trials[(alpha, E)] += 1
                hits[(alpha, E)] += v == "short"
    power = {k: hits[k] / trials[k] for k in trials}
    print("\npower of a 2x drop (alpha, E): " + ", ".join(f"({a}, {e}) {power[(a, e)]:.2f}" for a, e in sorted(power)))
    by_alpha = {a: sum(hits[k] for k in hits if k[0] == a) / sum(trials[k] for k in trials if k[0] == a) for a in ALPHAS}
    print("by alpha: " + ", ".join(f"{a}: {p:.2f}" for a, p in sorted(by_alpha.items())))
    # What the design can see with one theme dropping among 13: Benjamini-Hochberg's bar for a lone
    # discovery is q / 13, and a near-Poisson theme's alpha is shrunk towards the lens median. A 2x drop
    # over 4 weeks is then seen about two times in three at E = 250 for a near-Poisson theme, one time
    # in three at E = 30..120, rarely at alpha = 0.3 and never at alpha = 1, whose weekly swing is as
    # large as the drop. The proposal's 0.8 at E >= 30 is not what this design delivers (the A-R2.1
    # report says so); these floors catch a regression, not a target.
    assert power[(0.05, 250)] >= 0.55 and power[(0.05, 120)] >= 0.3 and power[(0.05, 30)] >= 0.2
    assert power[(0.3, 120)] >= 0.1 and power[(0.3, 500)] >= 0.1
    assert all(p <= 0.2 for (a, e), p in power.items() if a == 1.0)
    assert time.perf_counter() - t0 < 60


def _family(cells):
    """Verdicts for one lens-week family: E, C, alpha and 12 steady baseline weeks per cell."""
    out = []
    for E, C, alpha, m in cells:
        mu = [E / W] * W
        base = [E / W] * B
        ev = scoring.cell_evidence(E, C, alpha, mu, base)
        ev.update(gap=math.log((E + A) / (C + A)), alpha_weeks=m)
        out.append(ev)
    return scoring.judge(out)


def test_the_proposals_worked_examples():
    usual = [(40, 40, 0.3, 52)] * 12
    # E=3, C=0 among twelve usual cells: possibly fewer (p_low about 0.1), never short on its own
    v = _family([(3, 0, 0.3, 52), *usual])
    assert v[0] in ("possibly_short", "unclear") and v[1:] == ["usual"] * 12
    assert _family([(3, 0, 0.3, 52), *usual])[0] != "short"
    # E=200, C=140 with alpha 0.2: about as expected, the swing of such a theme covers it
    assert _family([(200, 140, 0.2, 52), *usual])[0] == "usual"
    # E=8, C=0 with alpha 0.3: short when it survives Benjamini-Hochberg on its own
    assert _family([(8, 0, 0.3, 52)]) == ["short"]
    ev = scoring.cell_evidence(8, 0, 0.3, [2.0] * W, [2] * B)
    assert ev["p_low"] < 0.01 and ev["chance"] in (100, 200, 500) and ev["ratio_lo"] > 1
    # the same cell with too short a dispersion record, or too wide an interval, is unclear
    assert _family([(8, 0, 0.3, 7)]) == ["unclear"]
    assert _family([(8, 0, 2.0, 52)]) == ["unclear"]        # SE_g about 1.5: exp(1.645 SE) > 4
    # a plentiful theme 1.3 times short is rejected by BH but reads usual below the practical floor
    assert _family([(400, 300, 0.02, 52)]) == ["usual"]
    # the mirror image: twice the expected articles reads over
    assert _family([(40, 95, 0.05, 52)]) == ["over"]
