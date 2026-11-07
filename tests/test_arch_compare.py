"""Picking the best architecture, the baseline clients, and head-to-head Elo. No model or CLI is ever run."""

from __future__ import annotations

import asyncio
import json
import subprocess
from types import SimpleNamespace

import pytest

from slm.arch.__main__ import compare_report, projects, select_best
from slm.arch.runner import run_arm
from slm.baselines.monolith import MonolithProject
from slm.bench import elo as E
from slm.contracts import Artifact
from slm.llm.cli import BackendUnavailable, ClaudeCLIClient, CodexCLIClient
from slm.trace import Tracer

DOMS = ("database", "auth", "network", "frontend")
DEV, DEV2, TEST = "proj-dev-a-0", "proj-dev-b-1", "proj-test-c-0"


def row(arm, project, rate):
    return {"arm": arm, "project_id": project, "template_id": project, "gold_pass": rate == 1.0,
            "gold_task_rate": rate, "own_pass": rate == 1.0, "plan_recall": None, "plan_valid": None,
            "wall_s": 10.0, "calls": 1, "tok_in": 1, "tok_out": 1, "crit_tok_out": 1, "crit_s": 1.0, "error": None,
            "by_domain": dict.fromkeys(DOMS, rate)}


def test_head_to_head_counts_and_sign():
    res = {"a": {"i": 1.0, "j": 1.0, "k": 0.5}, "b": {"i": 0.0, "j": 1.0, "k": 1.0}}
    h = E.head_to_head(res, "a", "b")
    assert (h["wins"], h["draws"], h["losses"], h["n"]) == (1, 1, 1, 3)
    assert h["diff"] == pytest.approx(0) and h["lo"] <= 0 <= h["hi"]
    assert E.head_to_head({"a": {"i": 1.0}, "b": {"i": 0.0}}, "b", "a")["diff"] < 0


def test_head_to_head_ci_resamples_clusters():
    res = {"a": {f"p{p}/{d}": 1.0 for p in range(5) for d in DOMS}, "b": {f"p{p}/{d}": 0.0 for p in range(5) for d in DOMS}}
    cl = {f"p{p}/{d}": f"p{p}" for p in range(5) for d in DOMS}
    h = E.head_to_head(res, "a", "b", cl)
    assert h["n_clusters"] == 5 and h["lo"] > 0  # a sweep of every project is separated


def test_selection_uses_dev_only_and_never_the_oracle_or_baselines():
    rows = [row("mgr-G1", DEV, 0.9), row("mgr-G4", DEV, 0.8), row("gold-G4", DEV, 1.0), row("base-opus", DEV, 1.0),
            row("mgr-G4", TEST, 1.0), row("mgr-G1", TEST, 0.0)]
    best, chosen_on = select_best(rows)
    assert best == "mgr-G1"
    assert {r["arm"] for r in chosen_on} == {"mgr-G1", "mgr-G4"} and {r["project_id"] for r in chosen_on} == {DEV}


def test_a_lagging_arm_does_not_shrink_the_selection():
    rows = [row("mgr-G1", DEV, 0.9), row("mgr-G1", DEV2, 0.9), row("mgr-G4", DEV, 0.8), row("mgr-G4", DEV2, 0.8),
            row("mgr-G2", DEV, 1.0)]  # G2 has one project so far: it can't win on it or cut the pairing to one
    best, chosen_on = select_best(rows)
    assert best == "mgr-G1" and {r["project_id"] for r in chosen_on} == {DEV, DEV2}


def test_report_pairs_best_with_baseline_per_split():
    rows = [row("mgr-G4", p, 0.5) for p in (DEV, TEST)] + [row("mono", DEV, 0.1)]
    rows += [row("base-opus", p, 1.0) for p in (DEV, TEST)]
    text, data = compare_report(rows)
    assert data["best"] == "mgr-G4" and "`mgr-G4` vs hosted baselines" in text
    by_split = {h["split"]: h for h in data["vs_baselines"]}
    assert set(by_split) == {"test", "dev"}
    assert by_split["test"]["losses"] == 4 and by_split["test"]["diff"] < 0  # negative: the baseline is ahead


def test_report_says_so_when_there_are_no_baselines():
    text, data = compare_report([row("mgr-G4", DEV, 0.5), row("mono", DEV, 0.1)])
    assert "No baseline results yet" in text and data["vs_baselines"] == []


def _proc(stdout="", returncode=0, stderr=""):
    return SimpleNamespace(stdout=stdout, stderr=stderr, returncode=returncode)


def _envelope(result, **kw):
    return json.dumps({"subtype": "success", "is_error": False, "result": result,
                       "usage": {"input_tokens": 3, "cache_read_input_tokens": 4, "output_tokens": 5},
                       "modelUsage": {"claude-opus-5-5": {}}, **kw})


def test_claude_cli_has_no_tools_or_repo_and_returns_usage(monkeypatch, tmp_path):
    seen = {}

    def fake(argv, **kw):
        seen.update(argv=argv, **kw)
        return _proc(_envelope('{"files": [], "summary": ""}'))

    monkeypatch.setenv("CLAUDECODE", "1")
    c = ClaudeCLIClient(run=fake)
    assert c.complete("sys", "the brief", Artifact).files == []
    argv = seen["argv"]
    assert argv[argv.index("--tools") + 1] == "" and argv[argv.index("--model") + 1] == "claude-opus-5-5"
    assert "sys" in argv[argv.index("--system-prompt") + 1] and "JSON Schema" in argv[argv.index("--system-prompt") + 1]
    assert seen["input"] == "the brief" and "slm-baseline-" in seen["cwd"] and "CLAUDECODE" not in seen["env"]
    assert c._raw("s", "u", {}).input_tokens == 7


@pytest.mark.parametrize("proc", [
    _proc(returncode=1, stderr="not logged in"),
    _proc("not json"),
    _proc(_envelope("rate limited", is_error=True)),
    _proc(_envelope("{}", modelUsage={"claude-haiku-5-5": {}})),  # a silent fallback is not an Opus result
])
def test_claude_cli_service_failures_are_not_model_failures(proc):
    with pytest.raises(BackendUnavailable):
        ClaudeCLIClient(run=lambda *a, **k: proc)._raw("s", "u", {})


def test_cli_timeout_is_a_service_failure():
    def slow(argv, **kw):
        raise subprocess.TimeoutExpired(argv, 1)

    with pytest.raises(BackendUnavailable):
        ClaudeCLIClient(run=slow)._raw("s", "u", {})


def test_codex_prompt_carries_the_system_text_and_reads_the_last_message():
    seen = {}

    def fake(argv, **kw):
        seen.update(argv=argv, **kw)
        open(argv[argv.index("--output-last-message") + 1], "w").write('{"files": [], "summary": "x"}')
        return _proc()

    c = CodexCLIClient(None, run=fake)
    assert c.complete("sys", "the brief", MonolithProject).summary == "x"
    assert "--model" not in seen["argv"] and seen["argv"][-1] == "-"
    assert seen["input"].startswith("sys") and seen["input"].endswith("the brief")


def test_codex_without_a_message_is_a_service_failure():
    with pytest.raises(BackendUnavailable):
        CodexCLIClient(None, run=lambda *a, **k: _proc())._raw("s", "u", {})


@pytest.mark.parametrize("arm", ["base-opus", "mono"])
def test_service_failure_leaves_no_result_but_bad_output_counts_as_a_loss(arm, tmp_path):
    p = projects(1)[0]
    down = ClaudeCLIClient(run=lambda *a, **k: _proc(returncode=1, stderr="429"))
    with pytest.raises(BackendUnavailable):
        asyncio.run(run_arm(arm, p, down, Tracer(run_id="d", trace_dir=tmp_path)))
    garbage = ClaudeCLIClient(run=lambda *a, **k: _proc(_envelope("I can't do that")))
    res = asyncio.run(run_arm(arm, p, garbage, Tracer(run_id="g", trace_dir=tmp_path)))[-1]
    assert res.gold_task_rate == 0.0 and not res.gold_pass and res.error


def test_verdict_refuses_to_call_a_winner_on_too_few_projects():
    from slm.arch.__main__ import _h2h_line

    base = {"a": "x", "b": "y", "wins": 3, "draws": 0, "losses": 0, "diff": 82.0, "lo": 82.0, "hi": 82.0}
    assert "too few projects" in _h2h_line("dev", {**base, "n_clusters": 3})
    assert "x is ahead" in _h2h_line("dev", {**base, "n_clusters": 5})
    assert "no clear winner" in _h2h_line("dev", {**base, "n_clusters": 5, "lo": -1.0})


def test_grade_tree_passes_gold_files_and_ignores_links_and_contract(tmp_path):
    from slm.arch.__main__ import grade_tree
    from slm.bench.catalog import gold_artifacts

    p = projects(1)[0]
    for art in gold_artifacts(p.plan).values():
        for f in art.files:
            target = tmp_path / f.path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(f.content)
    (tmp_path / "CONTRACT.md").write_text("notes")
    res = grade_tree(p, "opus-multiagent", tmp_path, calls=8)
    assert res.gold_pass and res.gold_task_rate == 1.0 and res.calls == 8
    first = next(tmp_path.rglob("*.sql"))
    outside = tmp_path.parent / "outside.sql"
    outside.write_text(first.read_text())
    first.unlink()
    first.symlink_to(outside)
    assert not grade_tree(p, "opus-multiagent", tmp_path).gold_pass  # a symlinked file doesn't count


def test_an_imported_arm_shows_up_in_the_baseline_comparison():
    rows = [row("mgr-G4", p, 0.5) for p in (DEV, TEST)] + [row("opus-multiagent", p, 1.0) for p in (DEV, TEST)]
    text, data = compare_report(rows)
    assert "opus-multiagent" in text and {h["b"] for h in data["vs_baselines"]} == {"opus-multiagent"}
