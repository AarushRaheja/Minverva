"""The manager and specialists under test, reached through its own command line so its code stays independent of the
evaluator. It builds new projects from a brief, and has no way to read or edit an existing repository, so a repository
task comes back UNSUPPORTED rather than counting as a coding failure."""

from __future__ import annotations

import json
import shutil
import sys
import tempfile
from pathlib import Path

from evaluation.benchmarks.project_build import project_index
from evaluation.core import BUDGET_EXHAUSTED, COMPLETED, ENVIRONMENT_FAILURE, UNSUPPORTED, AgentResult, Budget, Task
from evaluation.runner.process import run_limited
from evaluation.runner.sandbox import REPO_ROOT
from evaluation.runner.trajectory_logger import TrajectoryLogger


class SlmAgent:
    def __init__(self, manifest: dict):
        self.manifest = manifest
        self.arm = manifest["arm"]

    def run(self, task: Task, budget: Budget) -> AgentResult:
        art = Path(task.artifacts_path)
        log = TrajectoryLogger(art / "trajectory.jsonl")
        metrics = art / "metrics.json"
        done = lambda st, d="": AgentResult(task.task_id, None, st, str(log.path), str(metrics), d)  # noqa: E731
        m = {"steps": 0, "model_calls": 0, "tool_calls": 0, "tok_in": 0, "tok_out": 0}
        if task.family != "project_build" or task.project_id is None:
            metrics.write_text(json.dumps(m))
            return done(UNSUPPORTED, "this agent has no mode for editing an existing repository")
        with tempfile.TemporaryDirectory(prefix="agenteval-slm-", dir="/private/tmp") as raw:
            root = Path(raw)
            argv = [sys.executable, "-m", "slm.arch", "run", "--run", "t", "--out", str(root), "--arms", self.arm,
                    "--pick", str(project_index(task.project_id)), "--model", self.manifest["model_id"]]
            out: list[str] = []
            r = run_limited(argv, cwd=str(REPO_ROOT), env=None, wall_s=budget.wall_time_seconds, output=out)
            for line in out:
                log.log("message", text=line.rstrip())
            results = root / "t/results.jsonl"
            rows = [json.loads(x) for x in results.read_text().splitlines()] if results.exists() else []
            row = next((x for x in rows if x["arm"] == self.arm), None)
            m |= {"agent_cpu_s": r.cpu_s, "agent_peak_rss_mb": r.peak_rss_mb}
            if row is None:
                metrics.write_text(json.dumps(m))
                if r.timed_out:
                    return done(BUDGET_EXHAUSTED, "stopped at the budget")
                return done(ENVIRONMENT_FAILURE, "".join(out)[-400:])
            m |= {"model_calls": row["calls"], "steps": row["calls"], "tok_in": row["tok_in"], "tok_out": row["tok_out"],
                  "plan_valid": row.get("plan_valid"), "plan_recall": row.get("plan_recall"), "agent_error": row.get("error")}
            built = root / "t/files" / self.arm / task.project_id
            if built.is_dir():
                shutil.copytree(built, task.workspace_path, dirs_exist_ok=True)
        metrics.write_text(json.dumps(m, indent=1))
        return done(COMPLETED)
