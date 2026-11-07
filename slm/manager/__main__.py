"""uv run python -m slm.manager show-prompt --description "<project brief>" """

import typer

from slm.manager.manager import MANAGER_SYSTEM, user_prompt

app = typer.Typer(no_args_is_help=True)


@app.callback()
def _root() -> None:
    pass


@app.command("show-prompt")
def show_prompt(
    description: str = "Build an invoice tracker with sessions, REST endpoints, a client and pages.",
) -> None:
    """Print the exact system + user prompt the manager sees."""
    typer.echo("=== SYSTEM ===\n" + MANAGER_SYSTEM + "\n=== USER ===\n" + user_prompt(description))


if __name__ == "__main__":
    app()
