"""Prove the audit can fail. Each mutant is the reference UI or gold backend with one specific defect.

    uv run python scripts/check_mutants.py [--out results/consolidation/mutants.json]

The clean control must pass. Every mutant must be caught by the gate named beside it. Local only: this runs trusted
fixtures, never model output.
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from minerva import vendored  # noqa: E402,F401
from audit.scoring import audit_score  # noqa: E402
from frontendslm.generation import FIXED_CSS  # noqa: E402

from minerva.bridge.contract import contract_from_plan  # noqa: E402
from minerva.bridge.reference_ui import render_reference_ui  # noqa: E402
from minerva.bridge.tests import compile_tests, journey_tests  # noqa: E402
from minerva.integrator.assemble import HOST_KINDS, assemble  # noqa: E402
from minerva.verify.audit import LocalAuditor, make_task, stack_failures  # noqa: E402
from slm.bench.catalog import TRAIN_TEMPLATES, build_plan, gold_artifacts  # noqa: E402
from slm.manager.spec import without_oauth_plan  # noqa: E402

PLAN = without_oauth_plan(build_plan(TRAIN_TEMPLATES[0]))
CONTRACT = contract_from_plan(PLAN, "An audit self-test")
GOOD = render_reference_ui(CONTRACT)
ARTIFACTS = {k: v for k, v in gold_artifacts(PLAN).items() if PLAN.task(k).kind not in HOST_KINDS}


def ui(old: str, new: str):
    def apply(source: str) -> str:
        assert old in source, f"mutation target missing: {old}"
        return source.replace(old, new)
    return apply


def backend(fragment: str, old: str, new: str):
    def apply(artifacts: dict) -> dict:
        out, hit = {}, False
        for key, art in artifacts.items():
            files = []
            for f in art.files:
                if fragment in f.path and old in f.content:
                    f, hit = f.model_copy(update={"content": f.content.replace(old, new)}), True
                files.append(f)
            out[key] = art.model_copy(update={"files": files})
        assert hit, f"mutation target missing: {fragment} {old}"
        return out
    return apply


# name -> (UI mutation, backend mutation, the score key or stage that must catch it)
MUTANTS = {
    "clean_control": (None, None, None),
    "local_state_only": (ui("const created = await panel.create(title.trim());",
                            "const created = { id: Date.now(), title: title.trim(), created_at: '' };"), None, "interaction_pass"),
    "hardcoded_rows": (ui("panel.list().then(", "Promise.resolve([{ id: 1, title: 'Sample', created_at: '' }, { id: 2, title: 'Sample two', created_at: '' }] as Item[]).then("), None, "interaction_pass"),
    "ignores_typed_title": (ui("panel.create(title.trim())", "panel.create('new row')"), None, "interaction_pass"),
    "no_empty_title_check": (ui('if (!title.trim()) {', 'if (false) {'), None, "interaction_pass"),
    "missing_test_id": (ui('data-testid={`${panel.key}-submit`} ', ''), None, "interaction_pass"),
    "second_section_unreachable": (ui('onClick={() => setActive(panel)}', 'onClick={() => setActive(PANELS[0])}'), None, "interaction_pass"),
    "wrong_endpoint": (ui('panel.list().then(', 'fetch("/api/nope").then((r) => r.json() as Promise<Item[]>).then('), None, "interaction_pass"),
    "no_sign_out": (ui('onClick={() => void signOut()}', 'onClick={() => void signOut}'), None, "interaction_pass"),
    "console_error": (ui('const [active, setActive] = useState(PANELS[0]);', 'const [active, setActive] = useState(PANELS[0]);\n  console.error("boom");'), None, "no_console_errors"),
    "crash_on_render": (ui('const [active, setActive] = useState(PANELS[0]);', 'const [active, setActive] = useState(PANELS[0]);\n  if (active) throw new Error("boom");'), None, "interaction_pass"),
    "low_contrast": (ui('className="py-2 break-words"', 'className="py-2 break-words text-slate-300"'), None, "no_serious_a11y"),
    "horizontal_overflow": (ui('<div className="min-h-screen bg-white text-slate-900">', '<div className="min-h-screen bg-white text-slate-900" style={{ width: 2400 }}>'), None, "no_overflow"),
    "type_error": (ui('const [active, setActive] = useState(PANELS[0]);', 'const [active, setActive] = useState(PANELS[0]);\n  const wrong: number = "text"; void wrong;'), None, "build_pass"),
    "invented_field": (ui('{row.title}</li>', '{row.title} {(row as { cost: number }).cost.toFixed(2)}</li>'), None, "build_pass"),
    "backend_crashes_on_create": (None, backend("_api.py", '"INSERT INTO', '"INSERT INTO missing_'), "preflight"),
    "backend_no_auth": (None, backend("auth/session.py", "    if not token:\n", '    token = token or "audit-session-token"\n    if not token:\n'), "preflight"),
    "verify_clean_control": (None, None, "verify_clean"),
    "no_self_setup": (None, lambda files: {**files, "src/app.py": files["src/app.py"].replace('app.add_event_handler("startup", prepare_database)\n', "")}, "verify"),
    "self_setup_skips_schema": (None, lambda files: {**files, "src/database/bootstrap.py": files["src/database/bootstrap.py"].replace("    await apply_migrations(url)\n", "")}, "verify"),
    "backend_table_missing": (None, backend(".sql", "title TEXT NOT NULL", "name TEXT"), "preflight"),
}


def run_one(item: tuple[str, tuple]) -> dict:
    name, (mutate_ui, mutate_backend, catcher) = item
    with tempfile.TemporaryDirectory() as tmp:
        compiled = compile_tests(CONTRACT, f"mutant-{name}")
        source = mutate_ui(GOOD) if mutate_ui else GOOD
        if catcher in ("verify", "verify_clean"):
            files = assemble("mutant", PLAN, None, ARTIFACTS, CONTRACT, source, FIXED_CSS).files
            task = make_task("verify", CONTRACT, journey_tests(CONTRACT), compiled.seed_sql, "verify", views=["desktop"], test_views=["desktop"])
            task["api_probes"] = {"entities": [], "guarded_pages": list(CONTRACT.guarded_pages)}
            evidence = LocalAuditor(trusted=True)(mutate_backend(files) if mutate_backend else files, task, Path(tmp))
            faults = [f for f in stack_failures(evidence) if f != "no API checks ran"]
            passed = bool(evidence.get("tests")) and all(t["passed"] for t in evidence["tests"]) and not faults
            return {"name": name, "expected_catcher": catcher, "ok": passed if catcher == "verify_clean" else not passed,
                    "detail": [f[:200] for f in faults[:2]]}
        artifacts = mutate_backend(ARTIFACTS) if mutate_backend else ARTIFACTS
        built = assemble("mutant", PLAN, None, artifacts, CONTRACT, source, FIXED_CSS)
        audit = LocalAuditor(trusted=True)
        if catcher == "preflight":
            evidence = audit(built.files, make_task("preflight", CONTRACT, [], compiled.seed_sql, f"mutant-{name}"), Path(tmp))
            faults = stack_failures(evidence)
            return {"name": name, "expected_catcher": catcher, "caught": bool(faults), "ok": bool(faults), "detail": faults[:2]}
        evidence = audit(built.files, make_task("audit", CONTRACT, compiled.bound, compiled.seed_sql, f"mutant-{name}"), Path(tmp))
        score = audit_score(evidence)
        failed = [t["id"] for t in evidence.get("tests", []) if not t["passed"]]
        if catcher is None:
            return {"name": name, "expected_catcher": None, "ok": bool(score["audit_pass"]), "score": score,
                    "stack": stack_failures(evidence), "failed_tests": failed}
        return {"name": name, "expected_catcher": catcher, "caught": not score["audit_pass"], "ok": (not score["audit_pass"]) and score.get(catcher) is False,
                "gate_failures": [k for k, v in score.items() if v is False], "failed_tests": failed[:4]}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="results/consolidation/mutants.json")
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--only", default="")
    args = parser.parse_args()
    items = [(k, v) for k, v in MUTANTS.items() if not args.only or k in args.only.split(",")]
    with ThreadPoolExecutor(args.workers) as pool:
        rows = list(pool.map(run_one, items))
    for row in rows:
        print(f"{'OK ' if row['ok'] else 'BAD'} {row['name']:<28} {json.dumps({k: v for k, v in row.items() if k in ('expected_catcher', 'gate_failures', 'failed_tests', 'detail')})[:200]}")
    if not args.only:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(json.dumps({"passed": sum(r["ok"] for r in rows), "total": len(rows), "rows": rows}, indent=1))
    print(f"{sum(r['ok'] for r in rows)}/{len(rows)} behaved as expected")
    return 0 if all(r["ok"] for r in rows) else 1


if __name__ == "__main__":
    sys.exit(main())
