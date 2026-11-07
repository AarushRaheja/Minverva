import typer

from slm.baselines.__main__ import app as baselines_app
from slm.bench.__main__ import app as bench_app
from slm.contracts import DOMAINS
from slm.domains import ADAPTER
from slm.manager.__main__ import app as manager_app
from slm.train.__main__ import app as train_app

app = typer.Typer(no_args_is_help=True, help="Manager SLM + four domain specialists.")
app.add_typer(manager_app, name="manager", help="Manager SLM: prompt and plan scoring (WS4).")
app.add_typer(baselines_app, name="baselines", help="Monolith baseline (WS4).")
app.add_typer(bench_app, name="bench", help="Project data, gold plans and metrics (WS1).")
app.add_typer(train_app, name="train", help="Train adapters with a plain backprop loop on any GPU (no Modal).")


@app.callback()
def main():
    """Workstreams add their commands here (one small function each)."""


@app.command()
def domains():
    """List the four specialist domains and their adapter names."""
    typer.echo(f"{len(DOMAINS)} specialists")
    for d in DOMAINS:
        typer.echo(f"{d:9} {ADAPTER[d]}")


@app.command()
def specialists(domain: str = typer.Argument("", help="print one specialist's system prompt")):
    """Describe the four specialist SLMs (or print one system prompt)."""
    from slm.specialists import SPECIALISTS, describe, system_prompt

    if domain:
        if domain not in SPECIALISTS:
            raise typer.BadParameter(f"choose from {list(SPECIALISTS)}")
        typer.echo(system_prompt(domain))
    else:
        typer.echo(describe())


@app.command()
def run(
    project: int = 0,
    split: str = "dev",
    out: str = "out/deliverable",
    gold: bool = True,
    parallel: bool = True,
):
    """Run the whole pipeline on one generated project (oracle specialists by default) and write it."""
    from pathlib import Path

    from slm.bench.projects import generate_balanced
    from slm.llm.fake import FakeClient
    from slm.pipeline.dispatch import solve
    from slm.pipeline.oracle import OracleSpecialist
    from slm.trace import Tracer

    p = generate_balanced(project + 1, split, 0)[project]
    tracer = Tracer(run_id=f"cli-{p.id}")
    clients = {d: OracleSpecialist(tracer=tracer) for d in DOMAINS}
    plan_out, deliverable = solve(
        p, manager_client=FakeClient(tracer=tracer), specialist_clients=clients, tracer=tracer,
        gold_plan=gold, mode="gold" if gold else "specialists", parallel=parallel,
    )
    if deliverable is None:
        typer.echo("no deliverable (planning failed)")
        raise typer.Exit(1)
    root = Path(out) / p.id
    for f in deliverable.files:
        path = root / f.path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f.content)
    typer.echo(f"{p.id}: {'PASS' if deliverable.ok else 'FAIL'}  {len(deliverable.files)} files -> {root}")
    for c in deliverable.checks:
        if not c.ok:
            typer.echo(f"  FAILED {c.name} {c.detail}")
    typer.echo(f"trace: {tracer.path}")


@app.command()
def ui(host: str = "127.0.0.1", port: int = 8765):
    """Open the web workbench: write a brief, watch the plan dispatch, browse the deliverable."""
    from slm.ui.server import serve

    serve(host, port)


@app.command()
def code(
    path: str = typer.Argument("out/code", help="folder to open; runs are written inside it"),
    demo: bool = typer.Option(False, "--demo", help="start a no-model demo run right away"),
):
    """Open the VS Code-style terminal workbench."""
    from pathlib import Path

    try:
        from slm.ui.code import run_app
    except ImportError as e:
        typer.echo(f"`slm code` needs Textual: run `uv sync --group tui` ({e})")
        raise typer.Exit(1) from e
    Path(path).mkdir(parents=True, exist_ok=True)
    spec = {"name": "invoice tracker", "entities": ["invoice", "customer"], "form": "invoice", "oauth": True}
    run_app(path, {"backend": "demo", "spec": spec} if demo else None)


if __name__ == "__main__":
    app()
