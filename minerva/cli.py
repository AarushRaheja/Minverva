"""`minerva build "<brief>"`: run the pipeline. Exit codes: 0 verified, 10 works with defects, 20 fallback UI, 30 failed,
130 stopped (Ctrl-C or SIGTERM; the run resumes with --out)."""

from __future__ import annotations

import json
import signal
from pathlib import Path

import typer

from minerva.pipeline import Options, Result, build, default_run_dir, reassemble

app = typer.Typer(no_args_is_help=True, add_completion=False)


def _engine(name: str, architect: str):
    if name == "offline":
        from minerva.offline import OfflineEngine

        return OfflineEngine()
    if name == "modal":
        import sys

        sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
        from modal_apps.pipeline_app import ModalEngine

        return ModalEngine(architect=architect)
    raise typer.BadParameter("engine must be offline or modal")


def _stop_on_sigterm() -> None:
    """Treat SIGTERM like Ctrl-C, so `app.run()` contexts close and ephemeral Modal apps stop."""

    def interrupt(signum, frame):  # noqa: ARG001
        raise KeyboardInterrupt

    signal.signal(signal.SIGTERM, interrupt)


@app.command("build")
def build_command(
    brief: str = typer.Argument(..., help="What do you want? Goes to the manager, which plans the backend"),
    look: str = typer.Option("", help="How do you want it to look? Goes only to the frontend. Default: clean product UI"),
    engine: str = typer.Option("modal", help="modal: the real models. offline: gold fixtures, for testing the plumbing"),
    architect: str = typer.Option("thinking", help="thinking or instruct"),
    max_repairs: int = typer.Option(1, min=0, max=3, help="Frontend repair rounds after the first attempt"),
    budget_usd: float = typer.Option(3.0, help="Refuse to start a stage that would exceed this estimated total"),
    out: Path | None = typer.Option(None, help="Run directory. Pass an existing one to resume it"),
    stop_after: str | None = typer.Option(None, help="plan or backend: stop early, to check a stage on its own"),
    no_fallback: bool = typer.Option(False, help="Fail rather than ship the reference UI"),
) -> None:
    run_dir = out or default_run_dir(Path("runs"), brief)
    engine_impl = _engine(engine, architect)
    # First line, flushed: a UI can follow the run directory (events.jsonl) from the start.
    typer.echo(f"run: {run_dir}")
    _stop_on_sigterm()
    try:
        result: Result = build(brief, engine_impl, run_dir, Options(
            max_repairs=max_repairs, budget_usd=budget_usd, stop_after=stop_after, allow_fallback=not no_fallback),
            look=look)
    except KeyboardInterrupt:
        typer.echo(f"stopped. Resume with: --out {run_dir}")
        raise typer.Exit(130)
    typer.echo(f"{result.status}{f' ({result.stage})' if result.stage else ''}")
    if result.detail:
        typer.echo(result.detail)
    typer.echo(f"Report: {run_dir / 'REPORT.md'}")
    if result.project:
        typer.echo(f"Project: {result.project}")
    raise typer.Exit(result.exit_code)


@app.command()
def engines(
    as_json: bool = typer.Option(False, "--json", help="Machine-readable, for UIs"),
    max_repairs: int = typer.Option(1, min=0, max=3),
    architect: str = typer.Option("thinking", help="thinking or instruct"),
) -> None:
    """List the engines: where each sends your data, what it costs, and whether it can run here. No network call."""
    from minerva.engines import as_json as engines_json

    rows = engines_json(max_repairs, architect)
    if as_json:
        typer.echo(json.dumps(rows, indent=1))
        return
    for row in rows:
        state = "ready" if row["available"] else "not ready"
        typer.echo(f"{row['name']:8} {state:9} est. ${row['estimate_total_usd']:.2f}  {row['label']}")
        typer.echo(f"{'':8} data: {row['data_goes_to']}")
        typer.echo(f"{'':8} {row['why']}")


@app.command("reassemble")
def reassemble_command(run_dir: Path) -> None:
    """Rebuild a run's project with the current integrator, from its saved stages. Free: no model runs."""
    project = reassemble(run_dir)
    typer.echo(f"Project: {project}\nNot yet through `verify`: see its REPORT.md.")


@app.command()
def status(run_dir: Path) -> None:
    """Print a run's report."""
    typer.echo((run_dir / "REPORT.md").read_text())


if __name__ == "__main__":
    app()
