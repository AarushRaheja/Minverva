from __future__ import annotations

import pytest

from slm.bench.catalog import HELDOUT_TEMPLATES, TRAIN_TEMPLATES, build_plan, gold_artifact, gold_artifacts
from slm.bench.projects import generate, generate_balanced
from slm.contracts import DOMAINS, integrate
from slm.domains import ADAPTER, KINDS, canonical_path, provide_token, provides_of, requires_of, use_token


def test_adapter_names_are_distinct_and_domain_specific():
    assert len(set(ADAPTER.values())) == len(DOMAINS)
    assert set(ADAPTER) == set(DOMAINS)


@pytest.mark.parametrize("tpl", TRAIN_TEMPLATES + HELDOUT_TEMPLATES, ids=lambda t: t.id)
def test_every_template_builds_a_plan_that_integrates(tpl):
    plan = build_plan(tpl)
    d = integrate(tpl.id, plan, gold_artifacts(plan))
    assert d.ok, d.failures
    assert all(t.domain in DOMAINS for t in plan.tasks)


@pytest.mark.parametrize("tpl", TRAIN_TEMPLATES + HELDOUT_TEMPLATES, ids=lambda t: t.id)
def test_gold_artifacts_carry_both_their_provide_and_use_tokens(tpl):
    plan = build_plan(tpl)
    for task in plan.tasks:
        text = gold_artifact(plan, task).files[0].content
        for sym in provides_of(task.domain, task.kind, task.target):
            assert provide_token(sym) in text, (task.id, sym)
        for sym in plan.requires(task):
            assert use_token(sym) in text, (task.id, sym)


def test_kinds_cover_every_domain():
    assert set(KINDS) == set(DOMAINS)
    assert "schema" in KINDS["database"]
    assert "rest" in KINDS["network"]


def test_canonical_paths_are_unique_per_task():
    plan = build_plan(TRAIN_TEMPLATES[1])
    paths = [canonical_path(t.domain, t.kind, t.target) for t in plan.tasks]
    assert len(paths) == len(set(paths))


def test_requires_are_provided_by_earlier_tasks():
    plan = build_plan(TRAIN_TEMPLATES[2])
    provided: set[str] = set()
    for t in plan.tasks:
        assert all(s in provided for s in plan.requires(t)), t.id
        provided |= set(t.provides())


def test_layout_requires_every_page_route_and_component():
    plan = build_plan(TRAIN_TEMPLATES[3])
    layout = next(t for t in plan.tasks if t.kind == "layout")
    req = plan.requires(layout)
    assert any(s.startswith("route:") for s in req)
    assert any(s.startswith("component:") for s in req)


def test_requires_of_is_pure():
    assert requires_of("network", "rest", "orders") == ["table:orders", "guard:session"]
    assert requires_of("database", "schema", "orders") == []


def test_projects_are_deterministic_and_use_heldout_templates_for_test():
    a = generate(4, "train", 7)
    b = generate(4, "train", 7)
    assert [p.id for p in a] == [p.id for p in b]
    assert [p.plan.model_dump() for p in a] == [p.plan.model_dump() for p in b]
    test = generate(6, "test", 7)
    assert all(p.template_id in {t.id for t in HELDOUT_TEMPLATES} for p in test)
    train = generate(6, "train", 7)
    assert all(p.template_id in {t.id for t in TRAIN_TEMPLATES} for p in train)


def test_project_metadata_matches_the_plan():
    for p in generate_balanced(6, "dev", 0):
        assert p.n_tasks == len(p.plan.tasks)
        assert p.depth == len(p.plan.levels())
        assert p.description.count("- ") >= 4


def test_description_mentions_the_entities_and_stack():
    p = generate_balanced(1, "train", 0)[0]
    assert "fastapi+react+postgres" in p.description
    for e in p.plan.tasks:
        if e.domain == "database" and e.target != "users":
            assert e.target in p.description
