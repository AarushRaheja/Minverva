import json

import pytest
from conftest import BUDGET

from evaluation.adapters.baseline_agent import ClaudeCodeAgent
from evaluation.analysis import comparisons as c
from evaluation.analysis import statistics as s
from evaluation.benchmarks import harbor_export
from evaluation.benchmarks.task_registry import repo_tasks
from evaluation.evaluators.failures import classify, trace_metrics
from evaluation.runner import orchestrator as o
from evaluation.runner.trajectory_logger import TrajectoryLogger, redact


def test_mcnemar_only_counts_disagreements_and_is_exact():
    r = s.mcnemar([True] * 5 + [False] * 5, [False] * 5 + [False] * 5)
    assert (r["a_only"], r["b_only"], r["neither"]) == (5, 0, 5) and r["p"] == pytest.approx(0.0625)
    assert s.mcnemar([True, False], [True, False])["p"] == 1.0
    with pytest.raises(ValueError):
        s.mcnemar([True], [])


def test_six_one_way_disagreements_are_the_minimum_for_significance():
    assert s.min_discordant_for_significance() == 6
    assert s.mcnemar([True] * 6, [False] * 6)["p"] < 0.05 < s.mcnemar([True] * 5, [False] * 5)["p"]


def test_bootstrap_keeps_a_tasks_repeats_together_and_handles_constants():
    a = {"t1": [1.0, 1.0, 1.0], "t2": [0.0, 0.0, 0.0], "t3": [1.0, 0.0, 1.0]}
    b = {"t1": [0.0], "t2": [0.0], "t3": [0.0]}
    r = s.paired_difference_ci(a, b, {"t1": "g", "t2": "g", "t3": "h"}, n_boot=500)
    assert r["n"] == 3 and r["clusters"] == 2
    assert r["lo"] <= r["diff"] <= r["hi"]
    same = s.paired_difference_ci({"t": [1.0]}, {"t": [1.0]}, {}, n_boot=50)
    assert same["diff"] == same["lo"] == same["hi"] == 0


def test_wilson_keeps_real_uncertainty_at_zero_successes():
    lo, hi = s.wilson(0, 3)
    assert lo == 0 and 0.5 < hi < 0.6
    assert s.wilson(10, 10)[1] == 1.0 and s.wilson(10, 10)[0] > 0.6


def test_pass_at_k_and_all_ignore_tasks_without_enough_attempts():
    tasks = {"a": [True, False, False], "b": [True, True, True], "c": [False, False, False], "d": [True]}
    assert s.pass_at_k(tasks, 3) == pytest.approx(2 / 3)
    assert s.success_all(tasks, 3) == pytest.approx(1 / 3)
    assert s.pass_at_k({"d": [True]}, 3) is None


def test_cost_per_resolved_counts_failed_attempts_and_never_invents_a_price():
    assert s.cost_per_resolved([1.0, 1.0, 2.0], [True, False, False]) == 4.0
    assert s.cost_per_resolved([1.0, None], [True, True]) is None
    assert s.cost_per_resolved([1.0], [False]) is None


def test_interaction_and_robustness():
    assert s.interaction(0.8, 0.4, 0.5, 0.2) == pytest.approx(0.1)
    assert s.robustness_delta([True, False], [True, True]) == -0.5
    assert s.robustness_delta([], [True]) is None


def test_pareto_excludes_dominated_and_unknown_cost():
    pts = [{"name": "a", "cost": 1, "resolve": 0.5}, {"name": "b", "cost": 2, "resolve": 0.9}, {"name": "c", "cost": 3, "resolve": 0.8}, {"name": "d", "cost": None, "resolve": 1.0}]
    assert s.pareto_frontier(pts) == ["a", "b"]


def test_tasks_needed_grows_as_the_effect_shrinks_and_rejects_impossible_inputs():
    assert s.paired_tasks_needed(0.2, 0.05) > s.paired_tasks_needed(0.2, 0.1) > 0
    assert s.paired_tasks_needed(0, 0.05) is None and s.paired_tasks_needed(0.02, 0.05) is None


def test_holm_is_stricter_than_unadjusted():
    assert s.holm({"a": 0.03, "b": 0.04}) == {"a": False, "b": False}  # each would pass alone at 0.05
    assert s.holm({"a": 0.01, "b": 0.04}) == {"a": True, "b": True}


def row(agent, task, resolved, **kw):
    return {"agent": agent, "task": task, "resolved": resolved, "score": float(resolved), "repeat": 0, "status": "completed", "family": "repo", "group": task,
            "task_class": "x", "wall_s": 10.0, "cost_usd": 1.0, "cost_basis": "reported", "metrics": {}, "trace": {}, "grade": {"regression": False}, "failure": None,
            "provenance": "harness", "budget": "low", "control_of": None, **kw}


def test_censored_trials_never_count_as_failures_or_pairs():
    rows = [row("a", "t1", True), row("a", "t2", False, status="unsupported", grade=None), row("b", "t1", False), row("b", "t2", True)]
    x = next(x for x in c.agent_summary(rows) if x["agent"] == "a")
    assert x["attempted"] == 1 and x["resolved_at_1"] == 1.0 and x["censored"]["unsupported"] == 1
    assert c.paired(rows, "a", "b")["n"] == 1


def test_paired_refuses_a_verdict_it_cannot_support():
    rows = [row("a", f"t{i}", True) for i in range(3)] + [row("b", f"t{i}", False) for i in range(3)]
    assert "too few tasks" in c.paired(rows, "a", "b")["verdict"]
    rows = [row("a", f"t{i}", True) for i in range(8)] + [row("b", f"t{i}", False) for i in range(8)]
    assert c.paired(rows, "a", "b")["verdict"] == "a is ahead"


def test_factorial_reports_a_missing_cell_instead_of_an_estimate():
    rows = [row("x", "t", True), row("y", "t", False)]
    f = c.factorial(rows, {"00": "y", "11": "x"})
    assert f["interaction"] is None and set(f["missing"]) == {"01", "10"}


def test_controls_gate_the_report():
    good = [row("null", "t", False), row("oracle", "t", True)]
    assert c.controls_status(good)["valid"]
    assert not c.controls_status([row("null", "t", True), row("oracle", "t", True)])["valid"]
    assert not c.controls_status([])["valid"]


def test_evidence_level_stays_zero_until_a_task_is_resolved():
    rows = [row("me", f"t{i}", False) for i in range(5)]
    assert c.evidence_level(c.agent_summary(rows), "me", [])["level"] == 0
    assert c.evidence_level(c.agent_summary([row("me", "t", True)]), "me", [])["level"] == 1


def test_robustness_pairs_perturbed_with_its_control():
    rows = [row("a", "ctl", True), row("a", "noisy", False, control_of="ctl")]
    assert c.robustness(rows)[0]["delta"] == -1.0


def test_guard_blocks_big_costly_and_heldout_runs():
    exp = {"experiment": {"split": "dev"}}
    with pytest.raises(o.NotAllowed):
        o.guard(exp, {"trials": 4500, "worst_case_usd": 0, "worst_case_hours": 1}, yes=False, final=False)
    with pytest.raises(o.NotAllowed):
        o.guard(exp, {"trials": 3, "worst_case_usd": 500, "worst_case_hours": 1}, yes=False, final=False)
    o.guard(exp, {"trials": 4500, "worst_case_usd": 500, "worst_case_hours": 1}, yes=True, final=False)
    with pytest.raises(o.NotAllowed):
        o.guard({"experiment": {"split": "test"}}, {"trials": 1, "worst_case_usd": 0, "worst_case_hours": 0}, yes=True, final=False)


def test_final_heldout_experiment_needs_final(monkeypatch):
    with pytest.raises(o.NotAllowed, match="--final"):
        o.run_experiment("final-heldout", yes=True, say=lambda _: None)


def test_a_changed_task_is_refused_until_reviewed_again():
    spec = repo_tasks()[0]
    spec.reviewed_revision = "old"
    assert o.stale_tasks([{"task": spec}]) == [spec.id]


def test_retry_replaces_an_environment_failure_and_keeps_one_record(tmp_path):
    p = tmp_path / "t.jsonl"
    p.write_text(json.dumps({"key": "k", "status": "environment_failure"}) + "\n" + json.dumps({"key": "k", "status": "completed"}) + "\n")
    assert [r["status"] for r in o.load_trials(p)] == ["completed"]


def test_local_cost_is_amortized_and_unknown_is_not_zero():
    assert o.amortized_usd({"cost": {"amortized_usd_per_hour": 0.12}}, 3600, None) == pytest.approx(0.12)
    assert o.amortized_usd({}, 3600, None) is None
    assert o.amortized_usd({}, 3600, 2.5) == 2.5


def test_failure_labels_need_evidence():
    assert classify("completed", {"resolved": True}, {}) is None
    g = {"resolved": False, "patch_applied": True, "build_success": True, "fail_to_pass_failed": ["x"], "regression": False, "empty_patch": False}
    assert classify("completed", g, {"test_runs": 0})["primary"] == "verification"
    assert classify("completed", g, {"test_runs": 2, "tested_after_last_edit": True})["primary"] == "unknown"
    assert classify("completed", {**g, "touched_target": False}, {"test_runs": 2})["primary"] == "repository_navigation"
    assert classify("completed", g, {"most_repeated_action": 4, "test_runs": 1})["primary"] == "planning"
    assert classify("completed", g, {}, has_trajectory=False)["primary"] == "unknown"
    assert classify("crashed", g, {})["primary"] == "tool_execution"


def test_trace_metrics_read_actions_not_claims():
    ev = [{"type": "model", "text": "I ran all the tests and they pass"}, {"type": "tool_call", "tool": "read_file", "signature": "r"}, {"type": "tool_call", "tool": "edit_file", "signature": "e"}]
    t = trace_metrics(ev)
    assert t["test_runs"] == 0 and t["reads_before_first_edit"] == 1 and not t["tested_after_last_edit"]


def test_secrets_are_redacted_in_trajectories(tmp_path):
    secret = "sk-" + "a" * 30
    assert secret not in redact(f"token {secret}")
    assert "hunter2hunter2" not in redact("password=hunter2hunter2")
    log = TrajectoryLogger(tmp_path / "t.jsonl")
    log.log("message", text=secret, nested={"k": [secret]})
    assert secret not in (tmp_path / "t.jsonl").read_text()


def stream(agent, m, *events, budget=BUDGET, tmp=None):
    log = TrajectoryLogger(tmp / "l.jsonl")
    return [agent.handle_line(json.dumps(e), log, m, budget) for e in events], log


def fresh():
    return {"steps": 0, "model_calls": 0, "tool_calls": 0, "tok_in": 0, "tok_out": 0, "tool_errors": 0, "cost_usd": None}


def test_claude_stream_records_usage_and_tests(tmp_path):
    a, m = ClaudeCodeAgent({"model_id": "m"}), fresh()
    stream(a, m,
           {"type": "assistant", "message": {"content": [{"type": "tool_use", "name": "Bash", "input": {"command": "python3 -m unittest discover"}}]}},
           {"type": "user", "message": {"content": [{"type": "tool_result", "is_error": True, "content": "x"}]}},
           {"type": "result", "subtype": "success", "total_cost_usd": 0.5, "usage": {"input_tokens": 3, "cache_read_input_tokens": 4, "output_tokens": 2}, "modelUsage": {"m-1": {}}}, tmp=tmp_path)
    assert (m["tool_calls"], m["tool_errors"], m["tok_in"], m["tok_out"], m["cost_usd"]) == (1, 1, 7, 2, 0.5)
    assert "api_error" not in m
    assert '"is_test": true' in (tmp_path / "l.jsonl").read_text()


def test_claude_stream_stops_past_the_step_budget(tmp_path):
    a, m = ClaudeCodeAgent({"model_id": "m"}), fresh()
    call = {"type": "assistant", "message": {"content": [{"type": "tool_use", "name": "Read", "input": {}}]}}
    results, _ = stream(a, m, *[call] * (BUDGET.max_steps + 1), tmp=tmp_path)
    assert results[-1] is False and all(results[:-1])


def test_claude_stream_sorts_service_errors_from_budget_stops(tmp_path):
    a, m = ClaudeCodeAgent({"model_id": "m"}), fresh()
    stream(a, m, {"type": "result", "subtype": "success", "is_error": True, "result": "401 auth"}, tmp=tmp_path)
    assert m["api_error"] == "401 auth"
    m = fresh()
    stream(a, m, {"type": "result", "subtype": "error_max_budget_usd", "is_error": True}, tmp=tmp_path)
    assert m["budget_hit"] and "api_error" not in m


def test_harbor_export_keeps_hidden_tests_out_of_the_image(tmp_path):
    spec = repo_tasks()[0]
    d = harbor_export.export_task(spec, tmp_path)
    assert not list((d / "environment").rglob("test_private*"))
    assert list((d / "tests/private").glob("test_private*"))
    assert not list((d / "environment").rglob("solution"))
    assert set(json.loads((d / "tests/expected.json").read_text())) == {*spec.fail_to_pass, *spec.pass_to_pass}
