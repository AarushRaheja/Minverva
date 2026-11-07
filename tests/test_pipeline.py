from __future__ import annotations

import asyncio
import json

from slm.bench.catalog import TRAIN_TEMPLATES, build_plan, gold_artifacts
from slm.bench.projects import generate_balanced
from slm.contracts import DOMAINS, Artifact, ArtifactFile
from slm.domains import ADAPTER
from slm.llm.fake import FakeClient
from slm.pipeline.dispatch import run_plan, solve, solve_project
from slm.pipeline.oracle import OracleSpecialist
from slm.trace import Tracer


def _oracle_clients(tracer):
    return {d: OracleSpecialist(tracer=tracer) for d in DOMAINS}


def _project():
    return generate_balanced(1, "dev", 0)[0]


def test_gold_plan_with_oracle_specialists_passes_every_check(tmp_path):
    p = _project()
    tracer = Tracer(run_id="t", trace_dir=tmp_path)
    d = asyncio.run(run_plan(p.id, p.plan, _oracle_clients(tracer), tracer, mode="gold"))
    assert d.ok, d.failures
    final = [e for e in tracer.events() if e.kind == "final"]
    assert len(final) == 1 and final[0].output == "pass"


def test_each_task_is_routed_to_its_domain_adapter(tmp_path):
    p = _project()
    tracer = Tracer(run_id="t", trace_dir=tmp_path)
    asyncio.run(run_plan(p.id, p.plan, _oracle_clients(tracer), tracer, mode="gold"))
    routes = [e for e in tracer.events() if e.kind == "route"]
    assert len(routes) == len(p.plan.tasks)
    for e in routes:
        task = p.plan.task(e.task_id)
        assert e.adapter == ADAPTER[task.domain]
        assert e.domain == task.domain


def test_parallel_dispatch_is_faster_than_serial(tmp_path):
    """A slow specialist makes the wall clock of the two schedules measurable."""
    import time

    class SlowOracle(OracleSpecialist):
        def _trace_and_return(self, artifact, system, user, caller, callee, ctx, t0):
            time.sleep(0.01)
            return super()._trace_and_return(artifact, system, user, caller, callee, ctx, t0)

    p = _project()
    walls = {}
    for parallel in (True, False):
        tracer = Tracer(run_id=f"w{parallel}", trace_dir=tmp_path)
        clients = {d: SlowOracle(tracer=tracer) for d in DOMAINS}
        t = time.perf_counter()
        asyncio.run(run_plan(p.id, p.plan, clients, tracer, mode="gold", parallel=parallel))
        walls[parallel] = time.perf_counter() - t
    assert walls[True] < walls[False] * 0.7, walls


def test_serial_dispatch_finishes_tasks_one_at_a_time(tmp_path):
    p = _project()
    tracer = Tracer(run_id="ser", trace_dir=tmp_path)
    asyncio.run(run_plan(p.id, p.plan, _oracle_clients(tracer), tracer, mode="gold", parallel=False))
    tasks = [e for e in tracer.events() if e.kind == "task"]
    assert len(tasks) == len(p.plan.tasks)
    for prev, cur in zip(tasks, tasks[1:]):
        assert cur.t_start >= prev.t_end


def test_failed_task_is_recorded_and_blocks_the_deliverable(tmp_path):
    p = _project()
    tracer = Tracer(run_id="t", trace_dir=tmp_path)
    bad = FakeClient({"Artifact": [{"files": [{"path": "src/nowhere.py", "content": "x"}], "summary": "bad"}]},
                     tracer=tracer)
    d = asyncio.run(run_plan(p.id, p.plan, {dom: bad for dom in DOMAINS}, tracer, mode="specialists"))
    assert not d.ok
    tasks = [e for e in tracer.events() if e.kind == "task"]
    assert tasks and not any(e.ok for e in tasks)


def test_client_exception_is_a_task_failure_not_a_crash(tmp_path):
    p = _project()
    tracer = Tracer(run_id="t", trace_dir=tmp_path)

    class Boom(FakeClient):
        def _raw(self, system, user, json_schema):
            raise RuntimeError("no server")

    d = asyncio.run(run_plan(p.id, p.plan, {dom: Boom(tracer=tracer) for dom in DOMAINS}, tracer))
    assert not d.ok
    final = [e for e in tracer.events() if e.kind == "final"][-1]
    assert final.ok  # the run completed; the product is what failed
    assert final.output.startswith("fail:")


def test_solve_uses_the_manager_plan_not_the_gold_plan(tmp_path):
    p = _project()
    tracer = Tracer(run_id="t", trace_dir=tmp_path)
    manager = FakeClient(tracer=tracer)  # answers with the notes-app plan
    plan, d = solve(p, manager_client=manager, specialist_clients=_oracle_clients(tracer), tracer=tracer)
    assert plan is not None and plan.name == "notes app"
    assert d is not None and d.project_id == p.id
    # the oracle renders gold artifacts for the *manager's* plan, so it still integrates
    assert d.ok, d.failures
    assert any(e.kind == "plan" and e.ok for e in tracer.events())


def test_invalid_manager_plan_stops_the_run(tmp_path):
    p = _project()
    tracer = Tracer(run_id="t", trace_dir=tmp_path)
    manager = FakeClient({"ProjectPlan": ["not json"]}, tracer=tracer)
    plan, d = solve(p, manager_client=manager, specialist_clients=_oracle_clients(tracer), tracer=tracer)
    assert plan is None and d is None
    plan_ev = [e for e in tracer.events() if e.kind == "plan"][-1]
    assert plan_ev.ok is False and plan_ev.error
    final = [e for e in tracer.events() if e.kind == "final"][-1]
    assert final.ok is False and final.output is None


def test_gold_plan_mode_needs_no_manager(tmp_path):
    p = _project()
    tracer = Tracer(run_id="t", trace_dir=tmp_path)
    plan, d = asyncio.run(solve_project(
        p, manager_client=None, specialist_clients=_oracle_clients(tracer), tracer=tracer, gold_plan=True,
    ))
    assert plan is not None and d is not None and d.ok


def test_single_generalist_arm_uses_one_client_for_all_tasks(tmp_path):
    from slm.baselines.monolith import single_clients

    p = _project()
    tracer = Tracer(run_id="t", trace_dir=tmp_path)
    shared = FakeClient(
        {"Artifact": [Artifact(files=[ArtifactFile(path="src/x.py", content="x")]).model_dump()]},
        tracer=tracer,
    )
    d = asyncio.run(run_plan(p.id, p.plan, single_clients(shared), tracer, mode="single"))
    assert not d.ok  # a single generalist that ignores the task contract scores zero
    assert len(shared.calls) == len(p.plan.tasks)
