from __future__ import annotations

import json

import pytest

from slm.bench.catalog import HELDOUT_TEMPLATES, TRAIN_TEMPLATES, build_plan, gold_artifacts
from slm.bench.variety import generate_varied
from slm.contracts import integrate, specialist_prompt
from slm.domains import DOMAINS
from slm.manager.spec import (
    ProjectSpec, SpecTest, format_spec_example, gold_spec, score_spec_json, summarize_specs, to_plan,
)

SEED = 20261101


def _plans():
    yield from (build_plan(t) for t in TRAIN_TEMPLATES + HELDOUT_TEMPLATES)
    for split, n in (("train", 200), ("dev", 40), ("test", 40)):
        yield from (p.plan for p in generate_varied(n, split, SEED))


def test_compiling_a_gold_spec_gives_back_the_exact_plan():
    for plan in _plans():
        assert to_plan(gold_spec(plan)) == plan


def test_specialist_prompts_are_unchanged_by_the_round_trip():
    """The specialists train on these prompts, so the nested path must not alter them by one byte."""
    for plan in _plans():
        back = to_plan(gold_spec(plan))
        assert [specialist_prompt(back, t) for t in back.tasks] == \
               [specialist_prompt(plan, t) for t in plan.tasks]


def test_a_compiled_gold_spec_still_integrates():
    for plan in _plans():
        back = to_plan(gold_spec(plan))
        d = integrate("p", back, gold_artifacts(back))
        assert d.ok, d.failures


def test_gold_specs_score_perfectly():
    scores = [score_spec_json(gold_spec(p).model_dump_json(), p) for p in _plans()]
    assert all(v == 1.0 for k, v in summarize_specs(scores).items() if k != "n")


def test_spec_has_four_levels_of_nesting_below_the_project():
    spec = gold_spec(generate_varied(1, "train", SEED)[0].plan)
    for d in DOMAINS:
        section = spec.domain(d)
        assert section.groups and section.integration_tests
        for g in section.groups:
            assert g.id.count(".") == 0
            for t in g.tasks:
                assert t.id.startswith(g.id + ".") and t.steps
                for s in t.steps:
                    assert s.id.startswith(t.id + ".") and s.test.scope == "unit"


def test_every_test_id_is_unique_and_every_deps_points_at_a_real_task():
    for plan in _plans():
        spec = gold_spec(plan)
        ids = [t.id for t in spec.system_tests]
        for d in DOMAINS:
            ids += [t.id for t in spec.domain(d).integration_tests]
        task_ids = {t.id for _, t in spec.tasks()}
        for _, t in spec.tasks():
            ids += [s.test.id for s in t.steps]
            assert set(t.deps) <= task_ids
        assert len(ids) == len(set(ids))


def test_oauth_system_test_appears_only_with_oauth():
    for plan in _plans():
        has_oauth = any(t.kind == "oauth" for t in plan.tasks)
        assert any("provider:oauth" in t.verifies for t in gold_spec(plan).system_tests) == has_oauth


def _mutate(plan, fn) -> str:
    data = json.loads(gold_spec(plan).model_dump_json())
    fn(data)
    return json.dumps(data)


def _plan():
    return build_plan(TRAIN_TEMPLATES[0])


def test_score_rejects_malformed_text():
    s = score_spec_json("not json", _plan())
    assert not s.parsed and not s.compiled and s.plan.task_recall == 0.0


def test_unknown_dep_parses_but_does_not_compile():
    def fn(d):
        d["network"]["groups"][0]["tasks"][0]["deps"] = ["NOPE-9.9"]

    s = score_spec_json(_mutate(_plan(), fn), _plan())
    assert s.parsed and not s.compiled


def test_invented_symbol_lowers_known_refs():
    def fn(d):
        d["system_tests"][0]["verifies"] = ["table:made_up"]

    s = score_spec_json(_mutate(_plan(), fn), _plan())
    assert s.compiled and s.known_refs < 1.0


def test_wrong_test_scope_lowers_tests_scoped():
    def fn(d):
        d["system_tests"][0]["scope"] = "unit"

    s = score_spec_json(_mutate(_plan(), fn), _plan())
    assert s.tests_scoped < 1.0


def test_a_step_without_coverage_lowers_symbol_coverage():
    def fn(d):
        d["network"]["groups"][0]["tasks"][0]["steps"].pop()

    s = score_spec_json(_mutate(_plan(), fn), _plan())
    assert s.compiled and s.symbol_coverage < 1.0


def test_dropping_a_task_lowers_recall_but_stays_scorable():
    def fn(d):
        d["frontend"]["groups"][-1]["tasks"] = d["frontend"]["groups"][-1]["tasks"] or []
        d["frontend"]["groups"].pop()

    s = score_spec_json(_mutate(_plan(), fn), _plan())
    assert s.compiled and s.plan.task_recall < 1.0 and not s.plan.isomorphic


def test_schema_rejects_empty_levels():
    data = json.loads(gold_spec(_plan()).model_dump_json())
    data["auth"]["groups"] = []
    with pytest.raises(ValueError):
        ProjectSpec.model_validate(data)
    with pytest.raises(ValueError):
        SpecTest(id="x", scope="unit", description="d", expected="e", verifies=[])


def test_generated_text_uses_the_right_article():
    for split, n in (("train", 300), ("dev", 100), ("test", 160)):
        for p in generate_varied(n, split, SEED):
            text = gold_spec(p.plan).model_dump_json()
            for vowel in "aeiou":
                assert f"create a {vowel}" not in text and f"Create a {vowel}" not in text


def test_training_row_round_trips():
    p = generate_varied(1, "train", SEED)[0]
    user, completion = format_spec_example(p.description, p.plan)
    assert p.description in user
    assert to_plan(ProjectSpec.model_validate_json(completion)) == p.plan


def test_nested_eval_logic_scores_and_reports_failures():
    from slm.manager.train_logic import (
        parse_spec_plan, score_spec_outputs, spec_json_schema, summarize_spec_records,
    )

    projects = generate_varied(2, "dev", SEED)
    good = gold_spec(projects[0].plan).model_dump_json()
    assert parse_spec_plan(good)[0] == projects[0].plan
    assert parse_spec_plan("nope")[0] is None and parse_spec_plan("nope")[1]
    summary = summarize_spec_records(score_spec_outputs(projects, [good, "nope"]))
    assert summary["overall"]["n"] == 2 and summary["overall"]["compiled"] == 0.5
    assert [f["project_id"] for f in summary["failures"]] == [projects[1].id]
    assert "database" in spec_json_schema()["properties"]


def test_singular_reverses_plural_and_leaves_lookalikes_alone():
    from slm.manager.spec import singular

    for plural_form, one in [("campers", "camper"), ("boxes", "box"), ("batches", "batch"), ("crew_members", "crew_member"),
                             ("bosses", "boss"), ("camper", "camper"), ("status", "status"), ("boss", "boss"), ("analysis", "analysis")]:
        assert singular(plural_form) == one


def test_normalizing_a_gold_spec_changes_nothing():
    from slm.manager.spec import normalize_spec, without_oauth

    for plan in _plans():
        spec = without_oauth(gold_spec(plan))
        assert normalize_spec(spec) == spec


def test_a_plural_spec_normalizes_to_the_gold_spec():
    """A plan the manager pluralized must come out identical to the correct one, tests included."""
    from slm.bench.catalog import Template_
    from slm.manager.spec import normalize_spec

    def spec_of(entities, form):
        return gold_spec(build_plan(Template_("x", "summer camp", "a summer camp", entities, form, False)))

    wrong, right = spec_of(("campers", "cabins"), "cabins"), spec_of(("camper", "cabin"), "cabin")
    assert normalize_spec(wrong) == right


def test_a_form_that_disagrees_with_the_client_follows_the_client():
    from slm.manager.spec import ProjectSpec, normalize_spec, without_oauth_plan

    right = without_oauth_plan(build_plan(TRAIN_TEMPLATES[0]))
    data = json.loads(gold_spec(right).model_dump_json())
    form = next(t for g in data["frontend"]["groups"] for t in g["tasks"] if t["kind"] == "form")
    other = next(t.target for t in right.tasks if t.kind == "page" and t.target != form["target"])
    form["target"] = other
    assert to_plan(normalize_spec(ProjectSpec.model_validate(data))) == right


def test_removing_oauth_keeps_everything_else_and_matches_the_plan_without_it():
    from slm.bench.catalog import gold_artifacts
    from slm.contracts import integrate
    from slm.manager.spec import normalize_spec, without_oauth, without_oauth_plan

    for plan in _plans():
        spec = without_oauth(gold_spec(plan))
        back = to_plan(spec)
        assert back == without_oauth_plan(plan)
        assert not any(t.kind == "oauth" for t in back.tasks)
        assert not any("provider:oauth" in t.verifies for t in spec.system_tests)
        assert to_plan(normalize_spec(gold_spec(plan))) == back
        assert integrate("p", back, gold_artifacts(back)).ok


def test_removing_oauth_keeps_the_managers_own_text():
    from slm.manager.spec import without_oauth

    plan = next(p for p in _plans() if any(t.kind == "oauth" for t in p.tasks))
    data = json.loads(gold_spec(plan).model_dump_json())
    data["architecture"] = "written by the manager"
    data["database"]["groups"][0]["heading"] = "manager heading"
    out = without_oauth(ProjectSpec.model_validate(data))
    assert out.architecture == "written by the manager" and out.database.groups[0].heading == "manager heading"
