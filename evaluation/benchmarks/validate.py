"""A task can't be used until it is shown to fail on the base repo, pass with the reference, and repeat the same way."""

from __future__ import annotations

import json
import shutil
import tempfile
from pathlib import Path

from evaluation.benchmarks.task_registry import REVIEW, TaskSpec, repo_tasks, revision_of
from evaluation.evaluators.correctness import run_tests
from evaluation.runner import workspace

REQUIRED = ("metadata.toml", "instructions.md", "repository", "tests/public", "tests/private", "solution")


def reference_patch(spec: TaskSpec, out: Path) -> None:
    with tempfile.TemporaryDirectory(prefix="agenteval-ref-", dir="/private/tmp") as raw:
        root = Path(raw).resolve()
        tree, git = workspace.prepare(spec.path, root)
        shutil.copytree(spec.path / "solution", tree, dirs_exist_ok=True)
        workspace.capture_patch(tree, git, out)


def review_task(spec: TaskSpec, repeats: int = 3) -> dict:
    problems = [f"missing {r}" for r in REQUIRED if not (spec.path / r).exists()]
    if problems:
        return {"ok": False, "problems": problems}
    repo = spec.path / "repository"
    leaked = [p.name for p in repo.rglob("*") if {"private", "solution"} & set(p.relative_to(repo).parts)]
    problems += [f"agent would see {x}" for x in leaked]
    with tempfile.TemporaryDirectory(prefix="agenteval-rev-", dir="/private/tmp") as raw:
        tmp = Path(raw).resolve()
        empty, ref = tmp / "empty.diff", tmp / "ref.diff"
        empty.write_bytes(b"")
        reference_patch(spec, ref)
        base = run_tests(spec, empty)["tests"]
        runs = [run_tests(spec, ref) for _ in range(repeats)]
    first = runs[0]["tests"]
    if any(r["tests"] != first for r in runs):
        problems.append("flaky: the reference gives different results between runs")
    if not all(r["build"] for r in runs):
        problems.append("reference doesn't compile")
    not_passing = [t for t, v in first.items() if v != "pass"]
    problems += [f"reference fails {t}" for t in not_passing]
    f2p = sorted(t for t, v in first.items() if v == "pass" and base.get(t) != "pass")
    p2p = sorted(t for t, v in first.items() if v == "pass" and base.get(t) == "pass")
    if not f2p:
        problems.append("no test shows the initial failure")
    if not any(t.startswith("private::") for t in f2p):
        problems.append("no hidden test fails on the base repo")
    if any(t not in first for t in base if "_FailedTest" not in t):  # a module that can't import yet isn't a removal
        problems.append("the reference removes tests")
    return {"ok": not problems, "problems": problems, "revision": revision_of(spec.path), "fail_to_pass": f2p,
            "pass_to_pass": p2p, "reference_runs": repeats, "independently_reviewed": spec.independently_reviewed,
            "author": spec.author}


def validate_all(write: bool = True) -> list[tuple[str, dict]]:
    out = []
    for spec in repo_tasks():
        r = review_task(spec)
        if write and r["ok"]:
            p = spec.path / REVIEW
            p.parent.mkdir(exist_ok=True)
            p.write_text(json.dumps(r, indent=1) + "\n")
        out.append((spec.id, r))
    return out
