"""Small-sample statistics, pure Python (no numpy)."""

from __future__ import annotations

import math
import random
from collections import defaultdict
from statistics import NormalDist


def percentile(xs: list[float], q: float) -> float:
    """Linear-interpolated percentile, q in [0, 100]."""
    s = sorted(xs)
    if not s:
        raise ValueError("empty")
    k = (len(s) - 1) * q / 100
    lo, hi = math.floor(k), math.ceil(k)
    return s[lo] + (s[hi] - s[lo]) * (k - lo)


def _groups(clusters: list[str]) -> list[list[int]]:
    g: dict[str, list[int]] = defaultdict(list)
    for i, c in enumerate(clusters):
        g[c].append(i)
    return list(g.values())


def _boot(values: list[float], clusters: list[str], n_boot: int, seed: int) -> tuple[float, float, float]:
    """Mean of `values` and a 95% percentile CI from resampling whole clusters."""
    groups = _groups(clusters)
    rng = random.Random(seed)
    sums = [(sum(values[i] for i in g), len(g)) for g in groups]
    means = []
    for _ in range(n_boot):
        pick = [sums[rng.randrange(len(sums))] for _ in sums]
        tot = sum(s for s, _ in pick)
        cnt = sum(c for _, c in pick)
        means.append(tot / cnt)
    return sum(values) / len(values), percentile(means, 2.5), percentile(means, 97.5)


def accuracy_ci(correct: list[bool], clusters: list[str], n_boot: int = 2000, seed: int = 0):
    """(accuracy, lo, hi): 95% cluster bootstrap CI, clustered by template_id."""
    assert len(correct) == len(clusters) and correct
    return _boot([float(c) for c in correct], clusters, n_boot, seed)


def paired_bootstrap(a: list[bool], b: list[bool], clusters: list[str], n_boot: int = 2000, seed: int = 0):
    """(mean(a)-mean(b), lo, hi) on identical items, clustered by template_id."""
    assert len(a) == len(b) == len(clusters) and a
    return _boot([float(x) - float(y) for x, y in zip(a, b)], clusters, n_boot, seed)


def mcnemar(a: list[bool], b: list[bool]) -> dict:
    """Exact (binomial) McNemar test. n10 = a right & b wrong, n01 = a wrong & b right."""
    assert len(a) == len(b), "paired test needs the same items"
    n10 = sum(1 for x, y in zip(a, b) if x and not y)
    n01 = sum(1 for x, y in zip(a, b) if y and not x)
    n = n10 + n01
    if n == 0:
        return {"n10": 0, "n01": 0, "p": 1.0}
    k = min(n10, n01)
    tail = sum(math.comb(n, i) for i in range(k + 1)) / 2**n
    return {"n10": n10, "n01": n01, "p": min(1.0, 2 * tail)}


def power(n: int, p_base: float, alpha: float = 0.05, target: float = 0.8) -> float:
    """Minimum detectable difference between two independent accuracies, n items each, at 80% power
    (two-sided, normal approximation). Paired designs with positive correlation do better."""
    z = NormalDist().inv_cdf
    za, zb = z(1 - alpha / 2), z(target)
    d = (za + zb) * math.sqrt(2 * p_base * (1 - p_base) / n)
    for _ in range(50):  # refine with the variance under the alternative
        p2 = min(p_base + d, 1.0)
        pbar = (p_base + p2) / 2
        d = za * math.sqrt(2 * pbar * (1 - pbar) / n) + zb * math.sqrt(
            (p_base * (1 - p_base) + p2 * (1 - p2)) / n)
    return min(d, 1 - p_base)
