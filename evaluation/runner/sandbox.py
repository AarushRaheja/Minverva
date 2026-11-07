"""macOS sandbox-exec profiles for the agent and the grader. Docker isolation comes through the Harbor export."""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SANDBOX_EXEC = "/usr/bin/sandbox-exec"
SECRETS = (".ssh", ".aws", ".gnupg", ".config/gh", ".netrc", ".docker", ".kube")


def _paths(rule: str, paths) -> str:
    return "\n".join(f'({rule} (subpath "{Path(p).resolve()}"))' for p in paths)


def agent_profile(workspace: Path, tmp: Path, *, network: bool = False, extra_write=(), extra_read=()) -> str:
    """The agent can write only its workspace and temp folder. It can't read this repo, which holds the hidden tests,
    saved results and other agents' outputs, or the usual secrets folders. In SBPL the last matching rule wins."""
    home = Path.home()
    return "\n".join(["(version 1)", "(allow default)",
                      *([] if network else ["(deny network*)", "(allow network* (local unix))",
                                            "(allow network* (remote unix))"]),
                      "(deny file-write*)",
                      _paths("allow file-write*", [workspace, tmp, "/dev", *extra_write]),
                      _paths("deny file-read*", [REPO_ROOT, *(home / s for s in SECRETS)]),
                      _paths("allow file-read*", [workspace, tmp, *extra_read]),
                      "(allow file-read-metadata)", ""])


def grader_profile(tmp: Path, python_home: Path | None = None) -> str:
    """Submitted code runs with no network, writes only to its temp folder, and can't read home except the runtime."""
    home = Path.home()
    keep = [tmp, home / ".local/share/uv/python", REPO_ROOT / ".venv", *([python_home] if python_home else [])]
    return "\n".join(["(version 1)", "(allow default)", "(deny network*)", "(allow network* (local unix))",
                      "(allow network* (remote unix))", "(deny file-write*)",
                      _paths("allow file-write*", [tmp, "/dev"]),
                      _paths("deny file-read*", [home]), _paths("allow file-read*", keep),
                      "(allow file-read-metadata)", ""])


def agent_env(tmp: Path, base: dict | None = None) -> dict:
    """The agent's environment. This repo's virtualenv comes off PATH, because the sandbox blocks it and a python3 that
    can't start would count against the agent. Agents get the machine's own Python, the same for all of them."""
    import os

    base = dict(os.environ if base is None else base)
    path = [x for x in base.get("PATH", "").split(":") if x and not x.startswith(str(REPO_ROOT))]
    drop = ("VIRTUAL_ENV", "PYTHONHOME", "PYTHONPATH", "UV_")
    env = {k: v for k, v in base.items() if not k.startswith(drop)}
    return {**env, "PATH": ":".join(path), "TMPDIR": str(tmp), "PYTHONDONTWRITEBYTECODE": "1"}


def wrap(profile_text: str, profile_path: Path, argv: list[str]) -> list[str]:
    profile_path.write_text(profile_text)
    return [SANDBOX_EXEC, "-f", str(profile_path), *argv]
