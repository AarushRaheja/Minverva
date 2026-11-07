"""Minerva's bridge, integrator and pipeline. Stack tests start Postgres, FastAPI and a browser: set MINERVA_STACK=1."""

from __future__ import annotations

import json
import os
import re

import pytest

from minerva import vendored  # noqa: F401
from frontendslm.prompts import CONTRACT, FULLSTACK_CONTRACT, architect_messages
from frontendslm.repair import component_repair_messages

from minerva.bridge.case import build_case
from minerva.bridge.contract import RESERVED_TABLES, contract_from_plan, prepare_spec, render_api_client
from minerva.bridge.reference_ui import render_reference_ui
from minerva.bridge.tests import ANY_TITLE, compile_tests, journey_tests, seed_sql
from minerva.integrator.assemble import HOST_KINDS, assemble, write_tree
from minerva.offline import OfflineEngine
from minerva.pipeline import FALLBACK, FAILED, FUNCTIONAL, Options, build
from minerva.verify.audit import LocalAuditor, stack_failures
from slm.bench.catalog import TRAIN_TEMPLATES, build_plan, gold_artifacts
from slm.contracts import ProjectPlan, Task
from slm.domains import detail_for
from slm.manager.spec import gold_spec, to_plan, without_oauth_plan

stack = pytest.mark.skipif(not os.environ.get("MINERVA_STACK"), reason="set MINERVA_STACK=1 to start the real stack")


def _plan() -> ProjectPlan:
    return without_oauth_plan(build_plan(TRAIN_TEMPLATES[0]))


def _contract():
    return contract_from_plan(_plan(), "Track invoices for clients")


def _backend():
    plan = _plan()
    return {k: v for k, v in gold_artifacts(plan).items() if plan.task(k).kind not in HOST_KINDS}


def test_contract_covers_every_rest_entity_and_leads_with_the_form_entity():
    plan, contract = _plan(), _contract()
    assert {e.slug for e in contract.entities} == {t.target for t in plan.tasks if t.kind == "rest"}
    assert contract.primary.slug == next(t.target for t in plan.tasks if t.kind == "form")


def test_api_client_has_functions_for_every_entity_and_only_real_endpoints():
    contract = _contract()
    source = render_api_client(contract)
    for e in contract.entities:
        assert f"export async function list{e.pascal}(" in source
        assert f"export async function create{e.pascal}(" in source
    paths = set(re.findall(r'"(/api/[^"]+)"', source))
    assert paths == {"/api/auth/me", "/api/auth/login", "/api/auth/signup", "/api/auth/logout"} | {e.base for e in contract.entities}


def test_visible_tests_never_reveal_bound_values():
    compiled = compile_tests(_contract(), "s")
    shown = json.dumps(compiled.visible)
    assert compiled.nonce not in shown
    assert ANY_TITLE in shown
    assert compiled.nonce in json.dumps(compiled.bound)
    assert [t["id"] for t in compiled.visible] == [t["id"] for t in compiled.bound]


def test_each_round_uses_different_values_so_hardcoding_cannot_pass():
    contract = _contract()
    assert compile_tests(contract, "a").nonce != compile_tests(contract, "b").nonce


def test_seed_sql_matches_the_bound_tests():
    compiled = compile_tests(_contract(), "s")
    assert compiled.seed_sql == seed_sql(_contract(), compiled.nonce)
    assert compiled.nonce in compiled.seed_sql


def test_reserved_table_names_are_renamed_consistently():
    plan = _plan()
    target = next(t.target for t in plan.tasks if t.kind == "form")
    assert "order" in RESERVED_TABLES

    def rename(t: Task) -> Task:
        if t.target != target:
            return t
        return t.model_copy(update={"target": "order", "detail": detail_for(t.domain, t.kind, "order")})

    bad = ProjectPlan(name=plan.name, stack=plan.stack, tasks=[rename(t) for t in plan.tasks])
    fixed = to_plan(prepare_spec(gold_spec(bad).model_dump_json()))
    targets = {t.target for t in fixed.tasks}
    assert "order" not in targets and "order_record" in targets
    assert "`order_record`" in next(t.detail for t in fixed.tasks if t.kind == "schema" and t.target == "order_record")


def test_prepare_spec_rejects_a_plan_that_does_not_parse():
    with pytest.raises(ValueError):
        prepare_spec('{"name": "cut off')


def test_fullstack_prompt_lifts_the_backend_ban_and_the_default_keeps_it():
    assert "backend" in CONTRACT and "network calls" in CONTRACT  # the original benchmark contract is untouched
    assert "network calls" not in FULLSTACK_CONTRACT and "./api" in FULLSTACK_CONTRACT
    contract = _contract()
    case = build_case(contract, compile_tests(contract, "s"), "run")
    messages = architect_messages(case, "A1")
    assert FULLSTACK_CONTRACT in messages[0]["content"]
    assert "local state" not in messages[0]["content"]
    assert "export async function" in messages[-1]["content"]


def test_repair_prompt_keeps_the_api_contract():
    contract = _contract()
    case = build_case(contract, compile_tests(contract, "s"), "run")
    case["repair_context"] = {"previous_source": "x", "measured_evidence": {"measured_checks": []}}
    messages = component_repair_messages(case)
    assert FULLSTACK_CONTRACT in messages[0]["content"]
    assert "export async function" in messages[1]["content"]


def test_assemble_keeps_backend_seam_checks_and_adds_what_the_project_needs_to_run():
    contract = _contract()
    built = assemble("p", _plan(), None, _backend(), contract, render_reference_ui(contract), "/* css */")
    assert built.deliverable.ok, built.deliverable.failures
    for name in ("frontend/src/App.tsx", "frontend/src/api.ts", "frontend/package.json", "frontend/package-lock.json",
                 "frontend/index.html", "src/auth/accounts.py", "src/spa.py", "src/database/migrate.py", "Makefile"):
        assert name in built.files, name
    app = built.files["src/app.py"]
    assert app.index("include_router(accounts_router)") < app.index("mount_spa(app)")
    assert not any(n.startswith("src/frontend/") for n in built.files)


def test_every_project_prepares_its_own_database_on_startup():
    contract = _contract()
    files = assemble("p", _plan(), None, _backend(), contract, "x", "y").files
    app = files["src/app.py"]
    assert 'add_event_handler("startup", prepare_database)' in app
    assert 'add_event_handler("startup", build_frontend)' in app
    assert 'add_event_handler("shutdown", stop_database)' in app
    assert "test -x .venv/bin/python ||" in files["Makefile"]
    assert app.index("prepare_database)") < app.index("mount_spa(app)")
    assert "CREATE DATABASE" in files["src/database/bootstrap.py"] and "apply_migrations" in files["src/database/bootstrap.py"]
    assert "APP_ENV" in files["src/database/bootstrap.py"]
    assert "pg_advisory_lock" in files["src/database/migrate.py"]
    for name in ("src/database/bootstrap.py", "src/database/migrate.py", "src/spa.py", "src/main.py"):
        compile(files[name], name, "exec")
    assert "\npreview:" in files["Makefile"] and "\t.venv/bin/python -m src.main" in files["Makefile"]
    assert "createdb" not in files["README.md"] and "make preview" in files["README.md"]
    assert ".data/" in files[".gitignore"]
    assert '0.0.0.0' not in files["src/main.py"]


def test_reassemble_rebuilds_a_finished_run_without_a_model(tmp_path):
    from minerva.pipeline import reassemble

    run = tmp_path / "run"
    (run / "stages").mkdir(parents=True)
    plan = _plan()
    spec = gold_spec(plan)
    (run / "run.json").write_text(json.dumps({"brief": "b", "look": "l", "engine": "modal"}))
    (run / "status.json").write_text(json.dumps({"status": "fallback_ui", "frontend_source": "reference", "best_round": 0}))
    (run / "REPORT.md").write_text("# old")
    (run / "stages" / "plan.json").write_text(json.dumps({"spec": spec.model_dump_json()}))
    (run / "stages" / "backend.json").write_text(json.dumps({"artifacts": {k: v.model_dump_json() for k, v in _backend().items()}}))
    (run / "project" / ".data").mkdir(parents=True)
    (run / "project" / ".data" / "kept").write_text("database")
    (run / "project" / "stale.txt").write_text("old")
    project = reassemble(run)
    assert (project / "src" / "database" / "bootstrap.py").exists()
    assert not (project / "stale.txt").exists()
    assert (run / "project.previous" / "stale.txt").read_text() == "old"
    assert (project / ".data" / "kept").read_text() == "database"
    assert "not been through `verify`" in (project / "REPORT.md").read_text()
    assert json.loads((run / "status.json").read_text())["verify_stale"] is True
    reassemble(run)
    assert (run / "REPORT.md").read_text().count("Re-assembled") == 1


def test_assemble_still_fails_when_a_backend_task_is_missing():
    contract = _contract()
    backend = _backend()
    backend.pop(next(iter(backend)))
    built = assemble("p", _plan(), None, backend, contract, "x", "y")
    assert any(f.startswith("all_tasks_delivered") for f in built.deliverable.failures)


def test_integrate_without_host_kinds_still_requires_frontend_tasks():
    from slm.contracts import integrate

    plan = _plan()
    assert any(f.startswith("all_tasks_delivered") for f in integrate("p", plan, _backend()).failures)


def test_write_tree_refuses_paths_outside_the_project(tmp_path):
    with pytest.raises(ValueError):
        write_tree({"../escape.py": "x"}, tmp_path / "project")
    assert not (tmp_path / "escape.py").exists()


def test_local_auditor_refuses_untrusted_code():
    with pytest.raises(ValueError):
        LocalAuditor(trusted=False)


def test_stack_failures_name_backend_faults_and_refuse_an_empty_report():
    assert stack_failures({"stack": {}, "api_checks": []}) == ["no API checks ran"]
    bad = {"stack": {"migrate": {"ok": False, "log": "syntax error"}}, "api_checks": [{"name": "list:/a", "ok": False, "detail": "500"}]}
    assert any("syntax error" in f for f in stack_failures(bad)) and any("list:/a" in f for f in stack_failures(bad))


def test_journey_is_a_signed_out_flow_that_ends_with_the_row_still_there():
    test = journey_tests(_contract())[0]
    assert test["signed_out"] is True
    assert test["steps"][-1]["action"] == "expect_text"


class _Unplannable(OfflineEngine):
    def plan(self, brief):
        return {"spec": '{"name": "cut off', "seconds": 0, "usd": 0.5}


def test_a_failed_plan_stops_the_run_and_says_so(tmp_path):
    result = build("anything", _Unplannable(), tmp_path / "run")
    assert (result.status, result.stage) == (FAILED, "plan")
    report = (tmp_path / "run" / "REPORT.md").read_text()
    assert "FAILED" in report and "no model was called" in report
    assert result.exit_code == 30


def test_budget_stops_a_stage_before_it_runs(tmp_path):
    class Costly(OfflineEngine):
        def cost_estimate(self, stage):
            return 5.0

        def plan(self, brief):
            raise AssertionError("must not run")

    result = build("anything", Costly(), tmp_path / "run", Options(budget_usd=1.0))
    assert (result.status, result.stage) == (FAILED, "budget")


def test_a_run_directory_cannot_be_reused_for_another_brief(tmp_path):
    build("first", _Unplannable(), tmp_path / "run")
    with pytest.raises(ValueError):
        build("second", _Unplannable(), tmp_path / "run")


def test_a_finished_stage_is_not_paid_for_twice(tmp_path):
    class Counting(_Unplannable):
        calls = 0

        def plan(self, brief):
            Counting.calls += 1
            return super().plan(brief)

    build("same", Counting(), tmp_path / "run")
    build("same", Counting(), tmp_path / "run")
    assert Counting.calls == 1


def test_the_look_reaches_the_frontend_and_never_the_manager(tmp_path):
    seen = {}

    class Spy(_Unplannable):
        def plan(self, brief):
            seen["manager"] = brief
            return super().plan(brief)

    build("Track invoices", Spy(), tmp_path / "run", look="Warm, editorial, serif headings")
    assert seen["manager"] == "Track invoices"
    assert json.loads((tmp_path / "run" / "run.json").read_text())["look"] == "Warm, editorial, serif headings"
    assert "serif headings" in (tmp_path / "run" / "REPORT.md").read_text()

    contract = contract_from_plan(_plan(), "Track invoices", "Warm, editorial, serif headings")
    case = build_case(contract, compile_tests(contract, "s"), "run")
    assert case["spec"]["style"] == {"requested_look": "Warm, editorial, serif headings"}
    assert "serif headings" in architect_messages(case, "A1")[-1]["content"]
    built = assemble("p", _plan(), None, _backend(), contract, "x", "y")
    assert "serif headings" in built.files["README.md"] and "serif headings" in built.files["BRIEF.json"]


def test_no_look_leaves_the_style_empty_and_the_default_to_the_intent_stage():
    contract = _contract()
    assert build_case(contract, compile_tests(contract, "s"), "run")["spec"]["style"] == {}
    assert "Requested look" not in assemble("p", _plan(), None, _backend(), contract, "x", "y").files["README.md"]


def test_changing_the_look_on_a_finished_run_is_refused(tmp_path):
    build("same", _Unplannable(), tmp_path / "run", look="dark")
    with pytest.raises(ValueError):
        build("same", _Unplannable(), tmp_path / "run", look="light")


@stack
def test_offline_build_end_to_end(tmp_path):
    result = build("Track invoices", OfflineEngine(), tmp_path / "run")
    assert result.status == FUNCTIONAL  # never "verified": no Critic model ran, and it says so
    assert result.summary["journey_ok"] is True
    assert result.summary["rounds"][0]["score"]["audit_pass"] is True
    assert (result.project / "frontend" / "src" / "App.tsx").exists()
    assert not (result.project / "frontend" / "dist").exists()
    assert not (result.project / "frontend" / "node_modules").exists()


@stack
def test_repair_round_receives_measured_failures_and_can_fix_the_ui(tmp_path):
    seen = []

    def broken_first(source, job):
        seen.append(job.get("repair_context"))
        return source.replace("panel.create(title.trim())", "panel.create('new row')") if len(seen) == 1 else source

    result = build("Track invoices", OfflineEngine(broken_first), tmp_path / "run", Options(max_repairs=1))
    assert result.status == FUNCTIONAL
    assert seen[0] is None and seen[1]["measured_evidence"]["measured_checks"]
    assert [r["score"]["audit_pass"] for r in result.summary["rounds"]] == [False, True]
    assert result.summary["best_round"] == 1


@stack
def test_a_ui_that_never_works_falls_back_and_is_labelled(tmp_path):
    def always_broken(source, job):
        return source.replace('data-testid="sign-out"', "") + f"\n// attempt {bool(job.get('repair_context'))}\n"

    result = build("Track invoices", OfflineEngine(always_broken), tmp_path / "run", Options(max_repairs=1))
    assert result.status == FALLBACK and result.exit_code == 20
    assert result.summary["frontend_source"] == "reference"
    assert "FALLBACK UI" in (tmp_path / "run" / "REPORT.md").read_text()
