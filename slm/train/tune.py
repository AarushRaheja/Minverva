"""HP1 from EXPERIMENTS.md: tune the specialist LoRA recipe, one factor at a time around the default.

    python -m slm.train tune --dry-run                  # list the trials, needs no GPU
    python -m slm.train tune --role database --root out # train and score, resumable
    python -m slm.train tune-report --root out

Every trial for a domain is scored on the same `dev` rows (`load_rows` never sees `test`), so trials compare
row by row. A trial replaces the default only if its paired 95% CI against the default is entirely above zero,
the rule in EXPERIMENTS.md. With no clear winner the default stays. This module needs no torch, only train_role does.
"""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass, replace
from pathlib import Path

from slm import contracts as C
from slm.bench.stats import _boot
from slm.train.backprop import Recipe, load_rows, total_steps

SEARCH: dict[str, tuple] = {"r": (8, 32), "lr": (1e-4, 5e-4), "epochs": (1, 3), "target": ("attn",)}
DEFAULT = "default"


@dataclass(frozen=True)
class Trial:
    id: str
    recipe: Recipe


def trials(base: Recipe | None = None) -> list[Trial]:
    """The default recipe, then each other value of each factor with the rest held at the default."""
    base = base or Recipe()
    out = [Trial(DEFAULT, base)]
    for factor, values in SEARCH.items():
        for v in values:
            changes = {factor: v, **({"alpha": 2 * v} if factor == "r" else {})}  # alpha stays 2r
            out.append(Trial(f"{factor}={v}", replace(base, **changes)))
    return out


def _load(path: Path) -> list[dict]:
    return [json.loads(x) for x in path.read_text().splitlines() if x.strip()] if path.exists() else []


def plan_lines(roles: list[str], root: str | Path, base: Recipe | None = None) -> list[str]:
    """One line per trial with its optimizer steps, for sizing a run before spending GPU time."""
    lines, grand = [], 0
    for role in roles:
        train, ev = load_rows(root, role)
        n = min(len(train), base.max_train) if base and base.max_train else len(train)
        for t in trials(base):
            steps = total_steps(n, t.recipe.batch, t.recipe.epochs)
            grand += steps
            lines.append(f"{role:9} {t.id:10} train={n} eval={len(ev)} steps={steps}")
    lines.append(f"{len(lines)} trials, {grand} optimizer steps")
    return lines


def run_tuning(roles: list[str], root: str | Path, run: str = "hp1", *, base: Recipe | None = None, train_fn=None,
               device: str | None = None, model: str | None = None, log=print) -> Path:
    """Run every trial not yet recorded. A trial that crashes records nothing, so a later run retries it.
    Adapters are deleted after scoring to save disk on free GPUs: retrain the winner with `backprop`."""
    if train_fn is None:
        from slm.train.backprop import train_role as train_fn
    out = Path(root) / "tune" / run
    out.mkdir(parents=True, exist_ok=True)
    results = out / "results.jsonl"
    done = {(r["role"], r["trial"]) for r in _load(results)}
    for role in roles:
        for t in trials(base):
            if (role, t.id) in done:
                continue
            trial_dir = out / "adapters" / role / t.id.replace("=", "-")
            log(f"[tune] {role} {t.id}")
            try:
                rec = train_fn(role, root, t.recipe, device=device, base=model, out_root=trial_dir)
            except Exception as e:  # noqa: BLE001 - one bad trial (often out of memory) must not stop the sweep
                log(f"[tune] {role} {t.id} failed, nothing recorded: {type(e).__name__}: {str(e)[:200]}")
                continue
            finally:
                shutil.rmtree(trial_dir, ignore_errors=True)
            row = {"role": role, "trial": t.id, "gate": rec.get("gate_task_ok"), "flags": rec.get("gate_flags", []),
                   "clusters": rec.get("gate_clusters", []), "train_seconds": rec.get("train_seconds"),
                   "final_loss": rec.get("final_loss"), "n_train": rec.get("n_train"), "steps": rec.get("steps")}
            with results.open("a") as f:
                f.write(json.dumps(row) + "\n")
    return results


def verdict(default: dict | None, row: dict) -> tuple[float, float, float] | None:
    """(gate delta vs the default, lo, hi), or None if the two weren't scored on the same rows."""
    if default is None or not row["flags"] or row.get("clusters") != default.get("clusters"):
        return None
    if len(row["flags"]) != len(default["flags"]):
        return None
    deltas = [float(a) - float(b) for a, b in zip(row["flags"], default["flags"])]
    return _boot(deltas, row["clusters"], 2000, 0)


def choose(rows: list[dict]) -> dict[str, str]:
    """role -> winning trial: the largest gain whose whole CI is above zero, else the default."""
    best: dict[str, str] = {}
    for role in sorted({r["role"] for r in rows}):
        mine = [r for r in rows if r["role"] == role]
        default = next((r for r in mine if r["trial"] == DEFAULT), None)
        scored = [(verdict(default, r), r["trial"]) for r in mine if r["trial"] != DEFAULT]
        wins = [(v[0], trial) for v, trial in scored if v and v[1] > 0]
        best[role] = max(wins, key=lambda x: x[0])[1] if wins else DEFAULT
    return best


def report(rows: list[dict]) -> str:
    lines = []
    picks = choose(rows)
    for role in sorted(picks):
        mine = [r for r in rows if r["role"] == role]
        default = next((r for r in mine if r["trial"] == DEFAULT), None)
        lines += [f"## {role}: use `{picks[role]}`", "",
                  "| trial | gate (dev) | gain vs default (95% CI) | final loss | train s |", "|---|---|---|---|---|"]
        for r in sorted(mine, key=lambda r: (r["trial"] != DEFAULT, -(r["gate"] or 0))):
            v = verdict(default, r) if r is not default else None
            gain = "—" if v is None else f"{v[0]:+.3f} ({v[1]:+.3f} to {v[2]:+.3f})"
            gate = "—" if r["gate"] is None else f"{r['gate']:.3f}"
            lines.append(f"| {r['trial']} | {gate} | {gain} | {r['final_loss']:.4f} | {r['train_seconds']:.0f} |")
        if default is None:
            lines.append("\nThe default recipe has no result yet, so nothing can be compared.")
        elif len(mine) > 1 and all(r["gate"] == 1.0 for r in mine):
            lines.append("\nEvery trial scored 1.0, so the gate can't separate them on this data.")
        lines.append("")
    missing = [d for d in C.DOMAINS if d not in picks]
    if missing:
        lines.append(f"Not tuned yet: {', '.join(missing)}")
    return "\n".join(lines)
