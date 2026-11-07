"""The run check: does a project really work? The calibration cases run real code when the toolchain is installed."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from slm.arch.__main__ import load_files, pick_combo_arm, projects, run_table, save_files, select_best, with_run_scores
from slm.arch.runner import Result, gold_grade
from slm.bench.catalog import gold_artifacts
from slm.bench.runcheck import GraderUnavailable, check_project, sandbox_profile, spec_for, summarize
from slm.contracts import ArtifactFile
from slm.domains import provide_token, use_token

P = projects(1)[0]
ARTS = gold_artifacts(P.plan)
GOLD = [f for a in ARTS.values() for f in a.files]
needs_toolchain = pytest.mark.skipif(not Path("out/grader/venv/bin/python").exists(),
                                     reason="run `python -m slm.arch setup-grader` to include these")


def hollow():
    out = []
    for t in P.plan.tasks:
        for f in ARTS[t.id].files:
            tokens = [provide_token(s) for s in t.provides()] + [use_token(s) for s in P.plan.requires(t)]
            mark = "# " if f.path.endswith(".py") else ("-- " if f.path.endswith(".sql") else "// ")
            out.append(ArtifactFile(path=f.path, content="\n".join(mark + x for x in tokens) + "\n"))
    return out


def plural():
    def swap(s):
        for w in ("invoice", "client"):
            s = re.sub(rf"\\b(CREATE TABLE|FROM|INTO|ON|REFERENCES) {w}\\b", rf"\\1 {w}s", s)
        return s

    return [ArtifactFile(path=f.path.replace("/invoice.sql", "/invoices.sql").replace("/client.sql", "/clients.sql"),
                         content=swap(f.content)) for f in GOLD]


def spec_grade(files):
    res = Result(arm="x", project_id=P.id, template_id=P.template_id)
    gold_grade(P, files, res)
    return res


@needs_toolchain
def test_reference_project_works():
    assert check_project(GOLD, P.plan)["passed"]


@needs_toolchain
def test_comments_repeating_the_tokens_fool_the_string_grader_but_not_this():
    files = hollow()
    assert spec_grade(files).gold_pass
    rep = check_project(files, P.plan)
    assert not rep["passed"] and rep["by_group"]["api"] == 0 and rep["by_group"]["database"] == 0


@needs_toolchain
def test_syntax_errors_fool_the_string_grader_but_not_this():
    files = [ArtifactFile(path=f.path, content=f.content + "\n def ((( !!! syntax error\n") for f in GOLD]
    assert spec_grade(files).gold_pass
    rep = check_project(files, P.plan)
    assert rep["rate"] == 0 and not rep["passed"]


@needs_toolchain
def test_consistent_plural_tables_fail_the_string_grader_but_pass_this():
    files = plural()
    assert not spec_grade(files).gold_pass
    assert check_project(files, P.plan)["passed"]


@needs_toolchain
def test_an_endpoint_that_ignores_the_session_loses_the_auth_check():
    # Anyone can create rows here. The owner is a real user, so the request itself succeeds.
    def open_up(text):
        return text.replace(", user: dict = Depends(require_session)", "").replace('user["id"]', "1")

    files = [ArtifactFile(path=f.path, content=open_up(f.content)) if f.path.endswith("_api.py") else f for f in GOLD]
    rep = check_project(files, P.plan)
    assert not rep["passed"] and rep["by_group"]["api"] == 1 and rep["by_group"]["auth"] < 1


@needs_toolchain
def test_a_missing_guard_is_not_counted_as_blocking_the_page():
    files = [ArtifactFile(path=f.path, content=f.content.replace("await require_session(request)", "pass"))
             if f.path.endswith("guards.py") else f for f in GOLD]
    rep = check_project(files, P.plan)
    failed = {c["name"] for c in rep["checks"] if not c["ok"]}
    assert failed == {"guard_blocks:/invoices", "guard_blocks:/clients"}  # those pages 404 once nothing blocks them


@needs_toolchain
def test_generated_code_cannot_escape_the_sandbox(tmp_path):
    home_file = Path.home() / ".zshrc"
    outside = Path("/private/tmp/slm-sandbox-test-escape.txt")
    outside.unlink(missing_ok=True)
    evil = (f"\nimport socket\nout = []\n"
            f"for fn in (lambda: open({str(home_file)!r}).read(), lambda: open({str(outside)!r}, 'w').write('x'),\n"
            f"           lambda: socket.create_connection(('1.1.1.1', 53), timeout=3)):\n"
            f"    try:\n        fn()\n        out.append('ALLOWED')\n"
            f"    except OSError as e:\n        out.append('blocked')\n"
            f"raise RuntimeError(','.join(out))\n")
    files = [ArtifactFile(path=f.path, content=f.content + evil) if f.path.endswith("oauth.py") else f for f in GOLD]
    rep = check_project(files, P.plan)
    detail = next(c["detail"] for c in rep["checks"] if c["name"] == "oauth_module_imports")
    assert detail == "RuntimeError: blocked,blocked,blocked" and not outside.exists()


def test_paths_leaving_the_project_are_failures(tmp_path):
    save_files(tmp_path, [ArtifactFile(path="../../evil.py", content="x"), ArtifactFile(path="src/a.py", content="y")])
    assert not (tmp_path.parent.parent / "evil.py").exists() and (tmp_path / "src/a.py").read_text() == "y"
    assert {f.path for f in load_files(tmp_path)} == {"src/a.py", "../../evil.py"}


def test_missing_toolchain_is_not_a_project_failure(tmp_path):
    with pytest.raises(GraderUnavailable):
        check_project(GOLD, P.plan, grader=tmp_path)


def test_spec_comes_from_the_plan():
    s = spec_for(P.plan)
    assert {a["collection"] for a in s["apis"]} == {"/api/invoices", "/api/clients"}
    assert set(s["pages"]) == {"/invoices", "/clients"} and s["guarded"] and s["oauth"]


def test_sandbox_denies_network_and_writes_by_default(tmp_path):
    text = sandbox_profile(tmp_path, tmp_path)
    assert "(deny network*)" in text and "(deny file-write*)" in text and f'(deny file-read* (subpath "{Path.home()}"))' in text


def test_every_group_counts_equally():
    checks = [{"group": "parse", "ok": True} for _ in range(50)] + [{"group": "api", "ok": False}]
    rep = summarize(checks)
    assert rep["rate"] == 0.5 and not rep["passed"]


def test_results_keep_their_files_out_of_the_json():
    res = Result(arm="x", project_id="p", template_id="p", files=[ArtifactFile(path="a", content="b")])
    assert "files" not in res.as_dict() and json.dumps(res.as_dict())


def _row(arm, pid, spec=0.9):
    return {"arm": arm, "project_id": pid, "template_id": pid, "gold_task_rate": spec, "gold_pass": True,
            "by_domain": {"auth": spec}, "tok_in": 1, "calls": 1, "wall_s": 1.0, "error": None}


def _check(arm, pid, rate, passed=False):
    return {"arm": arm, "project_id": pid, "rate": rate, "passed": passed, "by_group": {"api": rate, "parse": 1.0}}


def test_run_scores_replace_the_string_score_everywhere():
    rows = [_row("mgr-G4", "proj-dev-a"), _row("mgr-G1", "proj-dev-a", spec=0.1), _row("mgr-G9", "proj-dev-a")]
    merged = with_run_scores(rows, [_check("mgr-G4", "proj-dev-a", 0.1), _check("mgr-G1", "proj-dev-a", 0.9)])
    assert {r["arm"] for r in merged} == {"mgr-G4", "mgr-G1"}  # no run check: left out, not scored as zero
    assert select_best(merged)[0] == "mgr-G1"  # the string score would have picked mgr-G4


def test_prompt_level_is_picked_on_the_run_score():
    rows = [_row("mgr-G4", "p"), _row("mgr-slim3", "p"), _row("mgr-slim2", "p")]
    checks = [_check("mgr-G4", "p", 0.9), _check("mgr-slim3", "p", 0.2), _check("mgr-slim2", "p", 0.9)]
    assert pick_combo_arm(with_run_scores(rows, checks)) == "mgr-combo-s2"


def test_run_table_shows_both_scores():
    rows = [_row("mgr-G4", "p"), _row("mgr-G1", "p", spec=0.5)]
    text = run_table(rows, [_check("mgr-G4", "p", 0.5, False), _check("mgr-G1", "p", 1.0, True)])
    assert "| 1 | mgr-G1 |" in text and "1 of 1" in text and text.rstrip().endswith("|")
    assert run_table(rows, []) == "No run checks yet."


@needs_toolchain
def test_a_server_error_reports_the_real_exception_and_file():
    files = [ArtifactFile(path=f.path, content=f.content.replace("db.fetch(", "db.fetch_all("))
             if f.path.endswith("invoice_api.py") else f for f in GOLD]
    rep = check_project(files, P.plan)
    detail = next(c["detail"] for c in rep["checks"] if c["name"] == "list:/api/invoices")
    assert "fetch_all" in detail and "src/network/invoice_api.py:" in detail


@needs_toolchain
def test_a_broken_import_names_the_file_that_has_it():
    files = [ArtifactFile(path=f.path, content='import "./Missing";\n' + f.content)
             if f.path.endswith("ClientPage.tsx") else f for f in GOLD]
    rep = check_project(files, P.plan)
    assert "src/frontend/ClientPage.tsx" in next(c["detail"] for c in rep["checks"] if c["name"] == "shell_bundles")


@needs_toolchain
@pytest.mark.parametrize("style", ["with", "await"])
def test_real_asyncpg_pool_calls_are_not_marked_as_failures(style):
    """`acquire` exists on a real asyncpg pool, so code using it must pass. `fetch_all` doesn't, and must not."""
    use = {"with": "    async with db.acquire() as conn:\n        user = await conn.fetchrow(SQL, token)\n",
           "await": "    conn = await db.acquire()\n    user = await conn.fetchrow(SQL, token)\n    await db.release(conn)\n"}[style]

    def rewrite(text):
        line = '    user = await db.fetchrow("SELECT * FROM users WHERE session_token = $1", token)\n'
        assert line in text
        return 'SQL = "SELECT * FROM users WHERE session_token = $1"\n' + text.replace(line, use)

    files = [ArtifactFile(path=f.path, content=rewrite(f.content)) if f.path.endswith("session.py") else f for f in GOLD]
    assert check_project(files, P.plan)["passed"]


@needs_toolchain
def test_a_missing_code_file_counts_against_the_project():
    whole = check_project(GOLD, P.plan)
    rep = check_project([f for f in GOLD if not f.path.endswith(("oauth.py", "InvoiceForm.tsx"))], P.plan)
    failed = {c["name"]: c["detail"] for c in rep["checks"] if not c["ok"]}
    assert failed["python:src/auth/oauth.py"] == "missing" and failed["typescript:src/frontend/InvoiceForm.tsx"] == "missing"
    assert whole["passed"] and not rep["passed"] and rep["by_group"]["parse"] < 1


@needs_toolchain
def test_a_missing_table_counts_against_the_project():
    rep = check_project([f for f in GOLD if not f.path.endswith("client.sql")], P.plan)
    assert {c["name"] for c in rep["checks"] if c["group"] == "database" and not c["ok"]} == {"table:client"}


@needs_toolchain
def test_a_table_file_that_will_not_load_only_loses_one_point():
    files = [ArtifactFile(path=f.path, content="not sql") if f.path.endswith("client.sql") else f for f in GOLD]
    rep = check_project(files, P.plan)
    assert {c["name"] for c in rep["checks"] if c["group"] == "database" and not c["ok"]} == {"loads:client.sql"}


@needs_toolchain
def test_every_table_in_one_file_is_not_missing_any():
    sql = {f.path: f.content for f in GOLD if f.path.endswith(".sql")}
    together = "\n".join(sql[p] for p in sorted(sql, key=lambda p: not p.endswith("users.sql")))
    files = [f for f in GOLD if not f.path.endswith(".sql")] + [ArtifactFile(path="src/database/schema.sql", content=together)]
    assert check_project(files, P.plan)["passed"]


@needs_toolchain
def test_syntax_only_the_compiler_sees_is_a_parse_failure():
    bad = "\ndef broken(pool):\n    async with pool:\n        pass\n"
    files = [ArtifactFile(path=f.path, content=f.content + bad) if f.path.endswith("oauth.py") else f for f in GOLD]
    rep = check_project(files, P.plan)
    detail = next(c["detail"] for c in rep["checks"] if c["name"] == "python:src/auth/oauth.py")
    assert "async with" in detail


def test_missing_files_lists_only_unwritten_code_from_the_plan():
    from slm.bench.runcheck import missing_files

    assert missing_files(GOLD, P.plan) == []
    assert [c["name"] for c in missing_files([f for f in GOLD if not f.path.endswith(("guards.py", ".sql"))], P.plan)] == [
        "python:src/auth/guards.py"]
