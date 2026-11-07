from __future__ import annotations

from slm.bench.catalog import TRAIN_TEMPLATES, build_plan
from slm.bench.projects import generate_balanced, make_project
from slm.contracts import ProjectPlan, Task
from slm.llm.fake import FakeClient
from slm.manager.data import sft_rows
from slm.manager.manager import MANAGER_SYSTEM, format_example, plan, user_prompt
from slm.manager.score import deps_satisfied, score_json, score_plan, summarize


def test_prompt_names_all_four_specialists():
    for domain in ("database", "auth", "network", "frontend"):
        assert domain in MANAGER_SYSTEM


def test_minimal_hand_plan_is_valid():
    assert _minimal_plan(use_session=True).tasks


def test_user_prompt_carries_the_brief():
    assert "Build X" in user_prompt("Build X")


def test_plan_parses_the_manager_output():
    got = plan("build a notes app", FakeClient())
    assert isinstance(got, ProjectPlan)
    assert {t.domain for t in got.tasks} == {"database", "auth", "network", "frontend"}


def test_format_example_round_trips_the_gold_plan():
    p = generate_balanced(1, "train", 0)[0]
    system, user, completion = format_example(p)
    assert system == MANAGER_SYSTEM and p.description in user
    assert ProjectPlan.model_validate_json(completion) == p.plan


def test_sft_rows_skip_projects_without_plans():
    p = make_project(TRAIN_TEMPLATES[0], "train", 0, 0)
    no_plan = p.model_copy(update={"plan": None})
    rows = sft_rows([p, no_plan])
    assert len(rows) == 1 and set(rows[0]) == {"system", "prompt", "completion"}


def test_score_identical_plans_is_perfect():
    gold = build_plan(TRAIN_TEMPLATES[2])
    s = score_plan(gold, gold)
    assert s.valid and s.isomorphic and s.task_recall == 1.0 and s.task_precision == 1.0
    assert s.deps_satisfied and s.domain_coverage == 1.0


def test_score_detects_a_dropped_task_and_a_wrong_entity():
    gold = build_plan(TRAIN_TEMPLATES[0])
    tasks = [t.model_copy(deep=True) for t in gold.tasks]
    dropped = ProjectPlan(name=gold.name, tasks=[t for t in tasks if t.id != tasks[-1].id])
    s = score_plan(dropped, gold)
    assert s.valid and not s.isomorphic
    assert s.task_recall < 1.0 and s.task_precision == 1.0

    wrong = [t.model_copy(deep=True) for t in tasks]
    rest = next(t for t in wrong if t.kind == "rest")
    rest.target = "widgets"
    s2 = score_plan(ProjectPlan(name=gold.name, tasks=wrong), gold)
    assert 0 < s2.task_recall < 1.0


def _minimal_plan(use_session: bool) -> ProjectPlan:
    """Four domains, one table, one router, one page - enough to exercise interface wiring."""
    tasks = [
        Task(id="t1", domain="database", kind="schema", target="users", detail="users table"),
        Task(id="t2", domain="database", kind="schema", target="order", detail="orders table"),
        Task(id="t3", domain="auth", kind="session" if use_session else "oauth",
             target="session" if use_session else "oauth", detail="auth",
             deps=["t1"]),
        Task(id="t4", domain="network", kind="rest", target="order", detail="orders api",
             deps=["t2"] + (["t3"] if use_session else [])),
        Task(id="t5", domain="frontend", kind="page", target="order", detail="orders page",
             deps=["t4"]),
    ]
    return ProjectPlan(name="shop", tasks=tasks)


def test_deps_satisfied_flags_missing_prerequisites():
    ok = _minimal_plan(use_session=True)
    assert deps_satisfied(ok)  # guard:session exists, so the router's session dependency resolves
    broken = _minimal_plan(use_session=False)  # only OAuth: nothing provides guard:session
    assert not deps_satisfied(broken)


def test_score_json_rejects_malformed_text():
    gold = build_plan(TRAIN_TEMPLATES[0])
    s = score_json("not a plan", gold)
    assert not s.valid and s.task_recall == 0.0


def test_summarize_averages_every_metric():
    gold = build_plan(TRAIN_TEMPLATES[0])
    out = summarize([score_plan(gold, gold), score_plan(None, gold)])
    assert out["n"] == 2 and out["valid"] == 0.5 and out["isomorphic"] == 0.5
