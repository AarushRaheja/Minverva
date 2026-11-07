from __future__ import annotations

import asyncio

from slm.bench.projects import generate_balanced
from slm.bench.score import score_runs
from slm.contracts import DOMAINS
from slm.llm.fake import FakeClient
from slm.pipeline.dispatch import run_plan, solve_project
from slm.pipeline.oracle import OracleSpecialist
from slm.trace import Tracer


def _run(projects, tmp_path, run_id="run"):
    tracer = Tracer(run_id=run_id, trace_dir=tmp_path)
    clients = {d: OracleSpecialist(tracer=tracer) for d in DOMAINS}
    for p in projects:
        asyncio.run(solve_project(p, manager_client=None, specialist_clients=clients,
                                  tracer=tracer, gold_plan=True, mode="gold"))
    return tracer.events()


def test_perfect_run_scores_one(tmp_path):
    projects = generate_balanced(3, "dev", 0)
    events = _run(projects, tmp_path)
    metrics, per_item = score_runs(events, {p.id: p for p in projects})
    assert len(metrics) == 1
    m = metrics[0]
    assert m.n == 3
    assert m.deliverable_ok == 1.0
    assert m.plan_valid == 1.0
    assert m.task_acc == 1.0
    assert set(m.by_domain) == set(DOMAINS)
    assert all(v == 1.0 for v in m.by_domain.values())
    assert m.failures == 0
    assert m.p50_s is not None and m.p95_s is not None
    assert len(per_item[("run", "gold")]) == 3


def test_broken_specialists_score_zero_product_but_record_attempts(tmp_path):
    projects = generate_balanced(2, "dev", 0)
    tracer = Tracer(run_id="bad", trace_dir=tmp_path)
    bad = FakeClient({"Artifact": [{"files": [], "summary": "nothing"}]}, tracer=tracer)
    for p in projects:
        asyncio.run(run_plan(p.id, p.plan, {d: bad for d in DOMAINS}, tracer, mode="specialists"))
    metrics, _ = score_runs(tracer.events(), {p.id: p for p in projects})
    m = metrics[0]
    assert m.deliverable_ok == 0.0
    assert m.task_acc == 0.0
    assert m.mode == "specialists"


def test_unknown_projects_are_ignored(tmp_path):
    projects = generate_balanced(1, "dev", 0)
    events = _run(projects, tmp_path)
    metrics, _ = score_runs(events, {})
    assert metrics == []


def test_by_depth_groups_projects(tmp_path):
    projects = generate_balanced(4, "dev", 0)
    events = _run(projects, tmp_path)
    metrics, _ = score_runs(events, {p.id: p for p in projects})
    depths = metrics[0].by_depth
    assert depths and sum(c.n for c in depths.values()) == len(projects)
