"""python -m slm.train build-data | backprop | estimate  (free-compute training, no Modal)."""

from __future__ import annotations

import json

import typer

from slm.train.backprop import ROLES, Recipe

app = typer.Typer(no_args_is_help=True, help="Train the specialists and the manager on any GPU (no Modal).")


@app.command("build-data")
def build_data(root: str = "out", scale: float = 1.0):
    """Write projects, manager rows and per-domain training files under <root>/data (CPU only)."""
    from slm.bench.build import build_all

    man = build_all(root=root, scale=scale)
    typer.echo(json.dumps({"domains": man["domains"], "manager": man["manager"]}, indent=1))


@app.command()
def estimate(root: str = "out"):
    """Row counts per role and optimizer steps at the default recipe. No torch needed."""
    from slm.train.backprop import load_rows, total_steps

    r = Recipe()
    for role in ROLES:
        train, ev = load_rows(root, role)
        typer.echo(f"{role:9} train={len(train):5} eval={len(ev):4} steps={total_steps(len(train), r.batch, r.epochs)}")


@app.command()
def backprop(
    role: str = typer.Option("all", help="database|auth|network|frontend|manager|specialists|all"),
    root: str = "out",
    seed: int = 0,
    epochs: int = 2,
    lr: float = 2e-4,
    rank: int = 16,
    batch: int = 8,
    micro_batch: int = 2,
    max_train: int = 0,
    gate_limit: int = 64,
    device: str = typer.Option("", help="cuda|mps|cpu (default: best available)"),
    base: str = typer.Option("", help="override the base model (e.g. a tiny model for a smoke test)"),
    run: str = "m-free",
    target: str = typer.Option("all", help="modules that get LoRA weights: all|attn"),
):
    """Train LoRA adapters with an explicit PyTorch backprop loop. Needs torch, transformers, peft."""
    from slm.train.backprop import TARGET_MODULES, train_role

    if target not in TARGET_MODULES:
        raise typer.BadParameter(f"choose from {list(TARGET_MODULES)}")

    roles = {"all": list(ROLES), "specialists": list(ROLES[:-1])}.get(role, [role])
    bad = [r for r in roles if r not in ROLES]
    if bad:
        raise typer.BadParameter(f"unknown role(s) {bad}; choose from {ROLES}")
    recipe = Recipe(r=rank, alpha=2 * rank, lr=lr, epochs=epochs, batch=batch, micro_batch=micro_batch,
                    max_train=max_train or None, gate_limit=gate_limit, seed=seed, target=target)
    results = [train_role(r, root, recipe, device=device or None, base=base or None, run=run) for r in roles]
    typer.echo(json.dumps([{k: v for k, v in x.items() if k in
                            ("role", "n_train", "final_loss", "gate_task_ok", "train_seconds", "path")}
                           for x in results], indent=1))


@app.command()
def tune(
    role: str = typer.Option("specialists", help="database|auth|network|frontend|specialists"),
    root: str = "out",
    run: str = "hp1",
    max_train: int = typer.Option(0, help="cap training rows per trial; 0 uses them all"),
    gate_limit: int = 64,
    seed: int = 0,
    device: str = typer.Option("", help="cuda|mps|cpu (default: best available)"),
    base: str = typer.Option("", help="override the base model (e.g. a tiny model for a smoke test)"),
    dry_run: bool = typer.Option(False, "--dry-run", help="list the trials and exit; needs no GPU"),
):
    """HP1: tune the specialist recipe one factor at a time, scored on dev. Resumable."""
    from slm.contracts import DOMAINS
    from slm.train.tune import plan_lines, run_tuning

    roles = list(DOMAINS) if role == "specialists" else [role]
    if any(r not in DOMAINS for r in roles):
        raise typer.BadParameter(f"choose from {list(DOMAINS)} or specialists")
    recipe = Recipe(max_train=max_train or None, gate_limit=gate_limit, seed=seed)
    if dry_run:
        typer.echo("\n".join(plan_lines(roles, root, recipe)))
        return
    if not gate_limit:
        raise typer.BadParameter("tuning needs gate scores, so --gate-limit must be above 0")
    results = run_tuning(roles, root, run, base=recipe, device=device or None, model=base or None)
    typer.echo(f"results: {results}. Now run: python -m slm.train tune-report --root {root} --run {run}")


@app.command("tune-report")
def tune_report(root: str = "out", run: str = "hp1"):
    """Per-domain trial table and the recipe to use (the default unless a trial clearly beats it)."""
    from pathlib import Path

    from slm.train.tune import _load, report

    rows = _load(Path(root) / "tune" / run / "results.jsonl")
    if not rows:
        raise typer.Exit("no tuning results yet")
    typer.echo(report(rows))


if __name__ == "__main__":
    app()
