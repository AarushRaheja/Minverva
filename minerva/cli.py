"""`minerva build "<brief>"`: run the pipeline. Exit codes: 0 verified, 10 works with defects, 20 fallback UI, 30 failed."""

from __future__ import annotations

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
    result: Result = build(brief, _engine(engine, architect), run_dir, Options(
        max_repairs=max_repairs, budget_usd=budget_usd, stop_after=stop_after, allow_fallback=not no_fallback), look=look)
    typer.echo(f"{result.status}{f' ({result.stage})' if result.stage else ''}")
    if result.detail:
        typer.echo(result.detail)
    typer.echo(f"Report: {run_dir / 'REPORT.md'}")
    if result.project:
        typer.echo(f"Project: {result.project}")
    raise typer.Exit(result.exit_code)


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
