"""Run the audit in the real Modal sandbox: the clean fixture must pass, and known-broken ones must be caught.

    uv run python scripts/check_sandbox.py

Costs CPU time only (about $0.25/hour while running), plus the first image build.
"""

from __future__ import annotations

import json
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from check_mutants import ARTIFACTS, CONTRACT, GOOD, MUTANTS, PLAN  # noqa: E402

from audit.scoring import audit_score  # noqa: E402
from frontendslm.generation import FIXED_CSS  # noqa: E402
from minerva.bridge.tests import compile_tests  # noqa: E402
from minerva.integrator.assemble import assemble  # noqa: E402
from minerva.verify.audit import make_task, stack_failures  # noqa: E402
from modal_apps.pipeline_app import ModalEngine  # noqa: E402

ENGINE = ModalEngine()
CASES = ["clean_control", "ignores_typed_title", "low_contrast", "backend_no_auth"]


def run(name: str) -> dict:
    mutate_ui, mutate_backend, catcher = MUTANTS[name]
    compiled = compile_tests(CONTRACT, f"sandbox-{name}")
    built = assemble("sandbox", PLAN, None, mutate_backend(ARTIFACTS) if mutate_backend else ARTIFACTS, CONTRACT,
                     mutate_ui(GOOD) if mutate_ui else GOOD, FIXED_CSS)
    with tempfile.TemporaryDirectory() as tmp:
        if catcher == "preflight":
            evidence = ENGINE.audit(built.files, make_task("preflight", CONTRACT, [], compiled.seed_sql, f"sandbox-{name}"), Path(tmp))
            faults = stack_failures(evidence)
            return {"name": name, "ok": bool(faults) and not evidence.get("harness_error"), "seconds": evidence["sandbox"]["seconds"],
                    "faults": faults[:3], "harness_error": evidence.get("harness_error")}
        evidence = ENGINE.audit(built.files, make_task("audit", CONTRACT, compiled.bound, compiled.seed_sql, f"sandbox-{name}"), Path(tmp))
    score = audit_score(evidence)
    ok = bool(score["audit_pass"]) if catcher is None else score.get(catcher) is False
    return {"name": name, "ok": ok and not evidence.get("harness_error"), "seconds": evidence["sandbox"]["seconds"],
            "gate_failures": [k for k, v in score.items() if v is False], "harness_error": evidence.get("harness_error"),
            "stack": stack_failures(evidence)[:3], "build_log": ((evidence.get("build") or {}).get("log") or "")[-400:] if not score["build_pass"] else "",
            "view_errors": {k: v.get("harness_error") for k, v in evidence.get("views", {}).items() if v.get("harness_error")}}


def main() -> int:
    first = run(CASES[0])  # build the image once before running in parallel
    with ThreadPoolExecutor(3) as pool:
        rows = [first, *pool.map(run, CASES[1:])]
    print(json.dumps(rows, indent=1))
    Path("results/consolidation").mkdir(parents=True, exist_ok=True)
    Path("results/consolidation/sandbox.json").write_text(json.dumps(rows, indent=1))
    print(f"{sum(r['ok'] for r in rows)}/{len(rows)} behaved as expected")
    return 0 if all(r["ok"] for r in rows) else 1


if __name__ == "__main__":
    sys.exit(main())
