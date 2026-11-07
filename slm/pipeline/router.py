"""Dispatch: one task -> its domain specialist's adapter name. The rule is the architecture."""

from __future__ import annotations

from slm.contracts import DOMAINS, ProjectPlan, Task
from slm.domains import ADAPTER
from slm.trace import Tracer


def adapter_for(task: Task) -> str:
    return ADAPTER[task.domain]


def route(plan: ProjectPlan, task: Task, *, tracer: Tracer | None = None, mode: str | None = None,
          project_id: str | None = None, dep_level: int | None = None) -> str:
    """Record the dispatch decision (no model call) and return the adapter to call."""
    assert task.domain in DOMAINS, task.domain
    name = adapter_for(task)
    if tracer is not None:
        tracer.record(
            kind="route", caller="dispatcher", callee=name, adapter=name, mode=mode, domain=task.domain,
            project_id=project_id, task_id=task.id, dep_level=dep_level,
        )
    return name
