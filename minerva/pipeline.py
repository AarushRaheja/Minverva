"""brief -> manager -> backend agents -> frontend loop -> integrator -> whole-stack check -> report.

Each stage saves its result in the run directory, so a stopped run resumes without paying for finished stages.
An Engine supplies the models and the sandbox: OfflineEngine for gold fixtures, modal_apps/pipeline_app for real ones.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from minerva import vendored  # noqa: F401 - makes frontendslm, audit and design importable
from audit.scoring import audit_score
from frontendslm.evidence import compact_evidence
from frontendslm.generation import FIXED_CSS
from frontendslm.repair import recover_repair_context

from minerva.bridge.case import build_case
from minerva.bridge.contract import AppContract, contract_from_plan, prepare_spec
from minerva.bridge.reference_ui import render_reference_ui
from minerva.bridge.tests import CompiledTests, compile_tests, journey_tests
from minerva.events import NO_EVENTS, Events
from minerva.integrator.assemble import assemble, write_tree
from minerva.verify.audit import make_task, stack_failures
from slm.contracts import Artifact
from slm.manager.spec import ProjectSpec, to_plan

VERIFIED = "verified"  # audit passed, the Critic accepted, and the sign-up journey works
FUNCTIONAL = "functional_with_defects"  # the app works, but a measured check failed or the Critic did not accept
FALLBACK = "fallback_ui"  # the Architect produced nothing that works, so the plain reference UI shipped
FAILED = "failed"
EXIT_CODES = {VERIFIED: 0, FUNCTIONAL: 10, FALLBACK: 20, FAILED: 30}


class BudgetExceeded(RuntimeError):
    pass


class Engine(Protocol):
    name: str

    def plan(self, brief: str) -> dict:
        """{'spec': raw JSON, 'seconds', 'usd'}"""

    def backend(self, spec_json: str, brief: str) -> dict:
        """{'artifacts': {task id: Artifact JSON}, 'failing': [..], 'seconds', 'usd'}"""

    def intent(self, brief: str, look: str) -> dict:
        """{'intent': dict | None, 'questions': [...], 'error': str | None, 'seconds', 'usd'}. `look` may be empty."""

    def architect(self, job: dict, run_key: str) -> dict:
        """A FrontEndSLM generation row: {'manifest': {...} | None, 'error', 'seconds', ...}"""

    def critic(self, case: dict, evidence_dir: Path, run_key: str) -> dict | None:
        """A FrontEndSLM critique row, with 'effective_verdict'."""

    def audit(self, files: dict[str, str], task: dict, out_dir: Path) -> dict:
        """Run harness/evaluate.mjs on these files. Real model output must stay in the sandbox."""

    def cost_estimate(self, stage: str) -> float:
        ...


@dataclass
class Options:
    max_repairs: int = 1
    budget_usd: float = 3.0
    stop_after: str | None = None
    allow_fallback: bool = True


@dataclass
class Ledger:
    path: Path
    budget: float
    spent: float = 0.0
    rows: list[dict] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.path.exists():
            self.rows = [json.loads(line) for line in self.path.read_text().splitlines() if line.strip()]
            self.spent = sum(r.get("usd", 0.0) for r in self.rows)

    def check(self, stage: str, estimate: float) -> None:
        if self.spent + estimate > self.budget:
            raise BudgetExceeded(f"{stage} is estimated at ${estimate:.2f}, with ${self.spent:.2f} of the "
                                 f"${self.budget:.2f} budget already spent")

    def add(self, stage: str, row: dict) -> None:
        entry = {"stage": stage, "usd": float(row.get("usd") or 0.0), "seconds": row.get("seconds")}
        self.rows.append(entry)
        self.spent += entry["usd"]
        with self.path.open("a") as f:
            f.write(json.dumps(entry) + "\n")


def slug_for(brief: str) -> str:
    words = re.findall(r"[a-z0-9]+", brief.lower())[:6]
    return "-".join(words) or "brief"


def default_run_dir(root: Path, brief: str) -> Path:
    return root / f"{time.strftime('%Y%m%d-%H%M%S')}-{slug_for(brief)}"


def _load(path: Path) -> dict | None:
    return json.loads(path.read_text()) if path.exists() else None


AUDIT_DONE = "audit-complete"  # written after an audit returns; evidence.json without it is a stopped audit's partial


def _load_audit(out_dir: Path) -> dict | None:
    """Evidence from a finished audit in out_dir, or None. A harness stopped mid-run leaves a partial evidence.json,
    which must be audited again on resume rather than scored. Runs from before the marker existed audit again too."""
    if not (out_dir / AUDIT_DONE).exists():
        return None
    return _load(out_dir / "evidence.json")


def _audit(engine: "Engine", files: dict, task: dict, out_dir: Path) -> dict:
    evidence = engine.audit(files, task, out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / AUDIT_DONE).write_text(time.strftime("%Y-%m-%dT%H:%M:%S%z"))
    return evidence


def _save(path: Path, value: dict) -> dict:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=1))
    temporary.replace(path)
    return value


def _stage(run_dir: Path, ledger: Ledger, engine: Engine, name: str, fn, events: Events = NO_EVENTS) -> dict:
    """Reuse a finished stage. Otherwise check the budget, run it, and save the result before anything else happens."""
    path = run_dir / "stages" / f"{name}.json"
    done = _load(path)
    if done is not None:
        events.cached(name)
        return done
    estimate = engine.cost_estimate(name)
    ledger.check(name, estimate)
    with events.step(name, estimate=estimate) as outcome:
        result = fn()
        _save(path, result)
        ledger.add(name, result)
        outcome.update(usd=result.get("usd"), seconds=result.get("seconds"), detail=result.get("error"))
    return result


def score_round(evidence: dict) -> dict:
    return audit_score(evidence)


def _works(score: dict) -> bool:
    """The app functions, even if an accessibility or layout check still fails."""
    return bool(score["build_pass"] and score["interaction_pass"] and score.get("no_runtime_failures", False))


@dataclass
class Result:
    status: str
    stage: str | None = None
    detail: str = ""
    run_dir: Path | None = None
    project: Path | None = None
    summary: dict = field(default_factory=dict)

    @property
    def exit_code(self) -> int:
        return EXIT_CODES[self.status]


def _has_source(generation: dict) -> bool:
    return bool(((generation.get("manifest") or {}).get("files") or {}).get("src/App.tsx"))


def _audit_detail(evidence: dict) -> str:
    """The failed gates of an audit, or the reason it could not run, for a progress event."""
    if evidence.get("harness_error"):
        return f"harness: {evidence['harness_error']}"[:300]
    build = evidence.get("build")
    if build is not None and not build.get("passed"):
        return "the build failed"
    score = score_round(evidence)
    failed = [k for k, v in score.items() if v is False and k != "audit_pass"]
    return ("failed: " + ", ".join(failed)) if failed else "passed"


def _frontend_loop(engine: Engine, run_dir: Path, ledger: Ledger, contract: AppContract, assemble_with, case_base: dict,
                   options: Options, events: Events = NO_EVENTS) -> dict:
    """Generate, assemble, audit and critique; repair from measured failures. Keeps the best round by measured results."""
    history: list[dict] = []
    best: dict | None = None
    last_source: str | None = None
    repair_context: dict | None = None
    for round_number in range(options.max_repairs + 1):
        round_dir = run_dir / "frontend" / f"round-{round_number}"
        salt = f"round-{round_number}"
        compiled: CompiledTests = compile_tests(contract, salt)
        case = {**case_base, "tests": compiled.visible}
        job = {**case, "repair_baseline": "A1", "repair_strategy": "component"}
        if repair_context:
            job["repair_context"] = repair_context
        row_path = round_dir / "generation.json"
        generation = _load(row_path)
        if generation is None:
            estimate = engine.cost_estimate("architect")
            ledger.check("architect", estimate)
            with events.step("architect", round_=round_number, estimate=estimate) as outcome:
                generation = engine.architect(job, f"{run_dir.name}/round-{round_number}")
                _save(row_path, generation)
                ledger.add("architect", generation)
                outcome.update(usd=generation.get("usd"), seconds=generation.get("seconds"),
                               ok=_has_source(generation), detail=generation.get("error"))
        else:
            events.cached("architect", round_=round_number, ok=_has_source(generation), detail=generation.get("error"))
        entry = {"round": round_number, "generation_error": generation.get("error"), "seconds": generation.get("seconds"),
                 "output_tokens": generation.get("output_tokens")}
        source = ((generation.get("manifest") or {}).get("files") or {}).get("src/App.tsx")
        if source is None:
            entry["score"] = None
            history.append(entry)
            if last_source is None:
                continue
            repair_context = {"previous_source": last_source, "evidence_recovered_from": None,
                              "generation_error": generation.get("error"), "measured_evidence": {},
                              "critic": None, "critic_validation": None, "audit_score": None,
                              "revision_number": round_number + 1}
            continue
        unchanged = source == last_source
        last_source = source
        entry["unchanged_from_previous"] = unchanged
        evidence_path = round_dir / "render" / "evidence.json"
        evidence = _load_audit(evidence_path.parent)
        cached_audit = evidence is not None
        if evidence is None:
            built = assemble_with(source)
            task = make_task("audit", contract, compiled.bound, compiled.seed_sql, salt)
            estimate = engine.cost_estimate("audit")
            ledger.check("audit", estimate)
            with events.step("audit", round_=round_number, estimate=estimate) as outcome:
                evidence = _audit(engine, built.files, task, round_dir / "render")
                ledger.add("audit", {"usd": estimate, "seconds": None})
                outcome.update(usd=estimate, ok=bool(score_round(evidence)["audit_pass"]),
                               detail=_audit_detail(evidence))
        if cached_audit:
            events.cached("audit", round_=round_number, ok=bool(score_round(evidence)["audit_pass"]),
                          detail=_audit_detail(evidence))
        score = score_round(evidence)
        entry["score"] = score
        if evidence.get("build") and not evidence["build"].get("passed"):
            entry["build_errors"] = [l for l in evidence["build"].get("log", "").splitlines() if "error" in l.lower()][:4]
        entry["failed_tests"] = sorted({t["id"] for t in evidence.get("tests", []) if not t.get("passed")})[:6]
        entry["backend_faults"] = stack_failures(evidence) if evidence.get("build") is None else []
        critique = None
        if score["audit_pass"]:
            critique_path = round_dir / "critique.json"
            critique = _load(critique_path)
            if critique is None:
                estimate = engine.cost_estimate("critic")
                ledger.check("critic", estimate)
                with events.step("critic", round_=round_number, estimate=estimate) as outcome:
                    critique = engine.critic({**case, "id": "frontend"}, round_dir / "render", f"{run_dir.name}/round-{round_number}")
                    if critique is not None:
                        _save(critique_path, critique)
                        ledger.add("critic", critique)
                    verdict = (critique or {}).get("effective_verdict")
                    # ok means the Critic gave a verdict; whether it accepted is in the detail (and decides `verified`)
                    outcome.update(usd=(critique or {}).get("usd"), ok=verdict is not None, detail=f"verdict: {verdict}")
            else:
                events.cached("critic", round_=round_number, ok=critique.get("effective_verdict") is not None,
                              detail=f"verdict: {critique.get('effective_verdict')}")
        entry["critic_verdict"] = (critique or {}).get("effective_verdict")
        history.append(entry)
        rank = (bool(score["audit_pass"]), _works(score), sum(bool(v) for v in score.values() if isinstance(v, bool)))
        if best is None or rank > best["rank"]:
            best = {"rank": rank, "round": round_number, "source": source, "score": score, "critic": critique}
        # Component repair uses only measured failures, so a Critic objection to a passing page gives it nothing to fix.
        if score["audit_pass"] or unchanged:
            break
        repair_context = {
            "previous_source": source, "evidence_recovered_from": None, "generation_error": generation.get("error"),
            "measured_evidence": compact_evidence(evidence, compiled.visible), "critic": None, "critic_validation": None,
            "audit_score": score, "revision_number": round_number + 1,
        }
    _save(run_dir / "frontend" / "history.json", {"rounds": history})
    return {"best": best, "history": history}


def build(brief: str, engine: Engine, run_dir: Path, options: Options | None = None, look: str = "") -> Result:
    """`brief` is what to build, and goes to the manager. `look` is how it should look, and goes only to the frontend."""
    options = options or Options()
    brief, look = brief.strip(), look.strip()
    if not brief:
        raise ValueError("the brief is empty")
    run_dir.mkdir(parents=True, exist_ok=True)
    meta = _load(run_dir / "run.json")
    if meta is None:
        _save(run_dir / "run.json", {"brief": brief, "look": look, "engine": engine.name, "started_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
                                     "max_repairs": options.max_repairs, "budget_usd": options.budget_usd})
    elif meta["brief"] != brief or meta.get("look", "") != look or meta["engine"] != engine.name:
        raise ValueError(f"{run_dir} belongs to another run: brief, look or engine differs")
    ledger = Ledger(run_dir / "ledger.jsonl", options.budget_usd)
    events = Events(run_dir)
    events.emit("run_start", engine=engine.name, brief=brief, look=look, resumed=meta is not None,
                budget_usd=options.budget_usd, max_repairs=options.max_repairs, spent_usd=round(ledger.spent, 3),
                pid=os.getpid())

    def finish(status: str, stage: str | None = None, detail: str = "", project: Path | None = None,
               summary: dict | None = None) -> Result:
        result = Result(status, stage, detail, run_dir, project, summary or {})
        _write_report(run_dir, brief, look, engine, result, ledger)
        events.emit("run_end", status=status, stage=stage, detail=detail[:500], usd=round(ledger.spent, 3),
                    exit_code=result.exit_code)
        return result

    def stopped(stage: str) -> bool:
        return options.stop_after == stage

    try:
        planned = _stage(run_dir, ledger, engine, "plan", lambda: engine.plan(brief), events)
        try:
            spec: ProjectSpec = prepare_spec(planned["spec"])
            plan = to_plan(spec)
            contract = contract_from_plan(plan, brief, look)
        except ValueError as error:
            return finish(FAILED, "plan", f"the manager's plan did not compile: {str(error)[:600]}")
        if stopped("plan"):
            return finish(FAILED, "stopped", "stopped after plan, as requested")

        written = _stage(run_dir, ledger, engine, "backend", lambda: engine.backend(spec.model_dump_json(), brief), events)
        artifacts = {k: Artifact.model_validate_json(v) for k, v in written["artifacts"].items()}

        def assemble_with(app_tsx: str):
            return assemble(run_dir.name, plan, spec, artifacts, contract, app_tsx, FIXED_CSS)

        with events.step("seams") as outcome:
            placeholder = assemble_with(render_reference_ui(contract))
            seam_failures = placeholder.deliverable.failures
            outcome.update(ok=not seam_failures, detail="; ".join(seam_failures[:8]))
        if seam_failures:
            _save(run_dir / "stages" / "seams.json", {"failures": seam_failures})
            return finish(FAILED, "backend", "the backend's parts do not connect: " + "; ".join(seam_failures[:8]))

        compiled = compile_tests(contract, "preflight")
        preflight_evidence = _load_audit(run_dir / "preflight")
        if preflight_evidence is None:
            with events.step("preflight") as outcome:
                preflight_evidence = _audit(engine, placeholder.files, make_task("preflight", contract, [], compiled.seed_sql,
                                                                                 "preflight"), run_dir / "preflight")
                faults = stack_failures(preflight_evidence)
                outcome.update(ok=not faults, detail="; ".join(faults[:3]))
        else:
            faults = stack_failures(preflight_evidence)
            events.cached("preflight", ok=not faults, detail="; ".join(faults[:3]) or None)
        if faults:
            return finish(FAILED, "preflight", "the generated backend does not work, so no frontend was attempted: "
                          + "; ".join(faults[:8]))
        if stopped("backend"):
            return finish(FAILED, "stopped", "stopped after backend preflight, as requested")

        intent = _stage(run_dir, ledger, engine, "intent", lambda: engine.intent(brief, look), events)
        case_base = build_case(contract, compile_tests(contract, "base"), run_dir.name, intent.get("intent"))
        loop = _frontend_loop(engine, run_dir, ledger, contract, assemble_with, case_base, options, events)
        best = loop["best"]
        status_source = "model"
        if best is None or not _works(best["score"]):
            if not options.allow_fallback:
                return finish(FAILED, "frontend", "no generated frontend worked, and the fallback UI is turned off",
                              summary={"rounds": loop["history"]})
            source, status_source = render_reference_ui(contract), "reference"
        else:
            source = best["source"]

        final = assemble_with(source)
        journey = journey_tests(contract)
        verify_task = make_task("verify", contract, journey, compile_tests(contract, "verify").seed_sql, "verify",
                                views=["desktop", "mobile"], test_views=["desktop", "mobile"])
        verify_task["api_probes"] = {"entities": [], "guarded_pages": list(contract.guarded_pages)}
        with events.step("verify") as outcome:
            verify_evidence = engine.audit(final.files, verify_task, run_dir / "verify")
            journey_ok = bool((verify_evidence.get("build") or {}).get("passed")) and bool(verify_evidence.get("tests")) \
                and all(t["passed"] for t in verify_evidence["tests"]) and not stack_failures_ignoring_probes(verify_evidence)
            outcome.update(ok=journey_ok, detail="sign-up journey " + ("passed" if journey_ok else "failed")
                           + (" on the reference UI" if status_source == "reference" else ""))

        project = run_dir / "project"
        with events.step("project"):
            shutil.rmtree(project, ignore_errors=True)
            write_tree(final.files, project)

        summary = {"frontend_source": status_source, "best_round": best["round"] if best else None,
                   "rounds": loop["history"], "journey_ok": journey_ok, "entities": [e.slug for e in contract.entities],
                   "critic": (best or {}).get("critic", {}) and best["critic"].get("effective_verdict"),
                   "intent_questions": intent.get("questions") or [], "plan_name": contract.name}
        if not journey_ok:
            failed = next((s for t in verify_evidence.get("tests", []) for s in t["steps"] if s.get("passed") is False), None)
            detail = f"the sign-up journey failed: {json.dumps(failed)[:500]}" if failed \
                else f"the sign-up journey did not run: {str(verify_evidence.get('harness_error') or verify_evidence.get('stack', {}).get('failed'))[:300]}"
            return finish(FAILED, "verify", detail, project=project, summary=summary)
        if status_source == "reference":
            return finish(FALLBACK, None, "no generated UI worked, so the plain reference UI shipped", project, summary)
        accepted = best["score"]["audit_pass"] and summary["critic"] == "accept"
        return finish(VERIFIED if accepted else FUNCTIONAL, None, "", project, summary)
    except BudgetExceeded as error:
        return finish(FAILED, "budget", str(error))
    except KeyboardInterrupt:
        events.emit("run_end", status="stopped", detail="stopped before it finished; run it again with --out to resume",
                    usd=round(ledger.spent, 3))
        raise
    except Exception as error:
        events.emit("run_end", status="error", detail=f"{type(error).__name__}: {error}"[:500], usd=round(ledger.spent, 3))
        raise


def reassemble(run_dir: Path) -> Path:
    """Rebuild project/ from a run's saved stages with the current integrator. Calls no model and runs no code.

    The new tree has not been through `verify`, and its report says so. The old tree moves to project.previous/, because
    other tools may have edited it. Only the installed .venv and the database in .data stay in place.
    """
    meta, status = _load(run_dir / "run.json"), _load(run_dir / "status.json")
    if meta is None or status is None:
        raise ValueError(f"{run_dir} is not a finished run")
    spec = prepare_spec(_load(run_dir / "stages" / "plan.json")["spec"])
    plan = to_plan(spec)
    contract = contract_from_plan(plan, meta["brief"], meta.get("look", ""))
    artifacts = {k: Artifact.model_validate_json(v) for k, v in _load(run_dir / "stages" / "backend.json")["artifacts"].items()}
    if status.get("frontend_source") == "model":
        generation = _load(run_dir / "frontend" / f"round-{status['best_round']}" / "generation.json")
        source = generation["manifest"]["files"]["src/App.tsx"]
    else:
        source = render_reference_ui(contract)
    built = assemble(run_dir.name, plan, spec, artifacts, contract, source, FIXED_CSS)
    project = run_dir / "project"
    previous = run_dir / "project.previous"
    keep = {name: project / name for name in (".venv", ".data")}
    with tempfile.TemporaryDirectory(dir=run_dir) as holding:
        for name, path in keep.items():
            if path.exists():
                shutil.move(str(path), Path(holding) / name)
        if project.exists():
            shutil.rmtree(previous, ignore_errors=True)
            shutil.rmtree(project / "frontend" / "node_modules", ignore_errors=True)
            shutil.move(str(project), previous)
        write_tree(built.files, project)
        for name in keep:
            if (Path(holding) / name).exists():
                shutil.move(str(Path(holding) / name), project / name)
    note = ("> **Re-assembled from saved stages with a newer integrator: no model ran.** The results below describe the "
            f"original run. This tree has not been through `verify`. Status of that run: `{status['status']}`.\n\n")
    report = (run_dir / "REPORT.md").read_text()
    if not report.startswith("> **Re-assembled"):
        report = note + report
        (run_dir / "REPORT.md").write_text(report)
    (project / "REPORT.md").write_text(report)
    _save(run_dir / "status.json", {**status, "verify_stale": True})
    return project


def stack_failures_ignoring_probes(evidence: dict) -> list[str]:
    return [f for f in stack_failures(evidence) if f != "no API checks ran"]


HEADLINES = {
    VERIFIED: "VERIFIED: audit passed, the Critic accepted, and the sign-up journey works.",
    FUNCTIONAL: "WORKS, WITH DEFECTS: the app functions, but a measured check failed or the Critic did not accept.",
    FALLBACK: "FALLBACK UI: no generated frontend worked, so this ships the plain reference UI. Not a model result.",
    FAILED: "FAILED",
}


def _write_report(run_dir: Path, brief: str, look: str, engine: Engine, result: Result, ledger: Ledger) -> None:
    s = result.summary
    head = HEADLINES[result.status] + (f" at stage `{result.stage}`." if result.status == FAILED else "")
    lines = [f"# {s.get('plan_name') or run_dir.name}", "", f"**{head}**", ""]
    if engine.name == "offline":
        lines += ["> **Offline run: no model was called.** A fixed template stood in for the manager and ignored the brief. "
                  "This tests the plumbing and says nothing about what the models can do.", ""]
    if result.detail:
        lines += [result.detail, ""]
    lines += ["## Brief", "", f"**What:** {brief}", "", f"**Look:** {look or '(not given: the default clean product style)'}", ""]
    if s.get("entities"):
        lines += ["## What was built", "", f"Entities in the plan: {', '.join(s['entities'])}.",
                  "Each has a table, a REST API and a section in the UI, with list and create by title. "
                  "**Compare this with the brief:** anything else it asks for was not built.", ""]
    for round_ in s.get("rounds") or []:
        if round_ is (s.get("rounds") or [None])[0]:
            lines += ["## Frontend rounds", ""]
        score = round_.get("score")
        state = "no usable source" if score is None else ("audit passed" if score.get("audit_pass") else "audit failed: " + ", ".join(
            k for k, v in score.items() if v is False))
        verdict = f"; Critic: {round_['critic_verdict']}" if round_.get("critic_verdict") else ""
        if score is not None and not score.get("build_pass", True):
            state = "the build failed"
        elif score is not None and not score.get("audit_pass"):
            state = "audit failed: " + ", ".join(k for k in ("interaction_pass", "no_serious_a11y", "no_overflow", "no_runtime_failures", "no_console_errors") if score.get(k) is False)
        lines.append(f"- Round {round_['round']}: {state}{verdict}")
        lines += [f"  - `{e[:160]}`" for e in round_.get("build_errors", [])]
        if round_.get("failed_tests"):
            lines.append(f"  - Failed tests: {', '.join(round_['failed_tests'])}")
    if s.get("rounds"):
        lines.append("")
    if "journey_ok" in s:
        lines += ["## Whole-stack journey", "", "Sign up, create a row, reload, sign out, sign back in, and find the row: "
                  + ("**passed**." if s["journey_ok"] else "**failed**."), ""]
    if s.get("intent_questions"):
        lines += ["## Unanswered design questions", "", *[f"- {q}" for q in s["intent_questions"]], ""]
    lines += ["## Not checked by anything here", "", "- Whether the design is good: nothing automated measures that.",
              "- Whether every visible control does what its label says, beyond the tested flows.",
              "- Security review of the generated code.", "",
              "## Run", "", f"- Engine: `{engine.name}`", f"- Estimated cost: ${ledger.spent:.2f}",
              "- Round-by-round evidence: `frontend/`", ""]
    (run_dir / "REPORT.md").write_text("\n".join(lines))
    _save(run_dir / "status.json", {"status": result.status, "stage": result.stage, "detail": result.detail,
                                    "usd": round(ledger.spent, 3), **{k: v for k, v in s.items() if k != "rounds"}})
    if result.project is not None:
        shutil.copy(run_dir / "REPORT.md", result.project / "REPORT.md")
