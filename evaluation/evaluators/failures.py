"""One primary failure label per unresolved trial, each with the evidence behind it. If the record doesn't show the
cause, the answer is `unknown`. An agent's own account of what it did is never used."""

from __future__ import annotations

from collections import Counter

from evaluation.core import BUDGET_EXHAUSTED, CRASHED, ENVIRONMENT_FAILURE, UNSUPPORTED

EDITS = ("edit", "write_file", "edit_file", "Edit", "Write", "MultiEdit")
LOOP_REPEATS = 3


def trace_metrics(events: list[dict]) -> dict:
    """Agentic behaviour as observable actions."""
    calls = [e for e in events if e["type"] == "tool_call"]
    is_edit = lambda e: e.get("tool") in EDITS  # noqa: E731
    first_edit = next((i for i, e in enumerate(calls) if is_edit(e)), None)
    last_edit = max((i for i, e in enumerate(calls) if is_edit(e)), default=None)
    tests = [i for i, e in enumerate(calls) if e.get("is_test")]
    actions = Counter(str(e.get("signature") or (e.get("tool"), str(e.get("args"))[:200])) for e in calls)
    return {"tool_calls": len(calls), "reads_before_first_edit": first_edit if first_edit is not None else len(calls),
            "edits": sum(map(is_edit, calls)), "test_runs": len(tests),
            "tested_after_last_edit": bool(tests) and last_edit is not None and tests[-1] > last_edit,
            "most_repeated_action": max(actions.values(), default=0),
            "tool_errors": sum(e["type"] == "error" or (e["type"] == "tool_result" and e.get("ok") is False) for e in events)}


def classify(status: str, grade: dict | None, trace: dict | None, *, has_trajectory: bool = True) -> dict | None:
    """{"primary", "evidence"}, or None if the trial resolved."""
    if status == ENVIRONMENT_FAILURE:
        return {"primary": "environment_failure", "evidence": "the backend or harness failed"}
    if status == UNSUPPORTED:
        return {"primary": "unsupported", "evidence": "the agent can't attempt this kind of task"}
    if grade is None:
        return {"primary": "environment_failure", "evidence": "no grade was recorded"}
    if grade.get("resolved"):
        return None
    if status == BUDGET_EXHAUSTED:
        return {"primary": "budget_exhaustion", "evidence": "stopped by the step, time or cost limit"}
    if status == CRASHED:
        return {"primary": "tool_execution", "evidence": "the agent process exited with an error"}
    if grade.get("empty_patch") and "by_group" in grade:
        return {"primary": "unknown", "evidence": "submitted no files, and the record doesn't show why"}
    if not grade.get("patch_applied", True):
        return {"primary": "tool_execution", "evidence": f"patch didn't apply: {grade.get('apply_error')}"}
    if grade.get("empty_patch"):
        t = trace or {}
        if t.get("tool_errors"):
            return {"primary": "tool_execution", "evidence": f"no edits, {t['tool_errors']} tool errors"}
        return {"primary": "unknown", "evidence": "submitted no changes, and the record doesn't show why"}
    if not grade.get("build_success", True) and "by_group" not in grade:
        return {"primary": "coding", "evidence": "the submission doesn't compile"}
    if "by_group" in grade:  # the run check says which part failed; no tool trace exists for these agents
        names = [c["name"] for c in grade.get("failed_checks", [])][:5]
        return {"primary": "coding", "evidence": f"built but failed run checks: {', '.join(names)}"}
    t = trace or {}
    if not has_trajectory:
        return {"primary": "unknown", "evidence": "no trajectory recorded"}
    if t.get("most_repeated_action", 0) >= LOOP_REPEATS:
        return {"primary": "planning", "evidence": f"same action repeated {t['most_repeated_action']} times"}
    if grade.get("touched_target") is False:
        return {"primary": "repository_navigation", "evidence": "changed code, but none of it in the files that needed fixing"}
    if t.get("test_runs", 0) == 0:
        return {"primary": "verification", "evidence": "never ran a test, and the submission fails"}
    if not t.get("tested_after_last_edit"):
        return {"primary": "verification", "evidence": "didn't test after its last edit"}
    if grade.get("regression"):
        return {"primary": "repair", "evidence": f"finished with regressions: {grade['regressed'][:3]}"}
    return {"primary": "unknown", "evidence": f"tested and stopped, still failing {grade.get('fail_to_pass_failed', [])[:3]}"}
