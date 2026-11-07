"""Run specialist-written projects for real: parse, compile, Postgres, live API, rendered frontend.

    uv run --with fastapi --with uvicorn --with httpx --with asyncpg python -m slm.bench.specialist_eval \
        --generated out/specialist-test/pilot.json --out out/specialist-test/pilot-report.json \
        --node-modules out/test-quality/node_modules --dsn postgresql://postgres@localhost:54329

Two questions, each with a control so a defect in the check itself isn't charged to the team:
  asked  did it build what the brief asked for? (the gold plan's tests; control: gold code on the gold plan)
  own    does it pass the tests the manager wrote? (control: gold code built for the manager's plan)
"""

from __future__ import annotations

import argparse
import json
import subprocess
import tempfile
from collections import Counter, defaultdict
from pathlib import Path

from slm.bench.build import SEED
from slm.bench.catalog import gold_artifact, gold_artifacts
from slm.bench.score import gate_ok
from slm.bench.test_quality import Runner, spec_tests
from slm.bench.variety import generate_varied
from slm.contracts import Artifact, ProjectPlan, integrate, task_ok
from slm.llm.base import _strip_fences
from slm.manager.spec import ProjectSpec, gold_spec, without_oauth_plan
from slm.manager.test_compile import compile_test


def typecheck(files: dict[str, str], node_modules: str) -> list[str]:
    """TypeScript errors for a project's frontend, from a real strict `tsc` run."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        for path, content in files.items():
            if path.endswith((".ts", ".tsx")):
                p = root / path
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text(content)
        (root / "node_modules").symlink_to(node_modules)
        (root / "tsconfig.json").write_text(json.dumps({
            "compilerOptions": {"strict": True, "jsx": "react-jsx", "module": "esnext", "moduleResolution": "bundler",
                                "target": "es2020", "noEmit": True, "skipLibCheck": True, "lib": ["es2020", "dom"]},
            "include": ["src/**/*.ts", "src/**/*.tsx"]}))
        run = subprocess.run([f"{node_modules}/.bin/tsc", "-p", "."], cwd=root, capture_output=True, text=True, timeout=120)
        return [line for line in run.stdout.splitlines() if "error TS" in line]


def python_errors(files: dict[str, str]) -> list[str]:
    errors = []
    for path, content in files.items():
        if path.endswith(".py"):
            try:
                compile(content, path, "exec")
            except SyntaxError as e:
                errors.append(f"{path}: {e.msg}")
    return errors


def _files(project_id: str, plan: ProjectPlan, artifacts: dict) -> dict[str, str]:
    return {f.path: f.content for f in integrate(project_id, plan, artifacts).files}


def _tests(spec: ProjectSpec) -> list[dict]:
    rows = []
    for level, _, test in spec_tests(spec):
        check = compile_test(test)
        rows.append({"id": test.id, "level": level, "check": check})
    return rows


def _run(runner: Runner, plan: ProjectPlan, files: dict[str, str], control_plan: ProjectPlan,
         control_files: dict[str, str], tests: list[dict]) -> list[dict]:
    checks = list({t["check"]: None for t in tests if t["check"] is not None})
    got, base = runner.run_version(plan, files, checks), runner.run_version(control_plan, control_files, checks)
    return [{"id": t["id"], "level": t["level"], "kind": t["check"].kind if t["check"] else None,
             "compiled": t["check"] is not None, "passed": bool(t["check"] and got[t["check"]]),
             "control_passed": bool(t["check"] and base[t["check"]])} for t in tests]


def _totals(projects: list[dict], key: str) -> dict:
    rows = [c for p in projects for c in p.get(key, []) if c["control_passed"]]
    kinds: dict = defaultdict(lambda: [0, 0])
    for c in rows:
        kinds[c["kind"]][0] += c["passed"]
        kinds[c["kind"]][1] += 1
    return {"passed": sum(c["passed"] for c in rows), "total": len(rows),
            "excluded_control_failed": sum(not c["control_passed"] for p in projects for c in p.get(key, [])),
            "projects_all_pass": sum(bool(p.get(key)) and all(c["passed"] for c in p[key] if c["control_passed"])
                                     for p in projects),
            "by_check": {k: f"{a}/{b}" for k, (a, b) in sorted(kinds.items())}}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--generated", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--node-modules", required=True)
    ap.add_argument("--dsn", required=True)
    args = ap.parse_args()

    data = json.loads(Path(args.generated).read_text())
    gold = {p.id: p for split, n in (("dev", 100), ("test", 160)) for p in generate_varied(n, split, SEED)}
    runner = Runner(args.dsn, args.node_modules, 90)
    projects = []
    for row in data["projects"]:
        project = gold[row["project_id"]]
        gold_plan = without_oauth_plan(project.plan)
        report = {"project_id": project.id, "brief": row["brief"], "plan_error": row.get("plan_error")}
        projects.append(report)
        if "plan" not in row:
            continue
        plan = ProjectPlan.model_validate_json(row["plan"])
        pk = {(t.domain, t.kind, t.target) for t in plan.tasks}
        gk = {(t.domain, t.kind, t.target) for t in gold_plan.tasks}
        report.update(plan_exact=pk == gk, extra_tasks=sorted(map(str, pk - gk)), missing_tasks=sorted(map(str, gk - pk)))
        artifacts, tasks = {}, []
        for t in plan.tasks:
            text = next(x["text"] for x in row["tasks"] if x["id"] == t.id)
            record = {"id": t.id, "domain": t.domain, "kind": t.kind, "target": t.target, "parsed": False,
                      "gate": False, "contract": False, "identical_to_gold": False, "text_head": text[:400]}
            try:
                artifact = Artifact.model_validate_json(_strip_fences(text))
                artifacts[t.id] = artifact
                reference = gold_artifact(plan, t)
                by_path = {f.path: f.content for f in artifact.files}
                record.update(parsed=True, gate=gate_ok(t.domain, t.kind, t.target, artifact),
                              contract=task_ok(plan, t, artifact)[0],
                              identical_to_gold=all(by_path.get(f.path, "").strip() == f.content.strip()
                                                    for f in reference.files))
            except ValueError as e:
                record["error"] = str(e)[:200]
            tasks.append(record)
        deliverable = integrate(project.id, plan, artifacts)
        files = {f.path: f.content for f in deliverable.files}
        report.update(tasks=tasks, integrator_pass=deliverable.ok, integrator_failures=deliverable.failures[:8],
                      python_errors=python_errors(files), ts_errors=typecheck(files, args.node_modules), files=files)
        report["asked"] = _run(runner, plan, files, gold_plan, _files(project.id, gold_plan, gold_artifacts(gold_plan)),
                               _tests(gold_spec(gold_plan)))
        report["own"] = _run(runner, plan, files, plan, _files(project.id, plan, gold_artifacts(plan)),
                             _tests(ProjectSpec.model_validate_json(row["spec"])))
        print(project.id, "exact" if report["plan_exact"] else "plan-differs",
              "asked", sum(c["passed"] for c in report["asked"] if c["control_passed"]),
              "of", sum(c["control_passed"] for c in report["asked"]),
              "own", sum(c["passed"] for c in report["own"] if c["control_passed"]),
              "of", sum(c["control_passed"] for c in report["own"]), flush=True)

    built = [p for p in projects if "tasks" in p]
    all_tasks = [t for p in built for t in p["tasks"]]

    def rate(field: str) -> float:
        return round(sum(t[field] for t in all_tasks) / max(len(all_tasks), 1), 3)

    by_domain = {d: f"{sum(t['contract'] for t in all_tasks if t['domain'] == d)}/{sum(t['domain'] == d for t in all_tasks)}"
                 for d in sorted({t["domain"] for t in all_tasks})}
    summary = {
        "briefs": len(projects), "plans_compiled": len(built), "plans_exact": sum(p["plan_exact"] for p in built),
        "tasks": len(all_tasks), "parsed": rate("parsed"), "old_gate": rate("gate"), "contract": rate("contract"),
        "contract_by_domain": by_domain, "identical_to_gold": rate("identical_to_gold"),
        "identical_by_kind": {k: f"{sum(t['identical_to_gold'] for t in all_tasks if t['kind'] == k)}/{v}"
                              for k, v in Counter(t["kind"] for t in all_tasks).items()},
        "integrator_pass_projects": sum(p["integrator_pass"] for p in built),
        "projects_with_python_errors": sum(bool(p["python_errors"]) for p in built),
        "projects_with_ts_errors": sum(bool(p["ts_errors"]) for p in built),
        "asked": _totals(projects, "asked"), "own": _totals(projects, "own"),
        # The verdict: every check passes, and the integrator, Python and TypeScript agree.
        "projects_fully_working": sum(
            p["integrator_pass"] and not p["python_errors"] and not p["ts_errors"]
            and all(c["passed"] for c in p["asked"] if c["control_passed"]) for p in built),
        "not_exact": [{"project_id": p["project_id"], "extra": p["extra_tasks"][:4], "missing": p["missing_tasks"][:4],
                       "asked": f"{sum(c['passed'] for c in p['asked'] if c['control_passed'])}/{sum(c['control_passed'] for c in p['asked'])}"}
                      for p in built if not p["plan_exact"]],
    }
    report = {"summary": summary, "generation": {k: v for k, v in data.items() if k != "projects"}, "projects": projects}
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(report))
    print(json.dumps(summary, indent=1))


if __name__ == "__main__":
    main()
