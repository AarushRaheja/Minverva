"""Every task the harness knows, with a revision hash so a result names exactly what was attempted."""

from __future__ import annotations

import hashlib
import json
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

PRIVATE = Path(__file__).parent / "private"
REVIEW = "audit/task_review.json"


@dataclass
class TaskSpec:
    id: str
    family: str  # repo | project_build
    benchmark: str
    task_class: str
    capability: str
    difficulty: str
    split: str  # dev | validation | test
    group: str  # same family of problems: resampled together, never split across partitions
    instruction: str
    path: Path | None = None
    project_id: str | None = None
    allowed_paths: list[str] = field(default_factory=list)
    target_paths: list[str] = field(default_factory=list)
    canaries: list[str] = field(default_factory=list)
    control_of: str | None = None
    perturbation: str | None = None
    author: str = ""
    independently_reviewed: bool = False
    revision: str = ""
    fail_to_pass: list[str] = field(default_factory=list)
    pass_to_pass: list[str] = field(default_factory=list)
    reviewed_revision: str | None = None


def revision_of(folder: Path) -> str:
    """Everything graded or shown to the agent, leaving out the review that records this hash."""
    h = hashlib.sha256()
    for f in sorted(p for p in folder.rglob("*") if p.is_file() and "__pycache__" not in p.parts):
        rel = f.relative_to(folder).as_posix()
        if rel != REVIEW:
            h.update(rel.encode() + b"\0" + f.read_bytes() + b"\0")
    return h.hexdigest()[:16]


def load_repo_task(folder: Path) -> TaskSpec:
    meta = tomllib.loads((folder / "metadata.toml").read_text())
    review = json.loads((folder / REVIEW).read_text()) if (folder / REVIEW).exists() else {}
    return TaskSpec(id=meta["id"], family="repo", benchmark="private-stress-suite", task_class=meta["task_class"],
                    capability=meta["capability"], difficulty=meta["difficulty"], split=meta["split"],
                    group=meta["group"], instruction=(folder / "instructions.md").read_text(), path=folder,
                    allowed_paths=meta.get("allowed_paths", []), target_paths=meta.get("target_paths", []),
                    canaries=meta.get("canaries", []), control_of=meta.get("control_of"),
                    perturbation=meta.get("perturbation"), author=meta.get("author", ""),
                    independently_reviewed=meta.get("independently_reviewed", False), revision=revision_of(folder),
                    fail_to_pass=review.get("fail_to_pass", []), pass_to_pass=review.get("pass_to_pass", []),
                    reviewed_revision=review.get("revision"))


def repo_tasks() -> list[TaskSpec]:
    return [load_repo_task(d) for d in sorted(PRIVATE.iterdir()) if (d / "metadata.toml").exists()]


def all_tasks(project_build: bool = True) -> list[TaskSpec]:
    tasks = repo_tasks()
    if project_build:
        from evaluation.benchmarks.project_build import project_tasks

        tasks += project_tasks()
    return tasks


def select(tasks: list[TaskSpec], *, split: str = "dev", family: list[str] | None = None,
           ids: list[str] | None = None, task_class: list[str] | None = None) -> list[TaskSpec]:
    out = [t for t in tasks if t.split == split]
    if family:
        out = [t for t in out if t.family in family]
    if task_class:
        out = [t for t in out if t.task_class in task_class]
    if ids:
        out = [t for t in out if t.id in ids]
    return out
