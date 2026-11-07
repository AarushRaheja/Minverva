"""Disk side of `slm code`: writing a run's files safely, and re-checking them after an edit. No Textual here."""

from __future__ import annotations

import re
from pathlib import Path

from slm import contracts as C

MAX_OPEN_BYTES = 2_000_000
IGNORED_DIRS = {".git", "__pycache__", ".venv", "node_modules", ".pytest_cache", ".mypy_cache", ".ruff_cache"}
LANGUAGES = {".py": "python", ".sql": "sql", ".ts": "javascript", ".tsx": "javascript", ".js": "javascript",
             ".jsx": "javascript", ".json": "json", ".md": "markdown", ".toml": "toml", ".yaml": "yaml",
             ".yml": "yaml", ".html": "html", ".css": "css", ".sh": "bash", ".xml": "xml"}
PATH_IN_TEXT = re.compile(r"[\w./-]+\.(?:py|sql|tsx?|jsx?)\b")


def language_for(path: Path) -> str | None:
    return LANGUAGES.get(path.suffix.lower())


def safe_target(root: Path, rel: str) -> Path | None:
    """Where `rel` lands under root, or None if it would escape. Paths come from model output, so they're untrusted."""
    if not rel or "\0" in rel or Path(rel).is_absolute():
        return None
    root = root.resolve()
    target = (root / rel).resolve()
    return target if target != root and target.is_relative_to(root) else None


def write_new_files(root: Path, files: list[dict], written: set[str]) -> tuple[list[str], list[str]]:
    """Write files not yet in `written`, so a file the user has edited since is never overwritten.
    Returns (written now, rejected paths)."""
    done, rejected = [], []
    for f in files:
        rel = f["path"]
        if rel in written:
            continue
        written.add(rel)
        target = safe_target(root, rel)
        if target is None:
            rejected.append(rel)
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(f["content"])
        done.append(rel)
    return done, rejected


def plan_from_view(view: dict) -> C.ProjectPlan:
    """server.plan_view() adds display-only keys that the strict plan schema rejects."""
    return C.ProjectPlan.model_validate({k: v for k, v in view.items() if k not in ("levels", "provides")})


def recheck(project_id: str, plan: C.ProjectPlan, artifacts: dict[str, dict], root: Path) -> C.Deliverable:
    """Run the integrator over each task's files as they are on disk now."""
    current: dict[str, C.Artifact] = {}
    for task_id, art in artifacts.items():
        files = []
        for f in art.get("files", []):
            target = safe_target(root, f["path"])
            if target is not None and target.is_file():
                files.append(C.ArtifactFile(path=f["path"], content=target.read_text()))
        if files:
            current[task_id] = C.Artifact(files=files, summary=art.get("summary", ""))
    return C.integrate(project_id, plan, current)


def task_status(plan: C.ProjectPlan, task: C.Task, artifact: dict | None) -> str:
    if artifact is None:
        return "pending"
    return "ok" if C.task_ok(plan, task, C.Artifact.model_validate(artifact))[0] else "failed"


def path_in_problem(text: str, root: Path) -> Path | None:
    """The first existing file a check's detail mentions, so selecting the problem can open it."""
    for match in PATH_IN_TEXT.findall(text or ""):
        target = safe_target(root, match)
        if target is not None and target.is_file():
            return target
    return None


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:32] or "run"
