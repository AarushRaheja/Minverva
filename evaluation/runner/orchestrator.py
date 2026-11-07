"""One trial per (agent, task, repeat, budget), resumable and strictly one at a time. Provision, run the agent, capture
what it left behind, then grade separately, after the agent is gone. Every trial is recorded, including failed ones."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import time
import tomllib
from datetime import datetime, timezone
from pathlib import Path

from evaluation.adapters.registry import CONFIGS, build_agent, load_manifest
from evaluation.benchmarks.task_registry import TaskSpec, all_tasks, select
from evaluation.core import CENSORED, ENVIRONMENT_FAILURE, AgentResult, Budget, Task
from evaluation.evaluators.correctness import GraderError, grade_project, grade_repo
from evaluation.evaluators.failures import classify, trace_metrics
from evaluation.runner import resource_monitor, workspace
from evaluation.runner.sandbox import REPO_ROOT
from evaluation.runner.trajectory_logger import load as load_trajectory

SCHEMA = 1
RESULTS = REPO_ROOT / "out/eval"
LOCAL_MODEL_ADAPTERS = ("slm", "tool_loop")
CONFIRM_TRIALS = 100  # a run larger than this, or that could cost more than CONFIRM_USD, needs an explicit yes
CONFIRM_USD = 25.0


class NotAllowed(RuntimeError):
    pass


def load_budget(name: str) -> Budget:
    d = tomllib.loads((CONFIGS / "budgets.toml").read_text())[name]
    return Budget(name, d["max_steps"], d["wall_time_seconds"], d.get("max_cost_usd"))


def load_experiment(name: str) -> dict:
    return tomllib.loads((CONFIGS / "experiments" / f"{name}.toml").read_text())


def _sha(data: bytes | str) -> str:
    return hashlib.sha256(data.encode() if isinstance(data, str) else data).hexdigest()


def _tree_hash(*paths: Path) -> str:
    h = hashlib.sha256()
    for root in paths:
        files = [root] if root.is_file() else sorted(p for p in root.rglob("*.py") if "__pycache__" not in p.parts)
        for f in files:
            h.update(f.read_bytes())
    return h.hexdigest()[:16]


def agent_commit() -> dict:
    """The commit, and a hash of uncommitted agent changes: an agent can differ from HEAD without a new commit."""
    git = lambda *a: subprocess.run(["git", *a], cwd=REPO_ROOT, capture_output=True, text=True).stdout  # noqa: E731
    diff = git("diff", "HEAD", "--", "slm")
    return {"commit": git("rev-parse", "HEAD").strip(), "dirty": bool(diff), "diff_sha256": _sha(diff)[:16] if diff else None}


def grader_version() -> str:
    base = REPO_ROOT / "evaluation/evaluators"
    return _tree_hash(base, REPO_ROOT / "slm/bench/runcheck")


def harness_version() -> str:
    return _tree_hash(REPO_ROOT / "evaluation/runner", REPO_ROOT / "evaluation/adapters", REPO_ROOT / "evaluation/core.py")


def plan_trials(exp: dict, tasks: list[TaskSpec] | None = None) -> list[dict]:
    e = exp["experiment"]
    tasks = all_tasks() if tasks is None else tasks
    chosen = select(tasks, split=e.get("split", "dev"), family=e.get("families"), ids=e.get("task_ids"),
                    task_class=e.get("task_classes"))
    budgets = e.get("budgets") or [e.get("budget", "medium")]
    return [{"agent": a, "task": t, "repeat": r, "budget": b}
            for t in chosen for a in e["agents"] for b in budgets for r in range(e.get("repeats", 1))]


def estimate(trials: list[dict], modal_rate: float = 0.0) -> dict:
    """modal_rate is the GPU's price per hour when local-model trials run on Modal, and 0 on the laptop."""
    hosted = [t for t in trials if load_manifest(t["agent"]).get("hosted")]
    worst = sum(load_budget(t["budget"]).max_cost_usd or 0 for t in hosted)
    worst += sum(load_budget(t["budget"]).wall_time_seconds / 3600 * modal_rate for t in trials
                 if load_manifest(t["agent"])["adapter"] in LOCAL_MODEL_ADAPTERS)
    hours = sum(load_budget(t["budget"]).wall_time_seconds for t in trials
                if load_manifest(t["agent"])["adapter"] in LOCAL_MODEL_ADAPTERS or load_manifest(t["agent"]).get("hosted")) / 3600
    return {"trials": len(trials), "hosted_trials": len(hosted), "worst_case_usd": worst, "worst_case_hours": hours,
            "agents": sorted({t["agent"] for t in trials}), "tasks": len({t["task"].id for t in trials})}


def guard(exp: dict, est: dict, *, yes: bool, final: bool) -> None:
    if exp["experiment"].get("split", "dev") != "dev" and not final:
        raise NotAllowed("this touches held-out tasks, which should run once at the end: pass --final if that's now")
    if (est["trials"] > CONFIRM_TRIALS or est["worst_case_usd"] > CONFIRM_USD) and not yes:
        raise NotAllowed(f"{est['trials']} trials, worst case ${est['worst_case_usd']:.2f}, {est['worst_case_hours']:.1f} h. "
                         "Pass --yes to start it.")


def trial_key(agent: str, task_id: str, repeat: int, budget: str) -> str:
    return f"{agent}|{task_id}|{repeat}|{budget}"


def load_trials(path: Path) -> list[dict]:
    """The latest record per trial, so a retried environment failure replaces the old one."""
    if not path.exists():
        return []
    latest = {}
    for line in path.read_text().splitlines():
        if line.strip():
            r = json.loads(line)
            latest[r["key"]] = r
    return list(latest.values())


def amortized_usd(manifest: dict, wall_s: float, reported: float | None) -> float | None:
    """A hosted agent's reported price, or the self-hosted machine's cost per hour. Never silently zero."""
    if reported is not None:
        return reported
    hourly = manifest.get("cost", {}).get("amortized_usd_per_hour")
    return None if hourly is None else hourly * wall_s / 3600


def run_trial(spec: TaskSpec, agent_id: str, manifest: dict, budget: Budget, repeat: int, root: Path, agent=None,
              grader=None) -> dict:
    art = root / "trials" / trial_key(agent_id, spec.id, repeat, budget.name).replace("|", "--")
    if art.exists():
        shutil.rmtree(art)
    art.mkdir(parents=True)
    started = datetime.now(timezone.utc).isoformat()
    with tempfile.TemporaryDirectory(prefix="agenteval-trial-", dir="/private/tmp") as raw:
        tmp = Path(raw).resolve()
        ws, git = workspace.prepare(spec.path if spec.family == "repo" else None, tmp)
        reference = (str(spec.path / "solution") if spec.family == "repo"
                     else str(REPO_ROOT / "out/arch/l2/files/base-opus" / spec.project_id))
        task = Task(spec.id, spec.instruction, str(ws), str(art), spec.family, spec.project_id,
                    reference if manifest["adapter"] == "oracle" else None)
        agent = agent or build_agent(manifest)
        t0 = time.monotonic()
        try:
            result: AgentResult = agent.run(task, budget)
        except Exception as e:  # noqa: BLE001 - one broken adapter must not stop the grid, and is reported as such
            result = AgentResult(spec.id, None, ENVIRONMENT_FAILURE, str(art / "trajectory.jsonl"), str(art / "metrics.json"),
                                 f"{type(e).__name__}: {e}")
        wall = time.monotonic() - t0
        patch_path = art / "patch.diff"
        patch = workspace.capture_patch(ws, git, patch_path)
        grade, grade_error = None, None
        if result.status not in CENSORED:
            try:
                grade = (grader or (grade_repo if spec.family == "repo" else _grade_project_tree))(
                    spec, patch_path if spec.family == "repo" else ws)
                grade["empty_patch"] = not patch
            except (GraderError, OSError, subprocess.SubprocessError) as e:
                grade_error = f"{type(e).__name__}: {e}"
                result.status = ENVIRONMENT_FAILURE
    metrics_path = Path(result.metrics_path)
    metrics = json.loads(metrics_path.read_text()) if metrics_path.exists() else {}
    events = load_trajectory(art / "trajectory.jsonl")
    trace = trace_metrics(events)
    failure = classify(result.status, grade, trace, has_trajectory=bool(events))
    cost = amortized_usd(manifest, wall, metrics.get("cost_usd"))
    rec = {
        "schema": SCHEMA, "key": trial_key(agent_id, spec.id, repeat, budget.name), "run_id": _sha(f"{agent_id}{spec.id}{repeat}{budget.name}{started}")[:12],
        "provenance": "harness", "agent": agent_id, "task": spec.id, "repeat": repeat, "budget": budget.name,
        "family": spec.family, "split": spec.split, "group": spec.group, "task_class": spec.task_class, "capability": spec.capability,
        "control_of": spec.control_of, "perturbation": spec.perturbation, "status": result.status, "detail": result.detail or grade_error or "",
        "resolved": bool(grade and grade.get("resolved")), "score": grade.get("score") if grade else None,
        "wall_s": wall, "cost_usd": cost, "cost_basis": "reported" if metrics.get("cost_usd") is not None else ("amortized" if cost is not None else None),
        "metrics": metrics, "trace": trace, "grade": grade, "failure": failure,
        "manifest": build_manifest(spec, agent_id, manifest, budget, started, patch, grade),
    }
    (art / "manifest.json").write_text(json.dumps(rec["manifest"], indent=1))
    (art / "grade.json").write_text(json.dumps(grade, indent=1))
    return rec


def _grade_project_tree(spec: TaskSpec, ws: Path) -> dict:
    return grade_project(spec, ws)


def build_manifest(spec: TaskSpec, agent_id: str, manifest: dict, budget: Budget, started: str, patch: bytes, grade: dict | None) -> dict:
    """Enough to reconstruct the result. A field this setup can't honor stays null instead of guessing."""
    return {"task_id": spec.id, "benchmark_name": spec.benchmark, "benchmark_version": "seed-1", "task_revision": spec.revision,
            "agent_id": agent_id, "agent_commit": agent_commit(), "agent_architecture": manifest.get("agent_architecture"),
            "model_checkpoint": manifest.get("model_id"), "model_revision": manifest.get("checkpoint_hash"),
            "system_prompt_hash": manifest.get("system_prompt_hash"), "tool_configuration": manifest.get("execution", {}),
            "inference": manifest.get("inference", {}), "seed": manifest.get("inference", {}).get("seed"),
            "seed_honored": manifest.get("seed_honored"), "known_limits": manifest.get("known_limits", []),
            "model_server": os.environ.get("SLM_OLLAMA_URL", "local ollama"), "sandbox": "macos-sandbox-exec", "container_image_digest": None, "hardware_configuration": resource_monitor.hardware(),
            "budget_configuration": {"name": budget.name, "max_steps": budget.max_steps, "wall_time_seconds": budget.wall_time_seconds, "max_cost_usd": budget.max_cost_usd},
            "start_timestamp": started, "completion_timestamp": datetime.now(timezone.utc).isoformat(),
            "final_patch_hash": _sha(patch)[:16], "grader_version": grader_version(), "harness_version": harness_version(),
            "grader_result": None if grade is None else {"resolved": grade.get("resolved"), "score": grade.get("score")}}


def stale_tasks(trials: list[dict]) -> list[str]:
    return sorted({t["task"].id for t in trials if t["task"].family == "repo"
                   and t["task"].reviewed_revision != t["task"].revision})


def uses_modal(exp: dict, backend: str | None = None) -> bool:
    return (backend or exp["experiment"].get("backend", "local")) == "modal"


def run_experiment(name: str, *, yes: bool = False, final: bool = False, say=print, retry_env: bool = True,
                   backend: str | None = None) -> Path:
    exp = load_experiment(name)
    if uses_modal(exp, backend):
        return _run_on_modal(exp, name, yes=yes, final=final, say=say, retry_env=retry_env)
    return _run(exp, yes=yes, final=final, say=say, retry_env=retry_env)


def _run_on_modal(exp: dict, name: str, *, yes: bool, final: bool, say, retry_env: bool) -> Path:
    """Every model call goes through the bridge, which checks the limit, and SLM_OLLAMA_URL points both agents at it."""
    from evaluation.runner.modal_bridge import Bridge, digest_problem, modal_forwarder
    from evaluation.runner.spend import SpendGuard, load_config

    cfg = load_config()
    spend = SpendGuard(cfg)
    guard(exp, estimate(plan_trials(exp), cfg["rate_usd_per_hour"]), yes=yes, final=final)  # before anything can wake a GPU
    why = spend.blocked()
    if why:
        raise NotAllowed(why)
    with Bridge(spend, modal_forwarder(cfg["app"])) as bridge:
        code, tags = bridge.handle("/api/tags", None)
        problem = f"Modal server: HTTP {code}: {tags[:200].decode('utf-8', 'replace')}" if code != 200 else digest_problem(tags, cfg)
        if problem:
            raise NotAllowed(problem)
        old = os.environ.get("SLM_OLLAMA_URL")
        os.environ["SLM_OLLAMA_URL"] = bridge.url
        try:
            def reserve(budget: Budget) -> str | None:  # a trial starts only if its whole time limit would fit
                return spend.blocked(budget.wall_time_seconds / 3600 * cfg["rate_usd_per_hour"])

            path = _run(exp, yes=yes, final=final, say=say, retry_env=retry_env, modal_reserve=reserve, modal_rate=cfg["rate_usd_per_hour"])
        finally:
            if old is None:
                os.environ.pop("SLM_OLLAMA_URL", None)
            else:
                os.environ["SLM_OLLAMA_URL"] = old
        say(f"Modal: {bridge.calls} calls, about ${spend.status().get('spent_usd')} of ${cfg['cap_usd']:.2f} used"
            + (f". Stopped by the limit: {bridge.tripped}" if bridge.tripped else ""))
    return path


def _run(exp: dict, *, yes: bool, final: bool, say, retry_env: bool, modal_reserve=None, modal_rate: float = 0.0) -> Path:
    trials = plan_trials(exp)
    if not trials:
        raise NotAllowed("the experiment selects no trials")
    est = estimate(trials, modal_rate)
    guard(exp, est, yes=yes, final=final)
    stale = stale_tasks(trials)
    if stale:
        raise NotAllowed(f"changed since their review, run `validate` first: {stale}")
    root = RESULTS / exp["experiment"]["id"]
    root.mkdir(parents=True, exist_ok=True)
    path = root / "trials.jsonl"
    (root / "experiment.json").write_text(json.dumps(exp, indent=1))
    done = {r["key"] for r in load_trials(path) if not (retry_env and r["status"] == ENVIRONMENT_FAILURE)}
    todo = [t for t in trials if trial_key(t["agent"], t["task"].id, t["repeat"], t["budget"]) not in done]
    say(f"{len(todo)} trials to do, {len(trials) - len(todo)} already recorded -> {path}")
    for i, t in enumerate(todo, 1):
        manifest = load_manifest(t["agent"])
        problems = resource_monitor.preflight(root, 1.0, 15, manifest["adapter"] in LOCAL_MODEL_ADAPTERS and modal_reserve is None)
        if problems:
            say(f"stopping before {t['agent']} on {t['task'].id}: {'; '.join(problems)}. Nothing was recorded for it.")
            break
        if modal_reserve is not None and manifest["adapter"] in LOCAL_MODEL_ADAPTERS:
            why = modal_reserve(load_budget(t["budget"]))
            if why:
                say(f"stopping before {t['agent']} on {t['task'].id}: {why}. Finished trials are kept, and it can resume.")
                break
        rec = run_trial(t["task"], t["agent"], manifest, load_budget(t["budget"]), t["repeat"], root)
        with path.open("a") as f:
            f.write(json.dumps(rec) + "\n")
        say(f"[{i}/{len(todo)}] {t['agent']:18} {t['task'].id:30} {rec['status']:18} resolved={int(rec['resolved'])} "
            f"score={rec['score'] if rec['score'] is None else round(rec['score'], 2)} {rec['wall_s']:.0f}s "
            f"{'' if rec['failure'] is None else rec['failure']['primary']}")
    return path
