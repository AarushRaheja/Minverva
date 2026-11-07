from __future__ import annotations

import pytest
from pydantic import ValidationError

from slm.bench.catalog import TRAIN_TEMPLATES, build_plan, gold_artifacts
from slm.contracts import (
    Artifact, ArtifactFile, ProjectPlan, Task, check_task, integrate, task_ok,
)

TPL = TRAIN_TEMPLATES[0]


def _task(**kw) -> Task:
    base = dict(id="t1", domain="database", kind="schema", target="orders", detail="orders table")
    return Task(**{**base, **kw})


def test_task_accepts_a_valid_kind():
    assert _task().provides() == ["table:orders"]


def test_task_rejects_kind_from_another_domain():
    with pytest.raises(ValidationError):
        _task(kind="rest")


def test_task_rejects_non_slug_target():
    with pytest.raises(ValidationError):
        _task(target="Order Table")


def test_task_rejects_self_dependency():
    with pytest.raises(ValidationError):
        _task(deps=["t1"])


def test_plan_requires_all_four_specialists():
    with pytest.raises(ValidationError, match="all four specialists"):
        ProjectPlan(name="x", tasks=[_task()])


def test_plan_rejects_forward_dependency():
    tasks = build_plan(TPL).tasks
    broken = [t.model_copy(deep=True) for t in tasks]
    broken[0].deps = [broken[-1].id]
    with pytest.raises(ValidationError, match="before it is defined"):
        ProjectPlan(name="x", tasks=broken)


def test_plan_levels_group_independent_work():
    plan = build_plan(TPL)
    levels = plan.levels()
    assert sum(len(lv) for lv in levels) == len(plan.tasks)
    by_id = {t.id: t for t in plan.tasks}
    for a, b in zip(levels[1:], levels[2:]):
        for tid in b:
            assert by_id[tid].deps, f"{tid} in a later level must depend on something"
    # the three tables have no dependencies, so the first level holds all of them
    assert len(levels[0]) >= 2


def test_providers_and_routes():
    plan = build_plan(TPL)
    providers = plan.providers()
    assert providers["table:invoice"] == "t2"
    assert "/invoices" in plan.routes()
    assert "InvoicePage" in plan.components()


def test_gold_artifact_satisfies_its_task():
    plan = build_plan(TPL)
    for task in plan.tasks:
        ok, detail = task_ok(plan, task, gold_artifacts(plan)[task.id])
        assert ok, f"{task.id} {detail}"


def test_gold_pipeline_integrates_cleanly():
    plan = build_plan(TPL)
    deliverable = integrate("p1", plan, gold_artifacts(plan))
    assert deliverable.ok, deliverable.failures
    assert deliverable.entry == "src/main.py"
    assert deliverable.read("src/app.py") is not None
    assert all(w.startswith("t") for w in deliverable.wiring)


def test_missing_artifact_is_reported():
    plan = build_plan(TPL)
    arts = gold_artifacts(plan)
    del arts["t3"]
    d = integrate("p1", plan, arts)
    assert not d.ok
    assert "all_tasks_delivered" in d.failures


def test_wrong_path_fails_the_layout_check():
    plan = build_plan(TPL)
    task = plan.tasks[0]
    bad = Artifact(files=[ArtifactFile(path="src/database/wrong.sql", content="CREATE TABLE users")])
    ok, detail = task_ok(plan, task, bad)
    assert not ok and detail.startswith("layout:")


def test_missing_provided_symbol_fails():
    plan = build_plan(TPL)
    rest = next(t for t in plan.tasks if t.kind == "rest")
    broken = Artifact(files=[ArtifactFile(
        path=f"src/network/{rest.target}_api.py",
        content=rest.detail,  # no decorators at all
    )])
    checks = {c.name: c.ok for c in check_task(plan, rest, broken)}
    assert checks[f"provides:{rest.id}:endpoint:GET /api/{rest.target}s"] is False


def test_frontend_endpoint_that_no_router_serves_fails():
    plan = build_plan(TPL)
    arts = gold_artifacts(plan)
    page = next(t for t in plan.tasks if t.kind == "page")
    path = f"src/frontend/{page.target.capitalize()}Page.tsx"
    arts[page.id] = Artifact(files=[ArtifactFile(
        path=path,
        content='export const route = "/invoices";\n'
                'export function InvoicePage() { fetch("/api/does_not_exist"); }\n',
    )])
    d = integrate("p1", plan, arts)
    assert "frontend_endpoints_resolve" in d.failures


def test_table_used_by_the_api_must_exist():
    plan = build_plan(TPL)
    arts = gold_artifacts(plan)
    rest = next(t for t in plan.tasks if t.kind == "rest")
    good = arts[rest.id].files[0]
    arts[rest.id] = Artifact(files=[ArtifactFile(
        path=good.path, content=good.content.replace(f"FROM {rest.target}", "FROM ghost_table"),
    )])
    d = integrate("p1", plan, arts)
    assert "tables_defined" in d.failures


def test_path_conflict_is_detected():
    plan = build_plan(TPL)
    arts = gold_artifacts(plan)
    a, b = plan.tasks[0], plan.tasks[1]
    arts[b.id] = Artifact(files=[ArtifactFile(path=arts[a.id].files[0].path, content="different")])
    d = integrate("p1", plan, arts)
    assert "no_path_conflicts" in d.failures
