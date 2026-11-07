"""Paired statistics for task-level results. Pure Python. Repeated attempts of one task are never independent samples."""

from __future__ import annotations

import math
import random
from statistics import NormalDist


def mcnemar(a: list[bool], b: list[bool]) -> dict:
    """Exact two-sided test on one result per paired task. Only the tasks where the two agents disagree count."""
    if len(a) != len(b):
        raise ValueError("a paired test needs the same tasks")
    a_only = sum(x and not y for x, y in zip(a, b))
    b_only = sum(y and not x for x, y in zip(a, b))
    n = a_only + b_only
    p = 1.0 if n == 0 else min(1.0, 2 * sum(math.comb(n, i) for i in range(min(a_only, b_only) + 1)) / 2**n)
    return {"a_only": a_only, "b_only": b_only, "both": sum(x and y for x, y in zip(a, b)),
            "neither": sum(not x and not y for x, y in zip(a, b)), "p": p}


def min_discordant_for_significance(alpha: float = 0.05) -> int:
    """Fewest disagreements, all one way, that can reach significance. Below this no result can, whatever happens."""
    n = 1
    while 2 / 2**n > alpha:
        n += 1
    return n


def percentile(xs: list[float], q: float) -> float:
    s = sorted(xs)
    if not s:
        raise ValueError("empty")
    k = (len(s) - 1) * q / 100
    lo, hi = math.floor(k), math.ceil(k)
    return s[lo] + (s[hi] - s[lo]) * (k - lo)


def clustered_bootstrap(rows: list[tuple[str, str, float]], stat, n_boot: int = 10000, seed: int = 0) -> tuple[float, float, float]:
    """rows: (cluster, item, value). Resample clusters, then items inside each, keeping all of an item's repeats together.
    stat takes a list of rows and returns a number, or None if the sample can't produce one."""
    clusters: dict[str, dict[str, list]] = {}
    for r in rows:
        clusters.setdefault(r[0], {}).setdefault(r[1], []).append(r)
    names = sorted(clusters)
    rng = random.Random(seed)
    out = []
    for _ in range(n_boot):
        sample = []
        for c in (names[rng.randrange(len(names))] for _ in names):
            items = list(clusters[c].values())
            for _ in items:
                sample.extend(items[rng.randrange(len(items))])
        v = stat(sample)
        if v is not None:
            out.append(v)
    point = stat(rows)
    if not out or point is None:
        return (point if point is not None else float("nan"), float("nan"), float("nan"))
    return point, percentile(out, 2.5), percentile(out, 97.5)


def paired_difference_ci(a: dict[str, list[float]], b: dict[str, list[float]], groups: dict[str, str],
                         n_boot: int = 10000, seed: int = 0) -> dict:
    """Mean of a minus b, per task, on the tasks both attempted; averages repeats within a task first."""
    shared = sorted(set(a) & set(b))
    if not shared:
        return {"n": 0, "diff": None, "lo": None, "hi": None}
    d = [(groups.get(t, t), t, sum(a[t]) / len(a[t]) - sum(b[t]) / len(b[t])) for t in shared]
    point, lo, hi = clustered_bootstrap(d, lambda rows: sum(r[2] for r in rows) / len(rows), n_boot, seed)
    return {"n": len(shared), "clusters": len({x[0] for x in d}), "diff": point, "lo": lo, "hi": hi}


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """A CI for a proportion that stays sensible at 0 of n, where a bootstrap would collapse to zero width."""
    if n == 0:
        return (float("nan"), float("nan"))
    p = k / n
    d = 1 + z**2 / n
    mid = (p + z**2 / (2 * n)) / d
    half = z * math.sqrt(p * (1 - p) / n + z**2 / (4 * n**2)) / d
    return max(0.0, mid - half), min(1.0, mid + half)


def pass_at_k(by_task: dict[str, list[bool]], k: int) -> float | None:
    """Tasks solved at least once in the first k independent attempts. Tasks with fewer attempts don't count."""
    eligible = [v[:k] for v in by_task.values() if len(v) >= k]
    return sum(any(v) for v in eligible) / len(eligible) if eligible else None


def success_all(by_task: dict[str, list[bool]], k: int = 3) -> float | None:
    eligible = [v[:k] for v in by_task.values() if len(v) >= k]
    return sum(all(v) for v in eligible) / len(eligible) if eligible else None


def cost_per_resolved(costs: list[float | None], resolved: list[bool]) -> float | None:
    """All spending, failed attempts included, per task solved. None if a cost is unknown or nothing was solved."""
    if any(c is None for c in costs) or not any(resolved):
        return None
    return sum(costs) / sum(resolved)


def interaction(p11: float, p10: float, p01: float, p00: float) -> float:
    return p11 - p10 - p01 + p00


def pareto_frontier(points: list[dict], x: str = "cost", y: str = "resolve") -> list[str]:
    """Names no other point beats: at least as cheap and as good, and strictly better on one. Unknown cost is left out."""
    known = [p for p in points if p.get(x) is not None and p.get(y) is not None]
    return [p["name"] for p in known
            if not any(o[x] <= p[x] and o[y] >= p[y] and (o[x] < p[x] or o[y] > p[y]) for o in known)]


def paired_tasks_needed(disagreement: float, diff: float, alpha: float = 0.05, power: float = 0.8) -> int | None:
    """Tasks for a paired test to detect `diff`, given the pilot's rate of disagreement (normal approximation)."""
    if disagreement <= 0 or abs(diff) > disagreement or diff == 0:
        return None
    z = NormalDist().inv_cdf
    za, zb = z(1 - alpha / 2), z(power)
    return math.ceil((za * math.sqrt(disagreement) + zb * math.sqrt(disagreement - diff**2)) ** 2 / diff**2)


def holm(pvalues: dict[str, float], alpha: float = 0.05) -> dict[str, bool]:
    ordered = sorted(pvalues.items(), key=lambda kv: kv[1])
    out, ok = {}, True
    for i, (name, p) in enumerate(ordered):
        ok = ok and p <= alpha / (len(ordered) - i)
        out[name] = ok
    return out


def robustness_delta(perturbed: list[bool], control: list[bool]) -> float | None:
    if not perturbed or not control:
        return None
    return sum(perturbed) / len(perturbed) - sum(control) / len(control)
