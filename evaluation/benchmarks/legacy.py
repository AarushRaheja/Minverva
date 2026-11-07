"""Bring the saved runs in out/arch into the same record format, without running any model. The manifest fields those
runs never recorded stay null and the provenance says imported, so they can't pass for fully reproducible trials."""

from __future__ import annotations

import json
from pathlib import Path

from evaluation.benchmarks.project_build import project_tasks
from evaluation.evaluators.correctness import report_to_grade
from evaluation.evaluators.failures import classify
from evaluation.runner.orchestrator import RESULTS, SCHEMA, trial_key
from evaluation.runner.sandbox import REPO_ROOT

NAMES = {"base-opus": "opus-one-call", "opus-multiagent": "opus-8-agents"}


def _rows(path: Path) -> list[dict]:
    return [json.loads(x) for x in path.read_text().splitlines() if x.strip()] if path.exists() else []


def import_runs(run: str = "l2", *, experiment: str = "legacy-l2") -> Path:
    root = REPO_ROOT / "out/arch" / run
    specs = {t.project_id: t for t in project_tasks()}
    results = {(r["arm"], r["project_id"]): r for r in _rows(root / "results.jsonl")}
    out = RESULTS / experiment
    out.mkdir(parents=True, exist_ok=True)
    recs = []
    for c in _rows(root / "runchecks.jsonl"):
        spec = specs.get(c["project_id"])
        if spec is None:
            continue
        arm = c["arm"]
        agent = NAMES.get(arm, f"slm-{arm}")
        r = results.get((arm, c["project_id"]), {})
        grade = report_to_grade(c)
        recs.append({
            "schema": SCHEMA, "key": trial_key(agent, spec.id, 0, "legacy"), "provenance": f"imported:out/arch/{run}", "agent": agent,
            "task": spec.id, "repeat": 0, "budget": "legacy", "family": "project_build", "group": spec.group, "task_class": spec.task_class,
            "capability": spec.capability, "control_of": None, "perturbation": None, "status": "completed", "detail": r.get("error") or "",
            "resolved": grade["resolved"], "score": grade["score"], "wall_s": r.get("wall_s"), "cost_usd": None, "cost_basis": None,
            "metrics": {"tok_in": r.get("tok_in"), "tok_out": r.get("tok_out"), "model_calls": r.get("calls")},
            "trace": {}, "grade": grade, "failure": classify("completed", grade, None, has_trajectory=False),
            "split": spec.split, "manifest": {"task_id": spec.id, "agent_id": agent, "arm": arm, "model_checkpoint": None, "agent_commit": None},
        })
    path = out / "trials.jsonl"
    path.write_text("".join(json.dumps(r) + "\n" for r in recs))
    return path
