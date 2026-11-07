"""python -m evaluation doctor | tasks | validate | plan | run | import-legacy | report | dashboard | export-harbor"""

from __future__ import annotations

import shutil
from pathlib import Path

import typer

app = typer.Typer(no_args_is_help=True, help="Evaluate coding agents with an independent grader.")


@app.command()
def doctor():
    """What this machine can run today."""
    from evaluation.adapters.model_interface import OllamaChat
    from evaluation.runner.orchestrator import RESULTS
    from evaluation.runner.resource_monitor import free_memory_pct

    disk = shutil.disk_usage(".").free / 1e9
    typer.echo(f"disk free      {disk:.1f} GB" + ("  (too little for Terminal-Bench or SWE-bench images)" if disk < 50 else ""))
    typer.echo(f"memory free    {free_memory_pct()}%")
    for tool in ("docker", "claude", "codex", "mini", "openhands", "gemini", "aider", "ruff", "semgrep", "git"):
        typer.echo(f"{tool:14} {shutil.which(tool) or 'not installed'}")
    typer.echo(f"ollama         {OllamaChat('x', timeout_s=3).version() or 'not reachable'}")
    typer.echo(f"grader tools   {'ready' if Path('out/grader/venv/bin/python').exists() else 'missing: run python -m slm.arch setup-grader'}")
    typer.echo(f"results        {RESULTS}")


@app.command()
def tasks():
    """List every task."""
    from evaluation.benchmarks.task_registry import all_tasks

    for t in all_tasks():
        reviewed = "n/a" if t.family != "repo" else ("reviewed" if t.reviewed_revision == t.revision else "NOT REVIEWED")
        typer.echo(f"{t.id:32} {t.family:14} {t.split:5} {t.task_class:15} {reviewed}")


@app.command()
def validate(check_only: bool = typer.Option(False, help="don't update the review files")):
    """Show each repository task fails on its base, passes with its reference, and doesn't flake."""
    from evaluation.benchmarks.validate import validate_all

    bad = 0
    for tid, r in validate_all(write=not check_only):
        bad += not r["ok"]
        typer.echo(f"{'ok  ' if r['ok'] else 'FAIL'} {tid:32} fail-to-pass={len(r.get('fail_to_pass', []))} pass-to-pass={len(r.get('pass_to_pass', []))} {'; '.join(r['problems'])}")
    raise typer.Exit(1 if bad else 0)


@app.command()
def plan(experiment: str):
    """How many trials an experiment needs, and the most it could cost."""
    from evaluation.runner.orchestrator import estimate, load_experiment, plan_trials, uses_modal

    exp = load_experiment(experiment)
    rate = 0.0
    if uses_modal(exp):
        from evaluation.runner.spend import load_config

        rate = load_config()["rate_usd_per_hour"]
        typer.echo(f"runs on Modal at about ${rate:.2f} an hour")
    e = estimate(plan_trials(exp), rate)
    typer.echo(f"{e['trials']} trials: {e['tasks']} tasks x agents {e['agents']}")
    typer.echo(f"hosted trials {e['hosted_trials']}, worst case ${e['worst_case_usd']:.2f}, worst case {e['worst_case_hours']:.1f} hours")


@app.command()
def run(experiment: str, yes: bool = typer.Option(False, "--yes", help="allow a large or costly run"),
        final: bool = typer.Option(False, "--final", help="allow held-out tasks"),
        backend: str = typer.Option("", help="local or modal; the default comes from the experiment")):
    """Run an experiment. Finished trials are skipped, so it can be stopped and resumed."""
    from evaluation.runner.orchestrator import NotAllowed, run_experiment

    try:
        run_experiment(experiment, yes=yes, final=final, say=typer.echo, backend=backend or None)
    except NotAllowed as e:
        typer.echo(str(e))
        raise typer.Exit(2) from e


@app.command()
def spend():
    """Modal spend against the limit. Starts nothing."""
    from evaluation.runner.spend import SpendGuard, load_config

    cfg = load_config()
    typer.echo(SpendGuard(cfg).status())


@app.command("modal-check")
def modal_check():
    """One real call through the bridge: checks the limit, the weights and that the model answers."""
    import json
    import time

    from evaluation.adapters.model_interface import OllamaChat
    from evaluation.runner.modal_bridge import Bridge, digest_problem, modal_forwarder
    from evaluation.runner.spend import SpendGuard, load_config

    cfg = load_config()
    guard = SpendGuard(cfg)
    why = guard.blocked(0.25)
    if why:
        typer.echo(why)
        raise typer.Exit(2)
    with Bridge(guard, modal_forwarder(cfg["app"])) as b:
        code, tags = b.handle("/api/tags", None)
        problem = f"HTTP {code}: {tags[:300]!r}" if code != 200 else digest_problem(tags, cfg)
        if problem:
            typer.echo(problem)
            raise typer.Exit(1)
        t0 = time.time()
        r = OllamaChat(cfg["model"], host=b.url, max_output_tokens=64).chat([{"role": "user", "content": 'Reply with the JSON {"ok": true}'}])
        typer.echo(json.dumps({"weights": "match", "reply": r["text"], "seconds": round(time.time() - t0, 1), "tok_out": r["tok_out"], "spend": guard.status()}))


@app.command("import-legacy")
def import_legacy(run: str = "l2"):
    """Bring saved out/arch results into this format. Runs no model."""
    from evaluation.benchmarks.legacy import import_runs

    typer.echo(import_runs(run))


@app.command()
def report(custom: str = "slm-mgr-G4-promptfix"):
    """Write report.md and report.json from every recorded trial on dev tasks."""
    from evaluation.analysis.comparisons import all_trials, write_report
    from evaluation.runner.orchestrator import RESULTS

    out = RESULTS / "reports"
    rep = write_report(all_trials(), out, custom)
    typer.echo((out / "report.md").read_text())
    typer.echo(f"written to {out}; {rep['n_trials']} trials")


@app.command()
def dashboard(custom: str = "slm-mgr-G4-promptfix"):
    """Write one self-contained HTML page."""
    from evaluation.analysis.comparisons import all_trials, build_report
    from evaluation.analysis.plots import write_dashboard
    from evaluation.runner.orchestrator import RESULTS

    rows = all_trials()
    path = write_dashboard(build_report(rows, custom), rows, RESULTS / "reports/dashboard.html")
    typer.echo(path)


@app.command("export-harbor")
def export_harbor(dest: str = "out/eval/harbor-tasks"):
    """Write repository tasks in Harbor's format, for running in Docker."""
    from evaluation.benchmarks.harbor_export import export_task
    from evaluation.benchmarks.task_registry import repo_tasks

    for t in repo_tasks():
        typer.echo(export_task(t, Path(dest)))


if __name__ == "__main__":
    app()
