"""Trace conformance for the serving path (slm/trace.py FROZEN kinds), through the real vLLM client.

Every metric is computed from traces alone, so these pin what the dispatcher must write: one final
per project, one route + one task per task, and enough context for bench.score to rebuild the
deliverable pass rate without ever seeing a Deliverable.
"""

from __future__ import annotations

import asyncio
from collections import Counter

import pytest

from slm.bench.catalog import gold_artifact
from slm.bench.projects import generate_balanced
from slm.bench.score import score_runs
from slm.contracts import BASE_MODEL, DOMAINS, Artifact, ArtifactFile
from slm.llm.fake import FakeClient
from slm.llm.vllm import VLLMLoRAClient
from slm.pipeline.dispatch import solve_project
from slm.pipeline.oracle import CALL
from slm.serve import smoke
from slm.serve.adapters import TRAINED_MARKER, dummy_targets
from slm.serve.mock import BASE_URL, MockVLLM
from slm.trace import Tracer, load

WRONG = Artifact(files=[ArtifactFile(path="src/auth/wrong.py", content="pass")], summary="wrong")


def _answer_failing_auth_of(bad_plan):
    """Gold for every task, except the auth tasks of one project: those miss their canonical file."""
    def answer(body: dict) -> str:
        plan, task = CALL.get()
        if plan is bad_plan and task.domain == "auth":
            return WRONG.model_dump_json()
        return gold_artifact(plan, task).model_dump_json()
    return answer


@pytest.fixture
def run(tmp_path):
    """Four dev projects with gold plans through MockVLLM; the second one fails on auth."""
    projects = generate_balanced(4, "dev", 0)
    bad = projects[1]
    server = MockVLLM(_answer_failing_auth_of(bad.plan))
    tracer = Tracer(run_id="conformance", trace_dir=tmp_path)
    shared = server.client(BASE_MODEL, tracer=tracer)

    async def solve_all():
        return [await solve_project(p, manager_client=None, specialist_clients={d: shared for d in DOMAINS},
                                    tracer=tracer, gold_plan=True, mode="specialists") for p in projects]

    results = asyncio.run(solve_all())
    return projects, bad, [d for _, d in results], load(tracer.path)


def test_one_final_and_one_plan_per_project(run):
    projects, _, _, events = run
    for p in projects:
        kinds = Counter(e.kind for e in events if e.project_id == p.id)
        assert kinds["final"] == 1 and kinds["plan"] == 1, (p.id, kinds)


def test_one_route_and_one_task_event_per_task(run):
    projects, _, _, events = run
    for p in projects:
        want = Counter(t.id for t in p.plan.tasks)
        for kind in ("route", "task"):
            got = Counter(e.task_id for e in events if e.project_id == p.id and e.kind == kind)
            assert got == want, (p.id, kind)


def test_every_event_carries_the_runs_arm_and_llm_events_carry_the_task(run):
    projects, _, _, events = run
    assert {e.mode for e in events} == {"specialists"}  # the gold-plan event too
    llm = [e for e in events if e.kind == "llm"]
    assert len(llm) == sum(len(p.plan.tasks) for p in projects)  # gold artifacts validate first time
    for e in llm:
        assert e.project_id and e.task_id and e.domain in DOMAINS and e.dep_level is not None
        assert e.model == e.adapter == e.callee  # the request went to the adapter the route chose


def test_score_rebuilds_the_deliverable_pass_rate_from_the_trace_alone(run):
    projects, bad, deliverables, events = run
    truth = sum(d.ok for d in deliverables) / len(deliverables)
    assert truth == 0.75  # the fixture really mixes passes and a failure

    metrics, per_item = score_runs(events, {p.id: p for p in projects})
    assert len(metrics) == 1 and metrics[0].mode == "specialists"
    m = metrics[0]
    assert m.n == len(projects) and m.deliverable_ok == truth and m.failures == 0

    n_tasks = sum(len(p.plan.tasks) for p in projects)
    bad_auth = sum(t.domain == "auth" for t in bad.plan.tasks)
    all_auth = sum(t.domain == "auth" for p in projects for t in p.plan.tasks)
    assert m.task_acc == (n_tasks - bad_auth) / n_tasks
    assert m.by_domain["auth"] == (all_auth - bad_auth) / all_auth
    assert all(m.by_domain[d] == 1.0 for d in DOMAINS if d != "auth")
    assert m.calls == n_tasks / len(projects)

    rec = {r.project_id: r for r in per_item[(m.run_id, m.mode)]}
    failed = next(d for d in deliverables if not d.ok)
    assert not rec[bad.id].ok and rec[bad.id].first_failure == failed.failures[0]


def test_a_failed_plan_writes_one_final_and_no_dispatch(tmp_path):
    p = generate_balanced(1, "dev", 0)[0]
    tracer = Tracer(run_id="t", trace_dir=tmp_path)
    manager = FakeClient({"ProjectPlan": ["not json"]}, tracer=tracer)
    plan, d = asyncio.run(solve_project(p, manager_client=manager, specialist_clients={}, tracer=tracer))
    assert plan is None and d is None
    events = load(tracer.path)
    kinds = Counter(e.kind for e in events)
    assert kinds["final"] == 1 and kinds["plan"] == 1 and kinds["route"] == kinds["task"] == 0
    m = score_runs(events, {p.id: p})[0][0]
    assert m.n == 1 and m.deliverable_ok == 0.0 and m.plan_valid == 0.0  # counted, not dropped


# --- smoke (task 1's command) ---------------------------------------------------


def test_smoke_runs_end_to_end_against_a_mock_server(monkeypatch):
    """Regression: the smoke asked for a 'manager' domain and died with StopIteration before any request."""
    fixed = Artifact(files=[], summary="untrained").model_dump_json()
    server = MockVLLM(lambda body: gold_artifact(*CALL.get()).model_dump_json() if CALL.get() else fixed)

    class Mocked(VLLMLoRAClient):
        def __init__(self, model, tracer=None, base_url=None, **kw):
            super().__init__(model, tracer, base_url, transport=server.transport,
                             async_transport=server.transport, **kw)

    monkeypatch.setattr(smoke, "VLLMLoRAClient", Mocked)
    out = smoke.run_smoke(BASE_URL)
    for d in DOMAINS:
        assert out[f"first_{d}_s"] >= 0 and out[f"warm_{d}_s"] >= 0
    n = len(smoke.PLAN.tasks)
    for schedule in ("parallel", "serial"):
        r = out[schedule]
        assert r["tasks_ok"] == r["tasks_total"] == n and r["calls"] == n and r["retries"] == 0
        assert r["checks_failed"] == []
    assert out["parallel_speedup"] is not None


# --- dummy adapters ---------------------------------------------------------------


def test_dummies_never_replace_a_trained_adapter(tmp_path):
    (tmp_path / "spec-auth").mkdir()
    (tmp_path / "spec-auth" / TRAINED_MARKER).write_text("{}")
    (tmp_path / "spec-network").mkdir()  # an earlier dummy: safe to refresh
    write, kept = dummy_targets(tmp_path, ["spec-database", "spec-auth", "spec-network", "spec-frontend"])
    assert write == ["spec-database", "spec-network", "spec-frontend"]
    assert kept == ["spec-auth"]
