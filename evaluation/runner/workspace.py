"""A fresh workspace per trial. The baseline lives in a git dir outside the workspace, so the submitted patch is
measured from the real starting state even if the agent commits, rewrites history or deletes files."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

GIT_ENV = {"GIT_AUTHOR_NAME": "eval", "GIT_AUTHOR_EMAIL": "eval@localhost", "GIT_COMMITTER_NAME": "eval",
           "GIT_COMMITTER_EMAIL": "eval@localhost", "GIT_AUTHOR_DATE": "2026-01-01T00:00:00Z",
           "GIT_COMMITTER_DATE": "2026-01-01T00:00:00Z", "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.devnull}
EXCLUDES = "__pycache__/\n*.pyc\n.git/\n.DS_Store\n.pytest_cache/\n.ruff_cache/\n"


def _git(git_dir: Path, tree: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess:
    env = {"PATH": os.environ["PATH"], **GIT_ENV, "GIT_DIR": str(git_dir), "GIT_WORK_TREE": str(tree)}
    return subprocess.run(["git", *args], cwd=tree, env=env, capture_output=True, check=check)


def snapshot(tree: Path, git_dir: Path) -> None:
    subprocess.run(["git", "init", "-q", "--bare", str(git_dir)], check=True, capture_output=True,
                   env={"PATH": os.environ["PATH"], **GIT_ENV})
    (git_dir / "info").mkdir(exist_ok=True)
    (git_dir / "info/exclude").write_text(EXCLUDES)
    _git(git_dir, tree, "config", "core.bare", "false")
    _git(git_dir, tree, "add", "-A")
    _git(git_dir, tree, "commit", "-q", "--allow-empty", "-m", "baseline")


def materialize(task_dir: Path, dest: Path) -> None:
    """What an agent starts with: the frozen repository and the visible tests. Never tests/private or solution/."""
    shutil.copytree(task_dir / "repository", dest)
    shutil.copytree(task_dir / "tests/public", dest / "tests/public", dirs_exist_ok=True)


def prepare(task_dir: Path | None, root: Path) -> tuple[Path, Path]:
    workspace, git_dir = root / "workspace", root / "baseline.git"
    if task_dir is not None:
        materialize(task_dir, workspace)
    else:
        workspace.mkdir(parents=True)
    snapshot(workspace, git_dir)
    return workspace, git_dir


def capture_patch(workspace: Path, git_dir: Path, out: Path) -> bytes:
    _git(git_dir, workspace, "add", "-A")
    patch = _git(git_dir, workspace, "diff", "--cached", "--binary", "HEAD").stdout
    out.write_bytes(patch)
    return patch


def changed_files(patch: bytes) -> list[str]:
    names = []
    for line in patch.decode("utf-8", "replace").splitlines():
        if line.startswith("diff --git a/"):
            names.append(line.split(" b/", 1)[-1].strip('"'))
    return names


def apply_patch(tree: Path, git_dir: Path, patch: Path) -> tuple[bool, str]:
    if patch.stat().st_size == 0:
        return True, ""
    p = _git(git_dir, tree, "apply", "--whitespace=nowarn", "--binary", str(patch), check=False)
    return p.returncode == 0, p.stderr.decode("utf-8", "replace")[:500]
