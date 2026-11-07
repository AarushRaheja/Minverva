"""uv run python -m slm.baselines show-prompt"""

import typer

from slm.baselines.monolith import SYSTEM
from slm.contracts import DOMAINS
from slm.domains import ADAPTER

app = typer.Typer(no_args_is_help=True)


@app.callback()
def _root() -> None:
    pass


@app.command("show-prompt")
def show_prompt() -> None:
    """Print the monolith system prompt and the specialist adapter names."""
    typer.echo("=== MONOLITH SYSTEM ===\n" + SYSTEM)
    typer.echo("\n=== SPECIALIST ADAPTERS ===")
    for d in DOMAINS:
        typer.echo(f"{d}: {ADAPTER[d]}")


if __name__ == "__main__":
    app()
