"""Pure-Python statistics behind the calibrated verdict. Nothing here imports numpy or scipy: the web
process and the scheduler never load them (scipy is pinned for the theme model and serves only as the
oracle in tests/test_stats.py).

  betainc(a, b, x)            regularised incomplete beta I_x(a, b): math.lgamma + Lentz's continued fraction
  poisson_cdf(k, lam)         P(X <= k)   poisson_sf(k, lam)   P(X >= k)
  nb_cdf(k, r, p)             P(X <= k) for X ~ NegBin(size r, success p) = I_p(r, k + 1)
  nb_sf(k, r, p)              P(X >= k) = I_{1-p}(k, r)
  nb_tail(E, V, C)            (p_low, p_high) for a count with mean E and variance V: Poisson when
                              V <= 1.001 E, else negative binomial with r = E^2 / (V - E), p = r / (r + E)
  interval(g, se, z)          (exp(g - z se), exp(g + z se))
  benjamini_hochberg(ps, q)   which p-values are rejected at false-discovery rate q
  one_in(p)                   "1 in N" with N in ONE_IN_STEPS, nearest on a log scale; None when p > 0.2
"""
import math

_TINY = 1e-300
_EPS = 1e-15
_MAX_ITER = 5000
ONE_IN_STEPS = (10, 20, 50, 100, 200, 500, 1000)
ONE_IN_MAX_P = 0.2   # above this the chance is not quoted: it could easily be chance


def _betacf(a: float, b: float, x: float) -> float:
    """The continued fraction for the incomplete beta, evaluated by the modified Lentz method
    (Numerical Recipes 6.4). Converges in about sqrt(max(a, b)) steps when x < (a + 1) / (a + b + 2)."""
    qab, qap, qam = a + b, a + 1.0, a - 1.0
    c = 1.0
    d = 1.0 - qab * x / qap
    if abs(d) < _TINY:
        d = _TINY
    d = 1.0 / d
    h = d
    for m in range(1, _MAX_ITER + 1):
        m2 = 2 * m
        aa = m * (b - m) * x / ((qam + m2) * (a + m2))
        d = 1.0 + aa * d
        if abs(d) < _TINY:
            d = _TINY
        c = 1.0 + aa / c
        if abs(c) < _TINY:
            c = _TINY
        d = 1.0 / d
        h *= d * c
        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        d = 1.0 + aa * d
        if abs(d) < _TINY:
            d = _TINY
        c = 1.0 + aa / c
        if abs(c) < _TINY:
            c = _TINY
        d = 1.0 / d
        de = d * c
        h *= de
        if abs(de - 1.0) < _EPS:
            break
    return h


def betainc(a: float, b: float, x: float) -> float:
    """Regularised incomplete beta I_x(a, b) for a, b > 0 and 0 <= x <= 1."""
    if a <= 0 or b <= 0:
        raise ValueError("betainc needs a, b > 0")
    if x <= 0:
        return 0.0
    if x >= 1:
        return 1.0
    front = math.exp(math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b) + a * math.log(x) + b * math.log1p(-x))
    if x < (a + 1.0) / (a + b + 2.0):
        return min(1.0, front * _betacf(a, b, x) / a)
    return max(0.0, 1.0 - front * _betacf(b, a, 1.0 - x) / b)


def _poisson_term(i: int, lam: float) -> float:
    return math.exp(i * math.log(lam) - lam - math.lgamma(i + 1))


def poisson_cdf(k: float, lam: float) -> float:
    """P(X <= k) for X ~ Poisson(lam): the terms summed in log space."""
    k = math.floor(k)
    if k < 0:
        return 0.0
    if lam <= 0:
        return 1.0
    return min(1.0, sum(_poisson_term(i, lam) for i in range(k + 1)))


def poisson_sf(k: float, lam: float) -> float:
    """P(X >= k) for X ~ Poisson(lam). The upper tail is summed directly when it is the smaller side,
    so a tiny probability keeps its digits."""
    k = math.ceil(k)
    if k <= 0:
        return 1.0
    if lam <= 0:
        return 0.0
    if k <= lam:
        return max(0.0, 1.0 - poisson_cdf(k - 1, lam))
    total, i = 0.0, k
    while True:   # terms fall geometrically once i > lam
        t = _poisson_term(i, lam)
        total += t
        i += 1
        if t <= total * 1e-17 or i > k + _MAX_ITER:
            return min(1.0, total)


def nb_cdf(k: float, r: float, p: float) -> float:
    """P(X <= k), X ~ NegBin(r, p): failures before the r-th success, mean r(1-p)/p."""
    k = math.floor(k)
    if k < 0:
        return 0.0
    return betainc(r, k + 1.0, p)


def nb_sf(k: float, r: float, p: float) -> float:
    """P(X >= k) = 1 - I_p(r, k) = I_{1-p}(k, r), computed on its own side for accuracy."""
    k = math.ceil(k)
    if k <= 0:
        return 1.0
    return betainc(float(k), r, 1.0 - p)


def nb_params(E: float, V: float) -> tuple[float, float] | None:
    """(r, p) of the negative binomial with mean E and variance V, or None when V <= 1.001 E (Poisson)."""
    if V <= 1.001 * E:
        return None
    r = E * E / (V - E)
    return r, r / (r + E)


def nb_tail(E: float, V: float, C: float) -> tuple[float, float]:
    """(p_low, p_high) = (P(X <= C), P(X >= C)) for a count C against a mean E with variance V
    if nothing had changed. Poisson when the variance is at the Poisson floor, else negative binomial."""
    if E <= 0:
        return (1.0, 1.0) if C <= 0 else (1.0, 0.0)
    rp = nb_params(E, V)
    if rp is None:
        return poisson_cdf(C, E), poisson_sf(C, E)
    r, p = rp
    return nb_cdf(C, r, p), nb_sf(C, r, p)


def interval(g: float, se: float, z: float = 1.645) -> tuple[float, float]:
    """(lo, hi) on exp(g): a 90% interval at the default z."""
    return math.exp(g - z * se), math.exp(g + z * se)


def benjamini_hochberg(ps: list[float], q: float) -> list[bool]:
    """Which of `ps` are rejected at false-discovery rate q: with the p-values in order, the largest k
    with p_(k) <= q k / m, and everything up to it."""
    m = len(ps)
    if m == 0:
        return []
    order = sorted(range(m), key=lambda i: ps[i])
    k = 0
    for rank, i in enumerate(order, 1):
        if ps[i] <= q * rank / m:
            k = rank
    out = [False] * m
    for i in order[:k]:
        out[i] = True
    return out


def one_in(p: float | None) -> int | None:
    """The chance as "1 in N", N the nearest of ONE_IN_STEPS on a log scale (the last step is a ceiling:
    1000 reads "about once in 1000"). None when p > ONE_IN_MAX_P: it could easily be chance."""
    if p is None or p > ONE_IN_MAX_P:
        return None
    if p <= 0:
        return ONE_IN_STEPS[-1]
    target = math.log(1.0 / p)
    return min(ONE_IN_STEPS, key=lambda n: abs(math.log(n) - target))
