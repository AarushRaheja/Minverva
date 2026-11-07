"""Elo ratings of systems from paired per-item outcomes. Pure Python (no numpy).

Every item that two systems both answered is one match: the higher score wins (right beats wrong); both right or both wrong is a
draw (half a win each), or is dropped with ties=False. Ratings are the maximum-likelihood Bradley-Terry fit
(Hunter's MM iteration) on the Elo scale, so unlike sequential Elo updates they do not depend on match order:

    P(a beats b) = 1 / (1 + 10 ** ((R_b - R_a) / 400)),   mean rating = 1000.

`prior` virtual draws per pair keep an undefeated system finite. CIs resample whole clusters (template_id
for synthetic, contest_id for LCB), like stats.accuracy_ci.
"""

from __future__ import annotations

import math
import random
from collections import defaultdict
from itertools import combinations

from slm.bench.stats import percentile

BASE, SCALE = 1000.0, 400.0

Results = dict[str, dict[str, float]]  # system -> item -> score (correct as bool, or a rate); higher wins
Tally = dict[tuple[str, str], list[float]]  # (a, b) with a < b -> [score of a, matches]


def expected_score(r_a: float, r_b: float) -> float:
    """P(a beats b), draws counting half, under the Elo model."""
    return 1 / (1 + 10 ** ((r_b - r_a) / SCALE))


def _tallies(results: Results, clusters: dict[str, str] | None, ties: bool) -> dict[str, Tally]:
    """cluster -> pair tallies over the items both systems answered."""
    out: dict[str, Tally] = defaultdict(lambda: defaultdict(lambda: [0.0, 0]))
    for a, b in combinations(sorted(results), 2):
        for item in sorted(results[a].keys() & results[b].keys()):
            x, y = results[a][item], results[b][item]
            if x == y and not ties:
                continue
            t = out[item if clusters is None else clusters[item]][(a, b)]
            t[0] += 0.5 if x == y else float(x > y)
            t[1] += 1
    return out


def _fit(names: list[str], tally: Tally, prior: float, tol: float = 1e-10, max_iter: int = 10_000) -> dict[str, float]:
    wins = {n: 0.0 for n in names}
    games: dict[tuple[str, str], float] = defaultdict(float)
    for a, b in combinations(names, 2):
        wins[a] += prior / 2
        wins[b] += prior / 2
        games[(a, b)] += prior
    for (a, b), (s, n) in tally.items():
        wins[a] += s
        wins[b] += n - s
        games[(a, b)] += n
    nbr: dict[str, list[tuple[str, float]]] = defaultdict(list)
    for (a, b), g in games.items():
        if g:
            nbr[a].append((b, g))
            nbr[b].append((a, g))
    if any(nbr[n] and wins[n] <= 0 for n in names):
        raise ValueError("a system with no wins or draws has rating -inf; use prior > 0")
    p = {n: 1.0 for n in names}
    for _ in range(max_iter):
        new = {i: wins[i] / sum(g / (p[i] + p[j]) for j, g in nbr[i]) if nbr[i] else 1.0 for i in names}
        gm = math.exp(sum(math.log(v) for v in new.values()) / len(new))
        new = {i: v / gm for i, v in new.items()}
        done = max(abs(math.log(new[i] / p[i])) for i in names) < tol
        p = new
        if done:
            break
    return {n: BASE + SCALE * math.log10(p[n]) for n in names}


def _merge(tallies: list[Tally]) -> Tally:
    out: Tally = defaultdict(lambda: [0.0, 0])
    for t in tallies:
        for k, (s, n) in t.items():
            out[k][0] += s
            out[k][1] += n
    return out


def elo(results: Results, clusters: dict[str, str] | None = None, *, ties: bool = True,
        prior: float = 1.0) -> dict[str, float]:
    """system -> rating (mean 1000). Items only one system answered are ignored."""
    return _fit(sorted(results), _merge(list(_tallies(results, clusters, ties).values())), prior)


def elo_ci(results: Results, clusters: dict[str, str] | None = None, *, ties: bool = True, prior: float = 1.0,
           n_boot: int = 500, seed: int = 0) -> dict[str, tuple[float, float, float]]:
    """system -> (rating, lo, hi): 95% CI from resampling whole clusters (each item its own if None)."""
    names = sorted(results)
    by_cluster = list(_tallies(results, clusters, ties).values())
    point = _fit(names, _merge(by_cluster), prior)
    if not by_cluster:
        return {n: (r, r, r) for n, r in point.items()}
    rng = random.Random(seed)
    boots: dict[str, list[float]] = {n: [] for n in names}
    for _ in range(n_boot):
        r = _fit(names, _merge([by_cluster[rng.randrange(len(by_cluster))] for _ in by_cluster]), prior)
        for n in names:
            boots[n].append(r[n])
    return {n: (point[n], percentile(boots[n], 2.5), percentile(boots[n], 97.5)) for n in names}


def head_to_head(results: Results, a: str, b: str, clusters: dict[str, str] | None = None, *, prior: float = 1.0,
                 n_boot: int = 2000, seed: int = 0) -> dict:
    """a vs b alone, over the items both answered: win/draw/loss for a, and a's rating minus b's with a 95%
    CI from resampling clusters. `prior` shrinks the gap, so a clean sweep over few items stays modest."""
    shared = sorted(results[a].keys() & results[b].keys())
    wins = sum(results[a][i] > results[b][i] for i in shared)
    losses = sum(results[a][i] < results[b][i] for i in shared)
    names = sorted((a, b))
    gap = lambda t: (lambda r: r[a] - r[b])(_fit(names, t, prior))  # noqa: E731
    by_cluster = list(_tallies({a: results[a], b: results[b]}, clusters, True).values())
    diff = gap(_merge(by_cluster))
    lo, hi = diff, diff
    if by_cluster:
        rng = random.Random(seed)
        boots = [gap(_merge([by_cluster[rng.randrange(len(by_cluster))] for _ in by_cluster])) for _ in range(n_boot)]
        lo, hi = percentile(boots, 2.5), percentile(boots, 97.5)
    return {"a": a, "b": b, "wins": wins, "draws": len(shared) - wins - losses, "losses": losses, "n": len(shared),
            "n_clusters": len(by_cluster), "diff": diff, "lo": lo, "hi": hi}


def from_per_item(per_item: dict[tuple, list]) -> tuple[Results, dict[str, str]]:
    """score_runs() per-item output -> (results, clusters by template_id). A system is
    '<topology>-A<atomicity>' ('<topology>' if no atomicity), prefixed by run_id when that collides."""
    label = lambda topo, at: str(topo) if at is None else f"{topo}-A{at}"  # noqa: E731
    counts = defaultdict(int)
    for _, topo, at in per_item:
        counts[label(topo, at)] += 1
    results: Results = {}
    clusters: dict[str, str] = {}
    for (run_id, topo, at), rs in per_item.items():
        name = label(topo, at) if counts[label(topo, at)] == 1 else f"{run_id}/{label(topo, at)}"
        results[name] = {r.problem_id: r.correct for r in rs}
        for r in rs:
            clusters[r.problem_id] = r.template_id or r.problem_id
    return results, clusters


def to_markdown(cis: dict[str, tuple[float, float, float]], results: Results) -> str:
    rows = ["| rank | system | Elo | 95% CI | accuracy (%) | n |", "|---|---|---|---|---|---|"]
    for i, (name, (r, lo, hi)) in enumerate(sorted(cis.items(), key=lambda kv: -kv[1][0]), 1):
        res = results[name]
        acc = 100 * sum(res.values()) / len(res) if res else float("nan")
        rows.append(f"| {i} | {name} | {r:.0f} | {lo:.0f}-{hi:.0f} | {acc:.1f} | {len(res)} |")
    return "\n".join(rows)
