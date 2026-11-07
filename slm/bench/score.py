"""Metrics from traces alone: per-run deliverable pass rate, per-task and per-domain accuracy,
plan validity, and the latency/call-cost of the whole manager -> specialists -> integrator path.

Reads the frozen event kinds of slm/trace.py:
- kind="plan": the manager's plan (ok=False means the run never dispatched).
- kind="route"/"task": one per task; the LAST task event per task_id counts.
- kind="final": exactly one per project; `output` == "pass" is the end-to-end success signal.
- kind="llm": calls, tokens and retries.
Latency per project = first t_start to last t_end over its events.
"""

from __future__ import annotations

import json
import logging
from collections import defaultdict
from pathlib import Path

from pydantic import BaseModel

from slm.bench.stats import percentile
from slm.contracts import DOMAINS, Artifact, Project
from slm.domains import canonical_path, provide_token, provides_of
from slm.trace import TraceEvent
from slm.trace import load as load_trace

log = logging.getLogger(__name__)


def gate_ok(domain: str, kind: str, target: str, artifact: Artifact) -> bool:
    """Offline gate used by the trainer: right canonical file, and every provided symbol present."""
    want = canonical_path(domain, kind, target)
    by_path = {f.path: f.content for f in artifact.files}
    if want not in by_path:
        return False
    text = by_path[want]
    return all(provide_token(s) in text for s in provides_of(domain, kind, target))


class Core(BaseModel):
    n: int
    deliverable_ok: float  # share of projects whose integrated product passed every check
    plan_valid: float | None = None
    task_acc: float | None = None  # share of tasks whose artifact passed its contract
    by_domain: dict[str, float] = {}
    p50_s: float | None = None
    p95_s: float | None = None
    calls: float = 0.0  # mean model calls per project
    tokens: float = 0.0  # mean input+output tokens per project (0 for the fake client)
    retries: int = 0
    failures: int = 0  # projects with no successful final event


class RunMetrics(Core):
    run_id: str
    mode: str | None = None
    by_depth: dict[int, Core] = {}


class ProjectResult(BaseModel):
    project_id: str
    template_id: str | None = None
    depth: int | None = None
    ok: bool
    first_failure: str | None = None
    plan_valid: bool | None = None  # None when the run used a gold plan (no manager to grade)
    tasks_total: int
    tasks_ok: int
    domain_ok: dict[str, list[bool]] = {}
    latency_s: float = 0.0
    calls: int = 0
    tokens: int = 0
    retries: int = 0
    failures: int = 0


def _tokens(e: TraceEvent) -> int:
    return e.input_tokens + e.output_tokens


def score_project(project: Project, events: list[TraceEvent]) -> ProjectResult:
    plans = [e for e in events if e.kind == "plan"]
    finals = [e for e in events if e.kind == "final"]
    final = finals[-1] if finals else None
    tasks = {e.task_id: e for e in events if e.kind == "task" and e.task_id}
    llm = [e for e in events if e.kind == "llm"]
    ok = final is not None and final.ok and (final.output or "").startswith("pass")
    if final is None:
        log.warning("project %s: no final event (counted as failure)", project.id)

    domain_ok: dict[str, list[bool]] = {}
    for e in tasks.values():
        if e.domain in DOMAINS:
            domain_ok.setdefault(e.domain, []).append(e.ok)

    timed = [e for e in events if e.t_start is not None and e.t_end is not None]
    latency = (max(e.t_end for e in timed) - min(e.t_start for e in timed)) if timed else 0.0
    first_failure = None
    if not ok and final is not None and final.output:
        first_failure = final.output.split(":", 1)[-1] if ":" in final.output else final.output
    return ProjectResult(
        project_id=project.id, template_id=project.template_id, depth=project.depth, ok=ok,
        first_failure=first_failure,
        plan_valid=(plans[-1].ok if plans else None),
        tasks_total=len(tasks), tasks_ok=sum(e.ok for e in tasks.values()),
        domain_ok=domain_ok, latency_s=latency, calls=len(llm),
        tokens=sum(_tokens(e) for e in llm),
        retries=sum(1 for e in llm if e.attempt > 1),
        failures=int(final is None),
    )


def aggregate(rs: list[ProjectResult]) -> Core:
    n = len(rs)
    tot = sum(r.tasks_total for r in rs)
    lat = [r.latency_s for r in rs]
    doms: dict[str, list[bool]] = defaultdict(list)
    for r in rs:
        for d, flags in r.domain_ok.items():
            doms[d].extend(flags)
    plans = [r.plan_valid for r in rs if r.plan_valid is not None]
    return Core(
        n=n,
        deliverable_ok=sum(r.ok for r in rs) / n,
        plan_valid=sum(plans) / len(plans) if plans else None,
        task_acc=sum(r.tasks_ok for r in rs) / tot if tot else None,
        by_domain={d: sum(v) / len(v) for d, v in sorted(doms.items()) if v},
        p50_s=percentile(lat, 50), p95_s=percentile(lat, 95),
        calls=sum(r.calls for r in rs) / n, tokens=sum(r.tokens for r in rs) / n,
        retries=sum(r.retries for r in rs), failures=sum(r.failures for r in rs),
    )


def score_runs(events: list[TraceEvent], projects: dict[str, Project]):
    """-> (list[RunMetrics], {(run_id, mode): [ProjectResult]}). Unknown projects/events are ignored."""
    by_project: dict[tuple[str, str], list[TraceEvent]] = defaultdict(list)
    for e in events:
        if e.project_id in projects and e.kind in ("llm", "plan", "route", "task", "final"):
            by_project[(e.run_id, e.project_id)].append(e)
    groups: dict[tuple[str, str | None], dict[str, list[TraceEvent]]] = defaultdict(dict)
    for (run_id, pid), evs in by_project.items():
        ctx = next((e for k in ("final", "plan", "task", "llm") for e in evs if e.kind == k), evs[0])
        groups[(run_id, ctx.mode)][pid] = evs
    metrics, per_item = [], {}
    for key in sorted(groups, key=str):
        rs = [score_project(projects[pid], evs) for pid, evs in sorted(groups[key].items())]
        per_item[key] = rs
        by_depth = {
            d: aggregate([r for r in rs if r.depth == d])
            for d in sorted({r.depth for r in rs if r.depth is not None})
        }
        metrics.append(RunMetrics(run_id=key[0], mode=key[1], **aggregate(rs).model_dump(),
                                  by_depth=by_depth))
    return metrics, per_item


def load_projects(paths: list[Path]) -> dict[str, Project]:
    out = {}
    for p in paths:
        for line in Path(p).read_text().splitlines():
            if line.strip():
                pr = Project.model_validate(json.loads(line))
                out[pr.id] = pr
    return out


def score_files(trace_paths: list[Path], project_paths: list[Path]) -> list[RunMetrics]:
    events = [e for p in trace_paths for e in load_trace(Path(p))]
    return score_runs(events, load_projects(project_paths))[0]
