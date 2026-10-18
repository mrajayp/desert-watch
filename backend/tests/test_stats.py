"""The pure-Python statistics behind the verdict against scipy, which is imported here only: the web
process and the scheduler never load it (tests/test_ml.py guards that)."""
import math

import pytest

from app import stats

A_B = (0.5, 1.0, 2.5, 7.0, 30.0, 120.0, 500.0, 2000.0)
X = (0.0, 1e-4, 0.01, 0.1, 0.3, 0.5, 0.7, 0.9, 0.99, 0.9999, 1.0)


def test_incomplete_beta_matches_scipy_across_the_grid():
    from scipy.special import betainc
    for a in A_B:
        for b in A_B:
            for x in X:
                assert stats.betainc(a, b, x) == pytest.approx(float(betainc(a, b, x)), rel=1e-9, abs=1e-13), (a, b, x)


def test_negative_binomial_cdf_and_sf_match_scipy():
    from scipy.stats import nbinom
    for r in (0.7, 3.0, 19.0, 150.0, 2000.0):
        for p in (0.1, 0.45, 0.9):
            for k in (0, 1, 5, 40, 300, 2500):
                assert stats.nb_cdf(k, r, p) == pytest.approx(float(nbinom.cdf(k, r, p)), rel=1e-9, abs=1e-13), (r, p, k)
                assert stats.nb_sf(k, r, p) == pytest.approx(float(nbinom.sf(k - 1, r, p)), rel=1e-9, abs=1e-13), (r, p, k)
    assert stats.nb_cdf(-1, 3.0, 0.5) == 0.0 and stats.nb_sf(0, 3.0, 0.5) == 1.0


def test_poisson_cdf_and_sf_match_scipy():
    from scipy.stats import poisson
    for lam in (0.5, 3.0, 20.0, 150.0, 1200.0):
        for k in (0, 1, 2, 5, 18, 25, 40, 140, 160, 300, 1100, 1300):
            assert stats.poisson_cdf(k, lam) == pytest.approx(float(poisson.cdf(k, lam)), rel=1e-9, abs=1e-13), (lam, k)
            assert stats.poisson_sf(k, lam) == pytest.approx(float(poisson.sf(k - 1, lam)), rel=1e-9, abs=1e-13), (lam, k)
    assert stats.poisson_cdf(-1, 3.0) == 0.0 and stats.poisson_sf(0, 3.0) == 1.0
    assert stats.poisson_cdf(4, 0.0) == 1.0 and stats.poisson_sf(1, 0.0) == 0.0


def test_nb_tail_has_the_right_moments_and_matches_scipy():
    from scipy.stats import nbinom, poisson
    for E, V, C in ((3.0, 4.98, 0), (8.0, 17.1, 0), (200.0, 2933.0, 140), (31.0, 90.0, 12), (50.0, 400.0, 95),
                    (20.0, 20.0, 15), (20.0, 20.019, 25)):
        rp = stats.nb_params(E, V)
        p_low, p_high = stats.nb_tail(E, V, C)
        if rp is None:   # at the Poisson floor
            assert V <= 1.001 * E
            assert p_low == pytest.approx(float(poisson.cdf(C, E)), rel=1e-9)
            assert p_high == pytest.approx(float(poisson.sf(C - 1, E)), rel=1e-9)
            continue
        r, p = rp
        assert nbinom.mean(r, p) == pytest.approx(E) and nbinom.var(r, p) == pytest.approx(V)
        assert p_low == pytest.approx(float(nbinom.cdf(C, r, p)), rel=1e-9)
        assert p_high == pytest.approx(float(nbinom.sf(C - 1, r, p)), rel=1e-9)
    # the proposal's worked examples: E=3, C=0 is about 1 in 10; E=8, C=0 is well under 1 in 100
    assert 0.09 < stats.nb_tail(3.0, 4.98, 0)[0] < 0.105
    assert stats.nb_tail(8.0, 17.1, 0)[0] < 0.006
    assert stats.nb_tail(0.0, 0.0, 0) == (1.0, 1.0) and stats.nb_tail(0.0, 0.0, 2) == (1.0, 0.0)


def test_interval_is_symmetric_on_the_log_scale():
    lo, hi = stats.interval(math.log(2.0), 0.3)
    assert lo == pytest.approx(2.0 * math.exp(-1.645 * 0.3)) and hi == pytest.approx(2.0 * math.exp(1.645 * 0.3))
    assert math.sqrt(lo * hi) == pytest.approx(2.0)


def test_benjamini_hochberg_on_known_cases_and_against_scipy():
    from scipy.stats import false_discovery_control
    # ranks: 0.01 <= 0.02, 0.03 <= 0.04, 0.04 <= 0.06, 0.2 > 0.08: the first three are rejected
    assert stats.benjamini_hochberg([0.01, 0.04, 0.03, 0.2, 0.5], 0.1) == [True, True, True, False, False]
    # a p-value past its own line is still rejected when a larger one makes the cut (step-up)
    assert stats.benjamini_hochberg([0.021, 0.02], 0.1) == [True, True]
    assert stats.benjamini_hochberg([0.099], 0.1) == [True]                 # alone: a single test at q
    assert stats.benjamini_hochberg([0.099, 0.5], 0.1) == [False, False]     # 0.099 > 0.05
    assert stats.benjamini_hochberg([0.05] * 10, 0.1) == [True] * 10
    assert stats.benjamini_hochberg([], 0.1) == []
    import random
    rng = random.Random(7)
    for _ in range(200):
        m = rng.randint(1, 30)
        ps = [rng.random() ** rng.choice((1, 3, 8)) for _ in range(m)]
        adjusted = false_discovery_control(ps, method="bh")
        assert stats.benjamini_hochberg(ps, 0.1) == [bool(a <= 0.1) for a in adjusted], ps


def test_one_in_rounds_to_the_named_steps():
    assert stats.one_in(0.3) is None and stats.one_in(0.21) is None and stats.one_in(None) is None
    assert stats.one_in(0.2) == 10 and stats.one_in(0.1) == 10
    assert stats.one_in(0.07) == 20 and stats.one_in(0.05) == 20
    assert stats.one_in(0.02) == 50 and stats.one_in(0.0101) == 100
    assert stats.one_in(0.004) == 200 and stats.one_in(0.003) == 500
    assert stats.one_in(1e-9) == 1000 and stats.one_in(0.0) == 1000
