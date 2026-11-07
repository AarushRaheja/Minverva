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


def test_nested_manager_runs_each_task_through_its_domain_specialist(tmp_path):
    from slm.bench.variety import generate_varied
    from slm.domains import ADAPTER
    from slm.manager.spec import ProjectSpec, gold_spec

    p = generate_varied(1, "dev", 0)[0]
    spec = gold_spec(p.plan)
    tracer = Tracer(run_id="nested", trace_dir=tmp_path)
    manager = FakeClient({"ProjectSpec": [spec.model_dump()]})
    plan, d = solve(p, manager_client=manager, specialist_clients=_oracle_clients(tracer), tracer=tracer,
                    nested=True)
    assert plan == p.plan and d.ok, d.failures
    routed = {e.task_id: e.callee for e in tracer.events() if e.kind == "route"}
    assert routed == {t.id: ADAPTER[t.domain] for t in p.plan.tasks}
    assert ProjectSpec.model_validate_json(d.read("SPEC.json")) == spec


def test_nested_spec_that_does_not_compile_is_a_failed_plan(tmp_path):
    from slm.bench.variety import generate_varied
    from slm.manager.spec import gold_spec

    p = generate_varied(1, "dev", 0)[0]
    bad = gold_spec(p.plan).model_dump()
    bad["network"]["groups"][0]["tasks"][0]["deps"] = ["NOPE-9.9"]
    tracer = Tracer(run_id="nested-bad", trace_dir=tmp_path)
    plan, d = solve(p, manager_client=FakeClient({"ProjectSpec": [bad]}),
                    specialist_clients=_oracle_clients(tracer), tracer=tracer, nested=True)
    assert plan is None and d is None
    assert [e.ok for e in tracer.events() if e.kind == "plan"] == [False]


def test_each_specialist_receives_only_one_task_from_its_own_category(tmp_path):
    from slm.bench.variety import generate_varied
    from slm.manager.spec import PREFIX, gold_spec, spec_task_prompts, task_ids

    p = next(x for x in generate_varied(40, "dev", 0) if any(t.kind == "oauth" for t in x.plan.tasks))
    spec = gold_spec(p.plan)
    prompts = spec_task_prompts(spec)
    assert set(prompts) == {t.id for t in p.plan.tasks}
    ids = task_ids(spec)
    for domain, task in spec.tasks():
        prompt = prompts[ids[task.id]]
        assert f"Your task {task.id} [{domain}/{task.kind}]" in prompt and task.acceptance in prompt
        for step in task.steps:
            assert step.id in prompt and step.test.description in prompt and step.test.expected in prompt
        others = [t.id for _, t in spec.tasks() if t.id != task.id]
        assert not any(f"{o} " in prompt or f"{o}." in prompt for o in others), prompt
        assert not any(f"{PREFIX[d]}-" in prompt for d in DOMAINS if d != domain)


def test_nested_pipeline_sends_those_prompts_to_the_specialists(tmp_path):
    from slm.bench.variety import generate_varied
    from slm.domains import ADAPTER
    from slm.manager.spec import gold_spec, spec_task_prompts

    class Recording(OracleSpecialist):
        def __init__(self, seen, domain, tracer):
            super().__init__(tracer=tracer)
            self.seen, self.domain = seen, domain

        async def acomplete(self, system, user, schema, **kw):
            self.seen.append((self.domain, user))
            return await super().acomplete(system, user, schema, **kw)

    p = generate_varied(1, "dev", 0)[0]
    spec = gold_spec(p.plan)
    tracer = Tracer(run_id="packets", trace_dir=tmp_path)
    seen: list[tuple[str, str]] = []
    clients = {d: Recording(seen, d, tracer) for d in DOMAINS}
    plan, d = solve(p, manager_client=FakeClient({"ProjectSpec": [spec.model_dump()]}), specialist_clients=clients,
                    tracer=tracer, nested=True)
    assert plan == p.plan and d.ok, d.failures
    shell = next(t.id for t in p.plan.tasks if t.kind == "layout")
    expected = {k: v for k, v in spec_task_prompts(spec).items() if k != shell}  # code writes the shell
    assert sorted(u for _, u in seen) == sorted(expected.values())
    domain_of = {t.id: t.domain for t in p.plan.tasks}
    assert all(domain_of[tid] == dom for tid, text in expected.items() for dom, u in seen if u == text)


def test_guard_prompt_names_every_page_route_and_other_prompts_do_not_list_them():
    from slm.bench.variety import generate_varied
    from slm.manager.spec import gold_spec, spec_task_prompts

    p = generate_varied(1, "dev", 0)[0]
    prompts = spec_task_prompts(gold_spec(p.plan))
    guard = next(t for t in p.plan.tasks if t.kind == "guards")
    assert all(r in prompts[guard.id] for r in p.plan.routes())
    assert sum("Page routes to protect" in text for text in prompts.values()) == 1


def _team(tmp_path, responses):
    from slm.bench.variety import generate_varied
    from slm.manager.spec import gold_spec

    p = generate_varied(1, "dev", 0)[0]
    tracer = Tracer(run_id="repair", trace_dir=tmp_path)
    clients = {d: OracleSpecialist(tracer=tracer) for d in DOMAINS}
    clients.update(responses(p, tracer))
    manager = FakeClient({"ProjectSpec": [gold_spec(p.plan).model_dump()]})
    return p, solve(p, manager_client=manager, specialist_clients=clients, tracer=tracer, nested=True)


def test_a_task_that_fails_its_contract_is_sent_back_and_fixed(tmp_path):
    from slm.bench.catalog import gold_artifact

    calls = []

    class Flaky(OracleSpecialist):
        async def acomplete(self, system, user, schema, **kw):
            calls.append(user)
            first = len(calls) == 1  # calls run at the same time, so read this before awaiting
            good = await super().acomplete(system, user, schema, **kw)
            if first:
                file = good.files[0]
                return Artifact(files=[ArtifactFile(path=file.path, content="// nothing useful")])
            return good

    p, (plan, d) = _team(tmp_path, lambda p, tr: {"database": Flaky(tracer=tr)})
    assert d.ok, d.failures
    assert any("failed this check" in c for c in calls)


def test_a_task_that_never_passes_stops_after_two_repairs(tmp_path):
    calls = []

    class Broken(OracleSpecialist):
        async def acomplete(self, system, user, schema, **kw):
            calls.append(user)
            return Artifact(files=[ArtifactFile(path="src/database/nope.sql", content="-- nope")])

    p, (plan, d) = _team(tmp_path, lambda p, tr: {"database": Broken(tracer=tr)})
    schemas = sum(t.domain == "database" for t in p.plan.tasks)
    assert len(calls) == schemas * 3 and not d.ok


def test_code_writes_the_shell_and_page_titles():
    from slm.bench.catalog import build_plan, gold_artifact, TRAIN_TEMPLATES
    from slm.pipeline.finish import code_artifact, finish_artifact, written_by_code

    plan = build_plan(TRAIN_TEMPLATES[0])
    shell = next(t for t in plan.tasks if t.kind == "layout")
    assert written_by_code(shell) and code_artifact(plan, shell) == gold_artifact(plan, shell)
    page = next(t for t in plan.tasks if t.kind == "page")
    good = gold_artifact(plan, page)
    wrong = Artifact(files=[ArtifactFile(path=good.files[0].path,
                                         content=good.files[0].content.replace("<h1>Invoice</h1>", "<h1>InvoicePage</h1>"))])
    assert wrong != good and finish_artifact(page, wrong).files == good.files


def test_specialists_arm_addresses_each_task_to_its_domain_adapter(tmp_path):
    from slm.contracts import BASE_MODEL
    from slm.serve.mock import MockVLLM

    p = _project()
    server = MockVLLM()
    tracer = Tracer(run_id="t", trace_dir=tmp_path)
    shared = server.client(BASE_MODEL, tracer=tracer)
    d = asyncio.run(run_plan(p.id, p.plan, {dom: shared for dom in DOMAINS}, tracer, mode="specialists"))
    assert d.ok, d.failures
    assert sorted(server.models()) == sorted(ADAPTER[t.domain] for t in p.plan.tasks)


def test_single_arm_keeps_one_adapter_even_for_an_addressable_client(tmp_path):
    """Regression: the dispatcher re-addressed every for_model() client to spec-<domain>, so the
    single arm on vLLM silently ran the four specialists."""
    from slm.baselines.monolith import single_clients
    from slm.serve.mock import MockVLLM

    p = _project()
    server = MockVLLM()  # answers gold for whichever adapter asks
    tracer = Tracer(run_id="t", trace_dir=tmp_path)
    clients = single_clients(server.client("spec-general", tracer=tracer))
    d = asyncio.run(run_plan(p.id, p.plan, clients, tracer, mode="single"))
    assert d.ok, d.failures
    assert server.models() == ["spec-general"] * len(p.plan.tasks)
    dispatched = [e for e in tracer.events() if e.kind in ("route", "task")]
    assert len(dispatched) == 2 * len(p.plan.tasks)
    assert all(e.adapter == "spec-general" for e in dispatched)  # the trace names who really served it
