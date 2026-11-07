"""Properties of slm.bench.stats against independent references and simulation. Offline, pure Python."""

import math
import random
import statistics

import pytest

from slm.bench import stats


@pytest.mark.parametrize("seed", range(5))
def test_percentile_matches_statistics_inclusive(seed):
    rng = random.Random(seed)
    xs = [rng.uniform(-50, 50) for _ in range(rng.randint(2, 40))]
    qs = statistics.quantiles(xs, n=100, method="inclusive")  # q = 1..99
    for q in range(1, 100):
        assert stats.percentile(xs, q) == pytest.approx(qs[q - 1])
    assert stats.percentile(xs, 0) == min(xs) and stats.percentile(xs, 100) == max(xs)
    assert stats.percentile(xs, 50) == pytest.approx(statistics.median(xs))


def test_percentile_order_invariant_and_empty():
    xs = [3.0, 1.0, 2.0, 10.0]
    assert stats.percentile(xs, 95) == stats.percentile(sorted(xs), 95)
    assert xs == [3.0, 1.0, 2.0, 10.0]  # input not mutated
    with pytest.raises(ValueError):
        stats.percentile([], 50)


def _mcnemar_ref(n10, n01):
    """Two-sided exact binomial test, summing every outcome at most as likely as the observed one."""
    n = n10 + n01
    if n == 0:
        return 1.0
    pmf = [math.comb(n, i) / 2**n for i in range(n + 1)]
    return min(1.0, sum(p for p in pmf if p <= pmf[n10] * (1 + 1e-12)))


@pytest.mark.parametrize("seed", range(20))
def test_mcnemar_matches_exact_binomial_and_is_symmetric(seed):
    rng = random.Random(seed)
    n = rng.randint(1, 60)
    a = [rng.random() < 0.6 for _ in range(n)]
    b = [rng.random() < 0.5 for _ in range(n)]
    r = stats.mcnemar(a, b)
    assert r["p"] == pytest.approx(_mcnemar_ref(r["n10"], r["n01"]))
    assert 0 <= r["p"] <= 1
    s = stats.mcnemar(b, a)
    assert (s["n10"], s["n01"]) == (r["n01"], r["n10"]) and s["p"] == r["p"]
    # concordant pairs carry no information
    both = [True] * 7 + [False] * 4
    assert stats.mcnemar(a + both, b + both) == r


def test_mcnemar_rejects_unpaired_inputs():
    with pytest.raises(AssertionError):
        stats.mcnemar([True, False, True], [True, False])


def test_mcnemar_type_one_error_is_controlled():
    # exact test under H0 (b is a with symmetric flips): rejection rate must not exceed alpha
    rng = random.Random(3)
    rejects, reps = 0, 400
    for _ in range(reps):
        a = [rng.random() < 0.7 for _ in range(80)]
        b = [x if rng.random() < 0.8 else rng.random() < 0.7 for x in a]
        rejects += stats.mcnemar(a, b)["p"] < 0.05
    assert rejects / reps <= 0.07


def test_bootstrap_is_seeded_bounded_and_contains_the_mean():
    rng = random.Random(0)
    ok = [rng.random() < 0.6 for _ in range(150)]
    cl = [f"t{i % 12}" for i in range(150)]
    r1 = stats.accuracy_ci(ok, cl, n_boot=300, seed=4)
    assert r1 == stats.accuracy_ci(ok, cl, n_boot=300, seed=4)
    assert r1 != stats.accuracy_ci(ok, cl, n_boot=300, seed=5)
    acc, lo, hi = r1
    assert acc == sum(ok) / len(ok) and 0 <= lo <= acc <= hi <= 1
    # a single cluster cannot be resampled into anything else
    assert stats.accuracy_ci(ok, ["one"] * 150, n_boot=50)[1:] == (acc, acc)


def test_bootstrap_ci_shrinks_with_n():
    width = []
    for n in (50, 200, 800):
        rng = random.Random(n)
        ok = [rng.random() < 0.7 for _ in range(n)]
        _, lo, hi = stats.accuracy_ci(ok, [str(i) for i in range(n)], n_boot=400, seed=0)
        width.append(hi - lo)
    assert width[0] > width[1] > width[2]
    assert width[0] / width[2] == pytest.approx(4, rel=0.35)  # ~ 1/sqrt(n)


def test_bootstrap_ci_coverage_by_simulation():
    # nominal 95%: the true accuracy should fall inside the interval in roughly 95% of repetitions
    rng, p, hits, reps = random.Random(11), 0.7, 0, 120
    for r in range(reps):
        ok = [rng.random() < p for _ in range(120)]
        _, lo, hi = stats.accuracy_ci(ok, [str(i) for i in range(120)], n_boot=300, seed=r)
        hits += lo <= p <= hi
    assert 0.88 <= hits / reps <= 0.995


def test_paired_bootstrap_antisymmetric_and_matches_difference():
    rng = random.Random(2)
    a = [rng.random() < 0.75 for _ in range(120)]
    b = [rng.random() < 0.55 for _ in range(120)]
    cl = [str(i % 15) for i in range(120)]
    d, lo, hi = stats.paired_bootstrap(a, b, cl, n_boot=400, seed=1)
    d2, lo2, hi2 = stats.paired_bootstrap(b, a, cl, n_boot=400, seed=1)
    assert d == pytest.approx(sum(a) / 120 - sum(b) / 120)
    assert (d2, lo2, hi2) == pytest.approx((-d, -hi, -lo))
    with pytest.raises(AssertionError):
        stats.paired_bootstrap(a, b[:-1], cl)


def test_paired_bootstrap_beats_unpaired_on_correlated_systems():
    # two systems that agree on most items: the paired CI on the difference is much tighter
    rng = random.Random(9)
    a = [rng.random() < 0.7 for _ in range(300)]
    b = [x if rng.random() < 0.9 else not x for x in a]
    cl = [str(i) for i in range(300)]
    _, lo, hi = stats.paired_bootstrap(a, b, cl, n_boot=400, seed=0)
    _, alo, ahi = stats.accuracy_ci(a, cl, n_boot=400, seed=0)
    _, blo, bhi = stats.accuracy_ci(b, cl, n_boot=400, seed=0)
    unpaired = math.hypot((ahi - alo) / 2, (bhi - blo) / 2) * 2
    assert hi - lo < 0.75 * unpaired


def test_power_monotone_and_matches_simulation():
    assert stats.power(500, 0.5) > stats.power(1000, 0.5) > stats.power(2000, 0.5)
    assert stats.power(1000, 0.5, alpha=0.01) > stats.power(1000, 0.5)
    assert stats.power(1000, 0.5, target=0.9) > stats.power(1000, 0.5)
    # at the reported MDE, a two-proportion z-test should reject about 80% of the time
    n, p0 = 400, 0.6
    d = stats.power(n, p0)
    rng, rejects, reps = random.Random(1), 0, 600
    z = statistics.NormalDist().inv_cdf(0.975)
    for _ in range(reps):
        x = sum(rng.random() < p0 for _ in range(n)) / n
        y = sum(rng.random() < p0 + d for _ in range(n)) / n
        pbar = (x + y) / 2
        se = math.sqrt(2 * pbar * (1 - pbar) / n)
        rejects += abs(y - x) / se > z
    assert 0.72 <= rejects / reps <= 0.88
