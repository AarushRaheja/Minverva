"""Architecture harness, offline: a perfect client passes every arm; a broken one fails every arm."""

from __future__ import annotations

import asyncio
import json

import pytest

from slm.arch import runner, teams
from slm.arch.teams import agent_for
from slm.arch.__main__ import projects, summarize, table
from slm.arch.runner import (
    ARMS, BASELINES, COMBO_ARMS, RECURRENT_ARMS, BatchFiles, SlimClient, slim_prompt, Result, batch_prompt, critical_path, gold_grade, make_plan, remember, render_memory,
    run_arm,
)
from slm.baselines.monolith import MonolithProject
from slm.bench.catalog import gold_artifact, gold_artifacts
from slm.contracts import Artifact, ProjectPlan, provide_token, specialist_prompt, specialist_system, use_token
from slm.domains import canonical_path
from slm.llm.base import LLMClient, RawResponse
from slm.llm.cli import BackendUnavailable
from slm.pipeline.oracle import CALL
from slm.specialists import system_prompt
from slm.trace import Tracer

P = projects(1)[0]


@pytest.fixture(autouse=True)
def fake_run_check(monkeypatch):
    """Passes when every task meets its contract, so these tests need neither the toolchain nor real execution."""
    def check(files, plan):
        by_path = {f.path: f for f in files}
        missing = [canonical_path(t.domain, t.kind, t.target) for t in plan.tasks
                   if canonical_path(t.domain, t.kind, t.target) not in by_path]
        checks = [{"group": "parse", "name": f"python:{m}", "ok": False, "detail": "missing"} for m in missing]
        return {"checks": checks, "by_group": {}, "rate": 1 - len(missing) / len(plan.tasks), "passed": not missing}

    monkeypatch.setattr(runner, "run_check", check)




class Perfect(LLMClient):
    """Answers like an ideal model: gold plan, gold artifacts, gold files for batch/monolith calls."""

    def __init__(self, project, tracer=None):
        super().__init__("perfect", tracer)
        self.project, self.systems = project, []

    def _raw(self, system, user, json_schema):
        self.systems.append(system)
        title = json_schema.get("title")
        if title == "Encoding":
            return RawResponse('{"context": "shared names"}', 10, 10)
        if title == "ProjectPlan":
            return RawResponse(self.project.plan.model_dump_json(), 10, 10)
        if title == "Artifact":
            plan, task = CALL.get()
            return RawResponse(gold_artifact(plan, task).model_dump_json(), 10, 10)
        files = [f for a in gold_artifacts(self.project.plan).values() for f in a.files]
        model = BatchFiles if title == "BatchFiles" else MonolithProject
        return RawResponse(model(files=files).model_dump_json(), 10, 10)


class Broken(Perfect):
    def _raw(self, system, user, json_schema):
        if json_schema.get("title") == "ProjectPlan":
            return super()._raw(system, user, json_schema)
        return RawResponse(json.dumps({"files": [{"path": "README.md", "content": "todo"}]}), 1, 1)


def run(arm, client, tmp_path):
    ps = asyncio.run(make_plan(P, client, Tracer(run_id="plan", trace_dir=tmp_path)))
    plan_events = [e for e in Tracer(run_id="plan", trace_dir=tmp_path).events() if e.kind == "llm"]
    return asyncio.run(run_arm(arm, P, client, Tracer(run_id=arm, trace_dir=tmp_path), ps, plan_events))


@pytest.mark.parametrize("arm", ARMS)
def test_perfect_client_passes_every_arm(arm, tmp_path):
    results = run(arm, Perfect(P), tmp_path)
    assert [r.arm for r in results] == (["mgr-G4", "mgr-G4-repair"] if arm == "mgr-G4-repair" else [arm])
    res = results[-1]
    assert res.error is None
    assert res.gold_pass and res.gold_task_rate == 1.0 and res.own_pass
    assert res.calls >= 1 and res.wall_s >= 0 and res.crit_tok_out > 0
    n = len(P.plan.tasks)
    if arm == "mono" or arm in BASELINES:
        assert res.calls == 1 and res.crit_tok_out == res.tok_out
    elif arm == "mgr-G4-batch":
        assert res.calls < 1 + n  # fewer calls than one per task
    elif arm in ("mgr-G4-shell", "mgr-G4-contract", "mgr-G4-context"):
        assert res.calls == n  # the manager, plus every task except the shell, which code writes
    elif arm == "gold-G4":
        assert res.calls == n and res.plan_recall == 1.0
    elif arm in COMBO_ARMS:
        assert res.calls == n + 1 and res.crit_tok_out == 10 * (1 + n)  # a perfect run has nothing to repair
    elif arm == "mgr-Nto1":
        assert res.calls == 2 and res.crit_tok_out == 20  # the plan, then one call for everything
    elif arm == "mgr-seq2seq":
        assert res.calls == n + 2 and res.crit_tok_out == 10 * (2 + n)  # plan, encoder, then every step in turn
    elif arm in RECURRENT_ARMS:
        assert res.calls == n + 1 and res.crit_tok_out == 10 * (1 + n)  # every step waits for the last
    else:
        assert res.plan_recall == 1.0 and res.calls == n + 1  # the shared plan call is counted
        assert res.crit_tok_out == 10 * (1 + len(P.plan.levels()))  # plan + slowest call per level


@pytest.mark.parametrize("arm", ["mono", "mgr-G4", "mgr-G4-batch", "mgr-G4-repair"])
def test_broken_client_fails_and_repair_retries(arm, tmp_path):
    results = run(arm, Broken(P), tmp_path)
    res = results[-1]
    assert not res.gold_pass and res.gold_task_rate == 0.0
    if arm == "mgr-G4-repair":
        before, after = results
        n = len(P.plan.tasks)
        assert before.calls == 1 + n and after.calls == 1 + 2 * n  # plan + first try + one repair each
        assert after.crit_tok_out > before.crit_tok_out  # the repair round is one more level


def test_manager_arm_requires_the_shared_plan(tmp_path):
    with pytest.raises(ValueError, match="PlanStats"):
        asyncio.run(run_arm("mgr-G4", P, Perfect(P), Tracer(run_id="x", trace_dir=tmp_path)))


def test_critical_path_takes_the_slowest_call_per_level():
    from slm.trace import TraceEvent

    def ev(level, task, tok, ms):
        return TraceEvent(run_id="r", ts=0, kind="llm", caller="c", callee="x", dep_level=level, task_id=task,
                          output_tokens=tok, latency_ms=ms)

    evs = [ev(-1, None, 50, 5000), ev(0, "a", 10, 1000), ev(0, "b", 30, 3000), ev(1, "c", 20, 2000),
           ev(1, "c", 5, 500)]  # c retried once: its two attempts add up
    assert critical_path(evs) == (50 + 30 + 25, 5 + 3 + 2.5)


def test_dropping_tasks_cannot_pass(tmp_path):
    """An arm graded on the gold plan fails if its files miss a gold task, whatever its own plan says."""
    files = [f for a in gold_artifacts(P.plan).values() for f in a.files][1:]
    res = Result(arm="x", project_id=P.id, template_id=P.template_id)
    gold_grade(P, files, res)
    assert not res.gold_pass and 0 < res.gold_task_rate < 1


@pytest.mark.parametrize("team", teams.TEAMS)
def test_team_prompts_route_every_task(team):
    seen = set()
    for t in P.plan.tasks:
        a = teams.agent_for(team, t)
        assert a in teams.agents(team)
        seen.add(a)
        p = teams.system_for(team, a)
        assert f"[{t.domain}/{t.kind}]" in p or f"[{t.kind}]" in p
        assert '{"files"' in p
    if team == "G4":
        assert all(teams.system_for("G4", d) == specialist_system(d) for d in seen)
    assert len(teams.agents(team)) == {"G1": 1, "G2": 2, "G4": 4, "G9": 9}[team]


def test_g9_prompt_is_scoped_to_one_kind():
    p = teams.system_for("G9", "network-client")
    assert "[network/client]" in p and "[network/rest]" not in p and "Teammates own" in p


def test_batch_prompt_lists_each_task_once():
    level0 = [P.plan.task(i) for i in P.plan.levels()[0]]
    text = batch_prompt(P.plan, level0)
    for t in level0:
        assert text.count(f"Your task {t.id} ") == 1
    assert text.count("The whole team provides") == 1


def test_summary_table(tmp_path):
    rows = []
    for arm in ("mgr-G4", "mono"):
        for p in projects(1)[:3]:
            r = Result(arm=arm, project_id=p.id, template_id=p.template_id, gold_pass=arm == "mgr-G4",
                       gold_task_rate=1.0 if arm == "mgr-G4" else 0.5, wall_s=10 if arm == "mgr-G4" else 5,
                       plan_recall=1.0 if arm == "mgr-G4" else None)
            rows.append(r.as_dict())
    s = summarize(rows)
    mono = next(r for r in s if r["arm"] == "mono")
    assert mono["d_task_vs_ref"][0] == pytest.approx(-0.5) and mono["d_wall_vs_ref"] == pytest.approx(0.5)
    assert "| mono | 3 |" in table(s)


def test_ollama_payload_is_greedy_and_schema_constrained():
    import httpx

    from slm.llm.ollama import OllamaClient

    seen = {}

    def handler(req):
        seen.update(json.loads(req.content))
        return httpx.Response(200, json={"message": {"content": '{"files": [], "summary": ""}'},
                                         "prompt_eval_count": 7, "eval_count": 3})

    c = OllamaClient("m", transport=httpx.MockTransport(handler))
    out = c.complete("s", "u", Artifact)
    assert out.files == [] and seen["think"] is False and seen["options"]["temperature"] == 0
    assert seen["format"]["title"] == "Artifact"
    assert ProjectPlan  # imported for the schema title check above


class Recording(Perfect):
    def __init__(self, project, tracer=None):
        super().__init__(project, tracer)
        self.users = []

    def _raw(self, system, user, json_schema):
        self.users.append(user)
        return super()._raw(system, user, json_schema)


def test_rnn_each_step_sees_the_memory_of_earlier_steps(tmp_path):
    client = Recording(P)
    res = run("mgr-rnn", client, tmp_path)[-1]
    assert res.gold_task_rate == 1.0
    steps = client.users[1:]  # the first call is the manager's plan
    assert "Already built by earlier steps" not in steps[0]
    assert all("Already built by earlier steps" in u for u in steps[1:])
    first_path = next(iter(gold_artifact(P.plan, P.plan.task(P.plan.levels()[0][0])).files)).path
    assert first_path in steps[1]


def test_rnn_memory_stays_bounded_and_forgets_the_oldest_first():
    entries = [f"t{i}" + "x" * 95 for i in range(50)]
    text = render_memory(entries, budget=300)
    assert len(text) < 400 and "t49" in text and "t0x" not in text
    assert text.index("t47") < text.index("t49")  # oldest first among what's kept
    assert render_memory([]) == "" and render_memory(["y" * 500], budget=10) == ""


def test_rnn_memory_keeps_interfaces_not_bodies():
    task = P.plan.tasks[0]
    art = Artifact(files=[{"path": "a.py", "content": "import os\n@router.get(\"/x\")\ndef x():\n    secret_body = 1\n"}])
    text = remember(task, art)
    assert '@router.get("/x")' in text and "def x():" in text and "secret_body" not in text and "import os" not in text


def test_rnn_a_failed_step_is_remembered_and_the_run_continues(tmp_path):
    class FailsOnce(Recording):
        def _raw(self, system, user, json_schema):
            if json_schema.get("title") == "Artifact" and len(self.users) <= 2:
                self.users.append(user)
                return RawResponse("not json", 1, 1)
            return super()._raw(system, user, json_schema)

    client = FailsOnce(P)
    res = run("mgr-rnn", client, tmp_path)[-1]
    assert res.error is None and 0 < res.gold_task_rate < 1
    assert any("FAILED, no output" in u for u in client.users)


def _gates(arm):
    """A recurrent client with every task of the plan already in memory except the last."""
    client = RECURRENT_ARMS[arm](Perfect(P), "G4")
    for t in P.plan.tasks[:-1]:
        client.memory.append((t, f"memory of {t.id}"))
    return client, P.plan.tasks[-1]


def test_lstm_reads_its_dependencies_and_the_latest_step_only():
    client, task = _gates("mgr-lstm")
    needed = set(P.plan.requires(task))
    deps = {t.id for t in P.plan.tasks[:-1] if needed & set(t.provides())}
    latest = P.plan.tasks[-2].id
    assert deps and {x.split()[-1] for x in client.recall(P.plan, task)} == deps | {latest}
    assert len(client.recall(P.plan, task)) < len(P.plan.tasks) - 1  # it is gated, unlike the RNN


def test_lstm_keeps_dependencies_when_the_budget_is_tight():
    client, task = _gates("mgr-lstm")
    entries = client.recall(P.plan, task)
    text = render_memory(entries, budget=len(entries[-1]))
    assert entries[-1] in text


def test_gru_drops_only_what_no_remaining_task_needs():
    client, task = _gates("mgr-gru")
    needed = set(P.plan.requires(task))
    want = {t.id for t in P.plan.tasks[:-1] if needed & set(t.provides())}
    assert {x.split()[-1] for x in client.recall(P.plan, task)} == want


def test_rnn_reads_everything():
    client, task = _gates("mgr-rnn")
    assert len(client.recall(P.plan, task)) == len(P.plan.tasks) - 1


def test_one_to_many_gets_only_the_brief_and_path_not_the_task_interfaces(tmp_path):
    client = Recording(P)
    assert run("mgr-1toN", client, tmp_path)[-1].gold_task_rate == 1.0
    steps = client.users[1:]
    assert all(P.description in u and "Write the file at exactly" in u for u in steps)
    assert not any("Interfaces you must" in u for u in steps)
    assert "Already built by earlier steps" in steps[1]


def test_many_to_one_makes_one_call_listing_every_task(tmp_path):
    client = Recording(P)
    assert run("mgr-Nto1", client, tmp_path)[-1].gold_pass
    assert len(client.users) == 2 and all(f"Your task {t.id} " in client.users[1] for t in P.plan.tasks)


def test_seq2seq_decoder_starts_from_the_encoder_context(tmp_path):
    client = Recording(P)
    assert run("mgr-seq2seq", client, tmp_path)[-1].gold_pass
    encoder, *steps = client.users[1:]
    assert "Tasks:" in encoder
    assert all(u.startswith("Shared context from the design lead:\nshared names") for u in steps)


def test_bad_encoder_output_does_not_stop_the_decoder(tmp_path):
    class BadEncoder(Recording):
        def _raw(self, system, user, json_schema):
            if json_schema.get("title") == "Encoding":
                return RawResponse("nope", 1, 1)
            return super()._raw(system, user, json_schema)

    client = BadEncoder(P)
    assert run("mgr-seq2seq", client, tmp_path)[-1].gold_pass
    assert not any("Shared context" in u for u in client.users)


class ServerDown(Perfect):
    def _raw(self, system, user, json_schema):
        if json_schema.get("title") == "ProjectPlan":
            return super()._raw(system, user, json_schema)
        raise BackendUnavailable("server stopped")


@pytest.mark.parametrize("arm", ["mgr-G4", "mgr-G1", "mgr-G4-batch", "mgr-G4-repair", "mgr-rnn", "mgr-lstm", "mgr-1toN",
                                 "mgr-Nto1", "mgr-seq2seq", "mgr-combo-s0", "mgr-combo-s3", "gold-G4", "mono"])
def test_a_server_failure_records_no_result_on_any_arm(arm, tmp_path):
    with pytest.raises(BackendUnavailable):
        run(arm, ServerDown(P), tmp_path)


def test_ollama_flags_a_server_that_ignores_the_schema():
    import httpx

    from slm.llm.ollama import OllamaClient

    def reply(content, done):
        return lambda req: httpx.Response(200, json={"message": {"content": content}, "done_reason": done})

    bad = OllamaClient("m", transport=httpx.MockTransport(reply('{"files":[{"path":"a","content"-- x', "stop")))
    with pytest.raises(BackendUnavailable, match="not enforcing"):
        bad._raw("s", "u", {})
    cut_off = OllamaClient("m", transport=httpx.MockTransport(reply('{"files":[', "length")))
    assert cut_off._raw("s", "u", {}).text == '{"files":['  # hitting the token limit is the model's own miss


def test_ollama_connection_failure_is_not_a_model_failure():
    import httpx

    from slm.llm.ollama import OllamaClient

    def refuse(req):
        raise httpx.ConnectError("refused")

    with pytest.raises(BackendUnavailable):
        OllamaClient("m", transport=httpx.MockTransport(refuse))._raw("s", "u", {})


@pytest.mark.parametrize("level", [1, 2, 3])
def test_slim_prompts_keep_every_token_the_grader_checks(level):
    for project in projects(1):
        plan = project.plan
        for t in plan.tasks:
            text = slim_prompt(plan, t, level)
            assert canonical_path(t.domain, t.kind, t.target) in text
            assert all(use_token(x) in text for x in plan.requires(t))
            assert all(provide_token(x) in text for x in t.provides())


def test_each_slim_level_is_smaller_than_the_last():
    def size(arm_level):
        client = SlimClient(Perfect(P), "G4")
        client.level = arm_level
        total = 0
        for t in P.plan.tasks:
            total += len(client.system_prompt(t, agent_for("G4", t))) + len(slim_prompt(P.plan, t, arm_level))
        return total

    full = sum(len(specialist_system(t.domain)) + len(specialist_prompt(P.plan, t)) for t in P.plan.tasks)
    sizes = [full, size(1), size(2), size(3)]
    assert sizes == sorted(sizes, reverse=True) and len(set(sizes)) == 4


def test_slim_arm_really_sends_the_smaller_prompt(tmp_path):
    client = Recording(P)
    assert run("mgr-slim3", client, tmp_path)[-1].gold_task_rate == 1.0
    assert not any("The rest of the team provides" in u for u in client.users[1:])
    assert not any('{"files"' in system for system in client.systems[1:])


def _slim_row(arm, project, rate, by_domain, tok=100, gold=False):
    return {"arm": arm, "project_id": project, "template_id": project, "gold_task_rate": rate, "gold_pass": gold,
            "by_domain": by_domain, "tok_in": tok, "calls": 13}


def test_slim_report_fails_a_level_that_loses_anything_even_if_the_average_holds():
    from slm.arch.__main__ import slim_report

    rows = [_slim_row("mgr-G4", "p", 0.5, {"auth": 1.0, "network": 0.0}, 100),
            _slim_row("mgr-slim1", "p", 0.5, {"auth": 1.0, "network": 0.0}, 60),
            _slim_row("mgr-slim2", "p", 0.5, {"auth": 0.0, "network": 1.0}, 50)]
    text = slim_report(rows)
    assert "| mgr-slim1 | 1 | -40% |" in text and "holds so far" in text
    assert "p/auth" in text and "fails" in text.split("mgr-slim2")[1]


def test_slim_report_fails_a_level_that_loses_a_full_pass():
    from slm.arch.__main__ import slim_report

    rows = [_slim_row("mgr-G4", "p", 1.0, {"auth": 1.0}, gold=True), _slim_row("mgr-slim1", "p", 1.0, {"auth": 1.0}, gold=False)]
    assert "fails" in slim_report(rows)


@pytest.mark.parametrize("arm,level", COMBO_ARMS.items())
def test_combo_uses_the_level_memory_and_a_repair_prompt_with_the_failures(arm, level, tmp_path):
    class FailsFirstTask(Recording):
        first = None

        def _raw(self, system, user, json_schema):
            if json_schema.get("title") == "Artifact" and "previous attempt" not in user and self.first is None:
                self.first = CALL.get()[1].id
            if json_schema.get("title") == "Artifact" and CALL.get()[1].id == self.first and "previous attempt" not in user:
                self.users.append(user)
                return RawResponse('{"files": [{"path": "README.md", "content": "todo"}], "summary": ""}', 1, 1)
            return super()._raw(system, user, json_schema)

    client = FailsFirstTask(P)
    res = run(arm, client, tmp_path)[-1]
    assert res.gold_task_rate == 1.0 and res.gold_pass  # the repair round fixed the one bad task
    steps = [u for u in client.users[1:] if "previous attempt" not in u]
    repairs = [u for u in client.users[1:] if "previous attempt" in u]
    assert len(repairs) == 1 and "failed these checks" in repairs[0] and "Already built" not in repairs[0]
    assert any("Already built by earlier steps" in u for u in steps)
    assert all(("The rest of the team provides" in u) == (level == 0) for u in steps)


def _pick_rows(levels_ok):
    base = {"arm": "mgr-G4", "project_id": "p", "template_id": "p", "gold_task_rate": 0.9, "gold_pass": False,
            "by_domain": {"auth": 0.9}}
    rows = [base]
    for level, ok in levels_ok.items():
        rate = 0.9 if ok else 0.5
        rows.append({**base, "arm": f"mgr-slim{level}", "gold_task_rate": rate, "by_domain": {"auth": rate}})
    return rows


@pytest.mark.parametrize("levels,want", [({1: True, 2: True, 3: True}, "mgr-combo-s3"), ({1: True, 2: True, 3: False}, "mgr-combo-s2"),
                                         ({1: False, 2: False, 3: False}, "mgr-combo-s0"), ({}, "mgr-combo-s0"),
                                         ({1: False, 2: True, 3: False}, "mgr-combo-s2")])
def test_combo_picks_the_smallest_level_that_lost_nothing(levels, want):
    from slm.arch.__main__ import pick_combo_arm

    assert pick_combo_arm(_pick_rows(levels)) == want


def test_combo_ignores_a_level_that_has_not_finished_every_project():
    from slm.arch.__main__ import pick_combo_arm

    rows = _pick_rows({3: True}) + [{**_pick_rows({})[0], "project_id": "q"}]
    assert pick_combo_arm(rows) == "mgr-combo-s0"


class FirstTaskBad(Recording):
    """Writes the wrong file for one task until a repair prompt says what failed."""

    first = None

    def _raw(self, system, user, json_schema):
        if json_schema.get("title") == "Artifact":
            task = CALL.get()[1]
            self.first = self.first or task.id
            if task.id == self.first and "previous attempt" not in user:
                self.users.append(user)
                return RawResponse('{"files": [{"path": "README.md", "content": "todo"}], "summary": ""}', 1, 1)
        return super()._raw(system, user, json_schema)


def test_runfix_sends_run_failures_to_the_model_and_stops_once_it_passes(tmp_path):
    client = FirstTaskBad(P)
    res = run("mgr-G4-runfix", client, tmp_path)[-1]
    repairs = [u for u in client.users if "previous attempt" in u]
    assert res.gold_pass and len(repairs) == 1 and "python:src/" in repairs[0] and "(missing)" in repairs[0]


def test_runfix_keeps_the_best_version_when_a_fix_makes_it_worse(tmp_path, monkeypatch):
    rates = iter([0.9, 0.2, 0.5])
    seen = []

    def check(files, plan):
        seen.append(len(files))
        return {"checks": [{"group": "api", "name": "create:/api/invoices", "ok": False, "detail": ""}], "by_group": {},
                "rate": next(rates), "passed": False}

    class WorseOnRepair(Recording):
        def _raw(self, system, user, json_schema):
            if "previous attempt" in user:
                self.users.append(user)
                return RawResponse('{"files": [{"path": "README.md", "content": "worse"}], "summary": ""}', 1, 1)
            return super()._raw(system, user, json_schema)

    monkeypatch.setattr(runner, "run_check", check)
    res = run("mgr-G4-runfix", WorseOnRepair(P), tmp_path)[-1]
    assert len(seen) == 3 and res.gold_task_rate == 1.0  # the first version was best, so it was the one kept


def test_runfix_records_no_result_when_the_toolchain_fails(tmp_path, monkeypatch):
    def down(files, plan):
        raise BackendUnavailable("no toolchain")

    monkeypatch.setattr(runner, "run_check", down)
    with pytest.raises(BackendUnavailable):
        run("mgr-G4-runfix", Perfect(P), tmp_path)


def _failed(name, detail=""):
    return {"group": "x", "name": name, "ok": False, "detail": detail}


def _owner(check):
    ids = runner.failures_by_task(P.plan, [check])
    return {P.plan.task(i).kind + ":" + P.plan.task(i).target for i in ids}


@pytest.mark.parametrize("check,want", [
    (_failed("create:/api/invoices"), {"rest:invoice"}),
    (_failed("list:/api/clients", "500 AttributeError: no fetch_all at src/network/client_api.py:12"), {"rest:client"}),
    (_failed("guard_blocks:/invoices", "404"), {"guards:routes"}),
    (_failed("users_accepts_a_session", "no session_token"), {"schema:users"}),
    (_failed("loads:invoice.sql", "syntax error"), {"schema:invoice"}),
    (_failed("python:src/auth/session.py", "SyntaxError"), {"session:session"}),
    (_failed("shell_bundles", 'Could not resolve "./X"'), {"layout:shell"}),
    (_failed("shell_bundles", 'Could not resolve "./X" at src/frontend/ClientPage.tsx'), {"page:client"}),
    (_failed("oauth_module_imports", "ImportError"), {"oauth:oauth"}),
    (_failed("table:invoice", "no table for it"), {"schema:invoice"}),
    (_failed("typescript:src/frontend/ClientPage.tsx", "missing"), {"page:client"}),
])
def test_each_failure_reaches_the_task_that_owns_it(check, want):
    assert _owner(check) == want


def test_a_passing_check_is_not_a_failure():
    assert runner.failures_by_task(P.plan, [{"group": "x", "name": "create:/api/invoices", "ok": True, "detail": ""}]) == {}


def test_run_check_never_sees_the_gold_plan(tmp_path, monkeypatch):
    seen = []

    def check(files, plan):
        seen.append(plan)
        return {"checks": [], "by_group": {}, "rate": 1.0, "passed": True}

    monkeypatch.setattr(runner, "run_check", check)
    client = Perfect(P)
    ps = asyncio.run(make_plan(P, client, Tracer(run_id="plan", trace_dir=tmp_path)))
    asyncio.run(run_arm("mgr-G4-runfix", P, client, Tracer(run_id="x", trace_dir=tmp_path), ps))
    assert seen and all(p is ps.plan for p in seen)


class RecordingSystem(Recording):
    def __init__(self, project, tracer=None):
        super().__init__(project, tracer)
        self.systems = []

    def _raw(self, system, user, json_schema):
        self.systems.append(system)
        return super()._raw(system, user, json_schema)


def test_promptfix_tells_auth_and_network_the_real_imports_and_db_methods(tmp_path):
    client = RecordingSystem(P)
    assert run("mgr-G4-promptfix", client, tmp_path)[-1].gold_pass
    told = [s for s in client.systems if "from src.database.db import db" in s and "await db.fetchrow(sql, *args)" in s]
    assert any("network specialist" in s for s in told) and any("auth specialist" in s for s in told)
    assert not any("src.database.db.db" in s for s in client.systems)


def test_promptfix_changes_no_other_arms_prompt():
    for domain in ("auth", "network"):
        assert "You may import: src.database.db.db" in teams.system_for("G4", domain)
        assert "fetch_all" not in teams.system_for("G4", domain)
    assert system_prompt("database", exact_imports=True) == system_prompt("database")
    assert system_prompt("frontend", exact_imports=True) == system_prompt("frontend")


# --- the shell, contract and context arms --------------------------------------


class PromptsByKind(Perfect):
    """Keeps the prompts each task was sent. Replies with a schema artifact that breaks nothing."""

    def __init__(self, project):
        super().__init__(project)
        self.prompts = {}

    def _raw(self, system, user, json_schema):
        if json_schema.get("title") != "ProjectPlan":
            _, task = CALL.get()
            self.prompts.setdefault(task.kind, []).append(user)
        return super()._raw(system, user, json_schema)


def contract_project():
    return next(p for p in projects(1) if p.template_id == "invoice_tracker")


def test_generated_shell_meets_its_own_contract_on_every_catalog_plan():
    from slm.arch.contract import generate_shell
    from slm.contracts import check_task

    for p in projects(1):
        task = next(t for t in p.plan.tasks if t.kind == "layout")
        checks = check_task(p.plan, task, generate_shell(p.plan, task))
        assert all(c.ok for c in checks), (p.template_id, [c.name for c in checks if not c.ok])


def test_generated_shell_imports_only_files_the_plan_writes():
    from slm.arch.contract import generate_shell

    p = contract_project()
    task = next(t for t in p.plan.tasks if t.kind == "layout")
    text = generate_shell(p.plan, task).files[0].content
    for t in (t for t in p.plan.tasks if t.kind == "page"):
        stem = canonical_path(t.domain, t.kind, t.target).rsplit("/", 1)[1].removesuffix(".tsx")
        assert f'from "./{stem}"' in text
    assert "/@/" not in text and 'from "/' not in text


def test_generated_shell_works_when_really_run_with_reference_code():
    from slm.arch.contract import generate_shell
    from slm.bench.runcheck import check_project, grader_root

    if not (grader_root() / "venv/bin/python").exists():
        pytest.skip("grader toolchain not installed")
    p = contract_project()
    shell = next(t for t in p.plan.tasks if t.kind == "layout")
    arts = gold_artifacts(p.plan) | {shell.id: generate_shell(p.plan, shell)}
    assert check_project([f for a in arts.values() for f in a.files], p.plan)["passed"]


def test_shell_arm_never_asks_a_model_for_the_shell(tmp_path):
    client = PromptsByKind(P)
    run("mgr-G4-shell", client, tmp_path)
    assert "layout" not in client.prompts and "schema" in client.prompts


def test_manager_text_cannot_override_the_contract():
    from slm.arch.contract import contract_prompt

    p = contract_project()
    task = next(t for t in p.plan.tasks if t.kind == "schema" and t.target != "users")
    bad = task.model_copy(update={"detail": f"Postgres table `{task.target}` with id, name, email, created_at."})
    prompt = contract_prompt(p.plan, bad)
    assert "name, email" not in prompt and "title TEXT NOT NULL" in prompt and "owner_id BIGINT" in prompt


def test_contract_states_the_shared_facts_each_kind_needs():
    from slm.arch.contract import contract_lines

    p = contract_project()
    by_kind = {t.kind: t for t in p.plan.tasks if t.target != "users"}
    rest = " ".join(contract_lines(by_kind["rest"]))
    assert "require no other field" in rest and "never as a tuple" in rest and "owner_id" in rest
    assert "session_token" in " ".join(contract_lines(next(t for t in p.plan.tasks if t.kind == "session")))
    assert "session_token TEXT" in contract_lines(next(t for t in p.plan.tasks if t.target == "users"))
    assert "await" in " ".join(contract_lines(by_kind["guards"]))
    assert contract_lines(by_kind["layout"]) == []


def test_context_shows_a_task_only_the_code_it_depends_on_and_stays_in_budget():
    from slm.arch.contract import MAX_CONTEXT_CHARS, dependency_block

    p = contract_project()
    arts = gold_artifacts(p.plan)
    rest = next(t for t in p.plan.tasks if t.kind == "rest")
    other = next(t for t in p.plan.tasks if t.kind == "schema" and t.target not in (rest.target, "users"))
    block = dependency_block(p.plan, rest, arts)
    assert f"CREATE TABLE {rest.target} (" in block and "require_session" in block
    assert f"CREATE TABLE {other.target} (" not in block
    assert dependency_block(p.plan, rest, {}) == ""
    huge = {k: Artifact(files=[f.model_copy(update={"content": f.content + "x" * 9000}) for f in a.files]) for k, a in arts.items()}
    assert len(dependency_block(p.plan, rest, huge)) <= MAX_CONTEXT_CHARS + 300


def test_context_arm_sends_earlier_code_to_later_tasks(tmp_path):
    client = PromptsByKind(P)
    run("mgr-G4-context", client, tmp_path)
    assert all("Code your teammates already wrote" not in x for x in client.prompts["schema"])
    assert all("CREATE TABLE" in x for x in client.prompts["rest"])


def test_new_arms_build_a_passing_project_from_correct_replies(tmp_path):
    for arm in ("mgr-G4-shell", "mgr-G4-contract", "mgr-G4-context"):
        assert run(arm, Perfect(P), tmp_path)[-1].gold_pass, arm


def test_repairs_keep_their_failure_text_under_the_contract():
    from slm.arch.runner import ContractClient

    p = contract_project()
    seen = {}

    class Inner(Perfect):
        def _raw(self, system, user, json_schema):
            seen["user"] = user
            return super()._raw(system, user, json_schema)

    task = next(t for t in p.plan.tasks if t.kind == "schema")
    CALL.set((p.plan, task))
    ContractClient(Inner(p), "G4").complete("", "attempt failed: column missing", Artifact, caller="repair", callee="repair")
    assert seen["user"] == "attempt failed: column missing"


def test_new_arms_change_no_existing_arms_prompts():
    p = contract_project()
    task = next(t for t in p.plan.tasks if t.kind == "schema")
    assert runner.ExactImportsClient(Perfect(p), "G4").task_prompt(p.plan, task) == specialist_prompt(p.plan, task)
    assert runner.TeamClient(Perfect(p), "G4").task_prompt(p.plan, task) == specialist_prompt(p.plan, task)
