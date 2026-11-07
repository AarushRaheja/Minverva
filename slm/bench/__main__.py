"""uv run python -m slm.bench sample --n 2 | build --out out/data | score ..."""

from __future__ import annotations

import json

import typer

app = typer.Typer(no_args_is_help=True, help="Project data, gold plans and metrics (WS1).")


@app.command()
def sample(n: int = 2, split: str = "train", seed: int = 0, full: bool = False):
    """Pretty-print generated projects with their gold plans."""
    from slm.bench.catalog import plan_summary
    from slm.bench.projects import generate_balanced

    for p in generate_balanced(n, split, seed):
        typer.echo(f"=== {p.id}  tasks={p.n_tasks} depth={p.depth} template={p.template_id}")
        typer.echo(p.description)
        if full:  # the brief alone is usually enough; --full prints the reference split
            typer.echo(plan_summary(p.plan))


@app.command()
def artifacts(project: int = 0, split: str = "train", domain: str = ""):
    """Show the gold artifact(s) for one generated project."""
    from slm.bench.catalog import gold_artifacts
    from slm.bench.projects import generate_balanced

    p = generate_balanced(project + 1, split, 0)[project]
    for tid, art in gold_artifacts(p.plan).items():
        task = p.plan.task(tid)
        if domain and task.domain != domain:
            continue
        typer.echo(f"=== {tid} [{task.domain}/{task.kind}] {task.target}")
        for f in art.files:
            typer.echo(f"--- {f.path}\n{f.content}")


@app.command()
def build(out: str = "out/data", scale: float = 0.05):
    """Write all data under a local directory (small scale by default)."""
    from slm.bench.build import build_all

    man = build_all(root=out, scale=scale)
    typer.echo(json.dumps({k: man[k] for k in ("projects", "domains", "manager")}, indent=1))


@app.command()
def score(traces: list[str], projects: list[str] = typer.Option(..., "--projects")):
    """Metrics table from trace JSONL files and Project JSONL files."""
    from pathlib import Path

    from slm.bench.score import score_files

    for m in score_files([Path(t) for t in traces], [Path(p) for p in projects]):
        typer.echo(f"{m.run_id} mode={m.mode} n={m.n} product={m.deliverable_ok:.3f} "
                   f"plan={m.plan_valid} tasks={m.task_acc} by_domain={m.by_domain} "
                   f"p50={m.p50_s:.2f}s p95={m.p95_s:.2f}s calls={m.calls:.1f} failures={m.failures}")


@app.command("score-plan")
def score_plan(project: str = "out/data/projects/dev.jsonl", pred: str = "pred.json"):
    """Score raw manager output(s) against the gold plan of one project file."""
    from pathlib import Path

    from slm.bench.score import load_projects
    from slm.manager.score import score_json, summarize

    proj = list(load_projects([Path(project)]).values())[0]
    preds = [ln for ln in Path(pred).read_text().splitlines() if ln.strip()]
    typer.echo(json.dumps(summarize([score_json(t, proj.plan) for t in preds]), indent=1))


if __name__ == "__main__":
    app()
