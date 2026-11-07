"""Live progress for UIs: events.jsonl, the `run:` line, `minerva engines`, and stopping a build cleanly."""

from __future__ import annotations

import json
import os
import signal

import pytest
from typer.testing import CliRunner

from minerva import cli
from minerva.engines import MODAL_ARCHITECT_USD, MODAL_STAGE_USD, as_json, engines
from minerva.events import EVENTS_FILE, Events
from minerva.offline import OfflineEngine
from minerva.pipeline import FAILED, FUNCTIONAL, build

stack = pytest.mark.skipif(not os.environ.get("MINERVA_STACK"), reason="set MINERVA_STACK=1 to start the real stack")


def _events(run_dir):
    return [json.loads(line) for line in (run_dir / EVENTS_FILE).read_text().splitlines()]


class _Unplannable(OfflineEngine):
    def plan(self, brief):
        return {"spec": '{"name": "cut off', "seconds": 1.5, "usd": 0.5}


def test_a_failed_plan_is_traced_from_start_to_end(tmp_path):
    build("Track invoices", _Unplannable(), tmp_path / "run", look="Warm")
    ev = _events(tmp_path / "run")
    assert [e["event"] for e in ev] == ["run_start", "stage_start", "stage_end", "run_end"]
    start, stage_start, stage_end, end = ev
    assert (start["engine"], start["brief"], start["look"], start["resumed"]) == ("offline", "Track invoices", "Warm", False)
    assert stage_start["stage"] == stage_end["stage"] == "plan" and stage_start["estimate_usd"] == 0.0
    assert (stage_end["ok"], stage_end["cached"], stage_end["seconds"], stage_end["usd"]) == (True, False, 1.5, 0.5)
    assert (end["status"], end["stage"], end["exit_code"], end["usd"]) == (FAILED, "plan", 30, 0.5)
    assert all(isinstance(e["ts"], float) for e in ev)


def test_a_resumed_run_appends_and_marks_reused_stages(tmp_path):
    build("Track invoices", _Unplannable(), tmp_path / "run")
    build("Track invoices", _Unplannable(), tmp_path / "run")
    ev = _events(tmp_path / "run")
    second = ev[[i for i, e in enumerate(ev) if e["event"] == "run_start"][-1]:]
    assert second[0]["resumed"] is True and second[0]["spent_usd"] == 0.5
    assert second[1] == {**second[1], "event": "stage_end", "stage": "plan", "cached": True, "ok": True}
    assert second[-1]["event"] == "run_end"


@pytest.mark.parametrize("raised, status", [(KeyboardInterrupt, "stopped"), (RuntimeError("boom"), "error")])
def test_an_interrupted_or_crashed_run_still_ends_its_events(tmp_path, raised, status):
    class Interrupted(OfflineEngine):
        def plan(self, brief):
            raise raised

    with pytest.raises(type(raised) if isinstance(raised, BaseException) else raised):
        build("Track invoices", Interrupted(), tmp_path / "run")
    ev = _events(tmp_path / "run")
    assert ev[-2] == {**ev[-2], "event": "stage_end", "stage": "plan", "ok": False}
    assert ev[-1]["event"] == "run_end" and ev[-1]["status"] == status
    assert not (tmp_path / "run" / "status.json").exists()


def test_a_step_reports_what_the_block_measured(tmp_path):
    events = Events(tmp_path)
    with events.step("audit", round_=1, estimate=0.02) as outcome:
        outcome.update(ok=False, usd=0.02, detail="failed: no_overflow")
    events.cached("architect", round_=1)
    start, end, cached = _events(tmp_path)
    assert (start["stage"], start["round"], start["estimate_usd"]) == ("audit", 1, 0.02)
    assert (end["ok"], end["usd"], end["detail"]) == (False, 0.02, "failed: no_overflow")
    assert cached == {**cached, "stage": "architect", "round": 1, "cached": True, "seconds": 0.0}


def test_the_cli_prints_the_run_directory_first(tmp_path, monkeypatch):
    monkeypatch.setattr(cli, "_engine", lambda name, architect: _Unplannable())
    out = tmp_path / "run"
    result = CliRunner().invoke(cli.app, ["build", "Track invoices", "--engine", "offline", "--out", str(out)])
    assert result.output.splitlines()[0] == f"run: {out}"
    assert result.exit_code == 30
    assert _events(out)[-1]["status"] == FAILED


def test_the_cli_turns_ctrl_c_into_a_resumable_stop(tmp_path, monkeypatch):
    class Interrupted(OfflineEngine):
        def plan(self, brief):
            raise KeyboardInterrupt

    monkeypatch.setattr(cli, "_engine", lambda name, architect: Interrupted())
    previous = signal.getsignal(signal.SIGTERM)
    try:
        result = CliRunner().invoke(cli.app, ["build", "Track invoices", "--out", str(tmp_path / "run")])
        assert result.exit_code == 130
        assert "Resume with: --out" in result.output
        with pytest.raises(KeyboardInterrupt):
            os.kill(os.getpid(), signal.SIGTERM)  # the build command makes SIGTERM behave like Ctrl-C
    finally:
        signal.signal(signal.SIGTERM, previous)


def test_engines_say_where_data_goes_and_what_it_costs():
    rows = {r["name"]: r for r in as_json(max_repairs=1, architect="thinking")}
    assert set(rows) >= {"offline", "modal"}
    offline, modal = rows["offline"], rows["modal"]
    assert offline["leaves_machine"] is False and offline["costs_money"] is False and offline["estimate_total_usd"] == 0.0
    assert modal["leaves_machine"] is True and modal["costs_money"] is True
    assert "Modal" in modal["data_goes_to"] and "third-party" in modal["data_goes_to"]
    s = MODAL_STAGE_USD
    two_rounds = s["plan"] + s["backend"] + s["intent"] + 2 * (MODAL_ARCHITECT_USD["thinking"] + s["audit"]) + s["critic"] + 2 * s["audit"]
    assert modal["estimate_total_usd"] == round(two_rounds, 2) == modal["estimates"]["thinking"][1]
    assert modal["estimates"]["instruct"][0] < modal["estimates"]["thinking"][0]
    assert {e.name for e in engines()} == set(rows)


def test_modal_engine_prices_come_from_the_shared_table():
    pytest.importorskip("modal")
    from modal_apps.pipeline_app import ModalEngine

    for architect, price in MODAL_ARCHITECT_USD.items():
        engine = ModalEngine(architect=architect)
        assert engine.cost_estimate("architect") == price
        assert {k: engine.cost_estimate(k) for k in MODAL_STAGE_USD} == MODAL_STAGE_USD


@stack
def test_an_offline_build_emits_every_stage_in_order(tmp_path):
    result = build("Track invoices", OfflineEngine(), tmp_path / "run", look="Warm")
    assert result.status == FUNCTIONAL
    ends = [(e["stage"], e.get("round")) for e in _events(tmp_path / "run") if e["event"] == "stage_end"]
    assert ends == [("plan", None), ("backend", None), ("seams", None), ("preflight", None), ("intent", None),
                    ("architect", 0), ("audit", 0), ("critic", 0), ("verify", None), ("project", None)]
    ev = _events(tmp_path / "run")
    assert ev[-1] == {**ev[-1], "event": "run_end", "status": FUNCTIONAL, "exit_code": 10}
    verify = next(e for e in ev if e["event"] == "stage_end" and e["stage"] == "verify")
    assert verify["ok"] is True and "passed" in verify["detail"]


def test_a_partial_audit_from_a_stopped_run_is_audited_again(tmp_path):
    from minerva.pipeline import AUDIT_DONE, _audit, _load_audit

    out = tmp_path / "render"
    out.mkdir()
    (out / "evidence.json").write_text('{"tests": [], "views": {}}')  # what a harness stopped mid-run leaves
    assert _load_audit(out) is None

    class Engine:
        def audit(self, files, task, out_dir):
            (out_dir / "evidence.json").write_text('{"tests": [{"id": "t", "passed": true}]}')
            return {"tests": [{"id": "t", "passed": True}]}

    _audit(Engine(), {}, {}, out)
    assert (out / AUDIT_DONE).exists()
    assert _load_audit(out) == {"tests": [{"id": "t", "passed": True}]}
