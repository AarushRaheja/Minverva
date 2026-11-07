"""Does a generated project work? Parses every file, then really runs it, unlike the string checks in `integrate`.

Generated code is untrusted, so worker.py and frontend.mjs run under sandbox-exec: no network, no reads of the home
folder and writes only to a temp folder. They use their own toolchain under out/grader (`python -m slm.arch
setup-grader`): an embedded Postgres, FastAPI, esbuild and React.

The integrator's src/app.py, src/main.py and src/database/db.py are the harness's job, not the model's, so they are
always supplied here. Table names are free as long as the code agrees with itself, since only behavior is checked.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from slm.contracts import ArtifactFile, ProjectPlan, app_files
from slm.domains import canonical_path, plural
from slm.ui.workspace import safe_target

HERE = Path(__file__).parent
GROUPS = ("parse", "database", "api", "auth", "frontend")
PY_PACKAGES = ("fastapi>=0.110,<1", "httpx>=0.27,<1", "pgserver==0.1.4", "asyncpg>=0.29,<1")
NODE_PACKAGES = ("esbuild@0.25.0", "react@18.3.1", "react-dom@18.3.1")
TIMEOUT_S = 180


class GraderUnavailable(RuntimeError):
    """The toolchain or sandbox failed, not the project: record no result."""


def grader_root(root: str | Path = "out/grader") -> Path:
    return Path(root).resolve()


def setup(root: str | Path = "out/grader") -> None:
    """Install the toolchain in its own folder, so nothing touches the project's or the system's packages."""
    r = grader_root(root)
    r.mkdir(parents=True, exist_ok=True)
    py = r / "venv/bin/python"
    if not py.exists():
        subprocess.run(["uv", "venv", "--python", "3.12", str(r / "venv")], check=True)
    subprocess.run(["uv", "pip", "install", "--python", str(py), *PY_PACKAGES], check=True)
    (r / "node").mkdir(exist_ok=True)
    subprocess.run(["npm", "install", "--prefix", str(r / "node"), "--no-audit", "--no-fund", *NODE_PACKAGES], check=True)


def spec_for(plan: ProjectPlan) -> dict:
    """What a working project must do, taken from the plan's interfaces rather than from any file's text."""
    apis = []
    for t in plan.tasks:
        if t.domain == "network" and t.kind == "rest":
            paths = [s.split(" ", 1)[1] for s in t.provides() if s.startswith("endpoint:GET ")]
            collection = min(paths, key=len)
            apis.append({"target": t.target, "collection": collection, "item": collection + "/{id}"})
    pages = [s.split(":", 1)[1] for t in plan.tasks for s in t.provides() if s.startswith("route:")]
    return {"apis": apis, "pages": pages, "guarded": any(t.kind == "guards" for t in plan.tasks),
            "oauth": any(t.kind == "oauth" for t in plan.tasks),
            "tables": [{"target": t.target, "names": [t.target, plural(t.target)]} for t in plan.tasks if t.kind == "schema"]}


def missing_files(files: list[ArtifactFile], plan: ProjectPlan) -> list[dict]:
    """A failure for each planned code file that wasn't written, so leaving work out can't raise a project's score.
    Tables are checked by what the database ends up with, since their names and files are free."""
    written = {f.path for f in files}
    paths = [canonical_path(t.domain, t.kind, t.target) for t in plan.tasks if t.domain != "database"]
    return [{"group": "parse", "name": f"{'python' if p.endswith('.py') else 'typescript'}:{p}", "ok": False, "detail": "missing"}
            for p in dict.fromkeys(paths) if p not in written]


def write_tree(files: list[ArtifactFile], plan: ProjectPlan, tree: Path) -> list[str]:
    """Lay out the model's files plus the harness glue. Paths that would leave the folder are refused and returned."""
    refused = []
    for f in files:
        target = safe_target(tree, f.path)
        if target is None:
            refused.append(f.path)
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(f.content)
    for f in app_files(plan):
        if f.path in ("src/app.py", "src/main.py"):
            target = tree / f.path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(f.content)
    shutil.copy(HERE / "db_shim.py", tree / "src/database/db.py") if (tree / "src/database").is_dir() else None
    return refused


def sandbox_profile(tmp: Path, grader: Path) -> str:
    home = Path.home()
    return f"""(version 1)
(allow default)
(deny network*)
(allow network* (local unix))
(allow network* (remote unix))
(deny file-write*)
(allow file-write* (subpath "{tmp}") (subpath "/dev"))
(deny file-read* (subpath "{home}"))
(allow file-read* (subpath "{grader}") (subpath "{tmp}") (subpath "{home}/.local/share/uv/python"))
(allow file-read-metadata)
"""


def check_project(files: list[ArtifactFile], plan: ProjectPlan, grader: str | Path = "out/grader") -> dict:
    """{"checks": [{"group", "name", "ok", "detail"}], "rate", "passed", "by_group"} for one project."""
    root = grader_root(grader)
    py = root / "venv/bin/python"
    if not py.exists():
        raise GraderUnavailable("toolchain missing: run `python -m slm.arch setup-grader`")
    with tempfile.TemporaryDirectory(prefix="slm-runcheck-", dir="/private/tmp") as raw:
        tmp = Path(raw).resolve()
        tree = tmp / "project"
        tree.mkdir()
        refused = write_tree(files, plan, tree)
        (tmp / "spec.json").write_text(json.dumps(spec_for(plan)))
        profile = tmp / "sandbox.sb"
        profile.write_text(sandbox_profile(tmp, root))
        for name in ("worker.py", "frontend.mjs"):
            shutil.copy(HERE / name, tmp / name)
        env = {"PATH": "/opt/homebrew/bin:/usr/bin:/bin", "HOME": str(tmp), "TMPDIR": str(tmp), "LANG": "en_US.UTF-8",
               "NODE_PATH": str(root / "node/node_modules"), "GRADER_NODE": str(root / "node/node_modules")}
        cmd = ["/usr/bin/sandbox-exec", "-f", str(profile), str(py), "-I", str(tmp / "worker.py"), str(tree),
               str(tmp / "spec.json"), str(tmp / "frontend.mjs"), str(tmp / "out.json")]
        try:
            p = subprocess.run(cmd, capture_output=True, text=True, timeout=TIMEOUT_S, env=env, cwd=tmp)
        except subprocess.TimeoutExpired as e:
            raise GraderUnavailable(f"run check timed out after {TIMEOUT_S}s") from e
        out = tmp / "out.json"
        if not out.exists():
            raise GraderUnavailable(f"worker wrote no report (exit {p.returncode}): {(p.stderr or p.stdout)[-600:]}")
        report = json.loads(out.read_text())
    if report.get("infrastructure_error"):
        raise GraderUnavailable(report["infrastructure_error"])
    checks = report["checks"] + missing_files(files, plan) + [
        {"group": "parse", "name": f"safe_path:{x}", "ok": False, "detail": "leaves the project"} for x in refused]
    return summarize(checks)


def summarize(checks: list[dict]) -> dict:
    """Every group counts equally, so a project with many files can't outweigh whether its API works."""
    by_group = {}
    for g in GROUPS:
        mine = [c["ok"] for c in checks if c["group"] == g]
        if mine:
            by_group[g] = sum(mine) / len(mine)
    return {"checks": checks, "by_group": by_group, "rate": sum(by_group.values()) / len(by_group) if by_group else 0.0,
            "passed": bool(checks) and all(c["ok"] for c in checks)}
