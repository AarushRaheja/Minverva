"""Run the harness on an assembled project. Local runs are for trusted code only; model output goes to the sandbox."""

from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
from pathlib import Path

from minerva.bridge.contract import AppContract
from minerva.bridge.tests import SESSION_TOKEN, api_probes
from minerva.integrator.assemble import write_tree

ROOT = Path(__file__).resolve().parents[2]
HARNESS = ROOT / "harness"
FRONTEND_MODULES = ROOT / "templates" / "frontend" / "node_modules"
STACK_VENV = ROOT / ".cache" / "stack-venv"


def make_task(mode: str, contract: AppContract, tests: list[dict], seed_sql: str, salt: str,
              views: list[str] | None = None, test_views: list[str] | None = None) -> dict:
    task = {"mode": mode, "tests": tests, "seed_sql": seed_sql, "session_token": SESSION_TOKEN,
            "api_probes": api_probes(contract, salt)}
    if views:
        task["views"] = views
    if test_views:
        task["test_views"] = test_views
    return task


def stack_python(requirements: str) -> Path:
    """A venv with exactly the generated project's pinned requirements."""
    python = STACK_VENV / "bin" / "python"
    stamp = STACK_VENV / "requirements.txt"
    if python.exists() and stamp.exists() and stamp.read_text() == requirements:
        return python
    STACK_VENV.parent.mkdir(exist_ok=True)
    subprocess.run(["uv", "venv", "--allow-existing", "--python", "3.12", str(STACK_VENV)], check=True, capture_output=True)
    with tempfile.NamedTemporaryFile("w", suffix=".txt") as f:
        f.write(requirements)
        f.flush()
        subprocess.run(["uv", "pip", "install", "--quiet", "--python", str(python), "-r", f.name], check=True, capture_output=True)
    stamp.write_text(requirements)
    return python


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class LocalAuditor:
    """Runs the harness on this machine with no isolation.

    Generated code runs as you. `trusted=True` states that these files are gold fixtures or the reference UI.
    """

    def __init__(self, *, trusted: bool):
        if not trusted:
            raise ValueError("model output must be audited in the Modal sandbox, not on this machine")

    def __call__(self, files: dict[str, str], task: dict, out_dir: Path, timeout: int = 900) -> dict:
        out_dir.mkdir(parents=True, exist_ok=True)
        python = stack_python(files["requirements.txt"])
        with tempfile.TemporaryDirectory(prefix="minerva-project-") as tmp:
            project = Path(tmp) / "project"
            write_tree(files, project)
            (project / "frontend" / "node_modules").symlink_to(FRONTEND_MODULES)
            task_path = Path(tmp) / "task.json"
            task_path.write_text(json.dumps(task))
            env = {**os.environ, "AUDIT_PROJECT": str(project), "AUDIT_TASK": str(task_path), "AUDIT_OUT": str(out_dir.resolve()),
                   "AUDIT_PYTHON": str(python), "AUDIT_PORT": str(free_port())}
            done = subprocess.run(["node", str(HARNESS / "evaluate.mjs")], cwd=HARNESS, env=env, capture_output=True,
                                  text=True, timeout=timeout)
            (out_dir / "runner.log").write_text(done.stdout + "\n" + done.stderr)
            if not (out_dir / "evidence.json").exists():
                return {"harness_error": f"harness exited {done.returncode}: {done.stderr[-1500:]}", "views": {}, "tests": [],
                        "references": [], "screenshots": {}, "build": None, "api_checks": [], "stack": {}}
            return json.loads((out_dir / "evidence.json").read_text())


def stack_failures(evidence: dict) -> list[str]:
    """Backend faults only. These stop a run before any frontend is paid for, and are never blamed on the UI."""
    stack = evidence.get("stack", {})
    out = []
    if evidence.get("harness_error"):
        out.append(f"harness: {evidence['harness_error'][:300]}")
    for name in ("postgres", "migrate", "seed", "self_setup"):
        if name in stack and not stack[name].get("ok"):
            out.append(f"{name}: {stack[name].get('log', '')[-300:]}")
    if stack.get("migrate_is_repeatable") is False:
        out.append("migrate: a second run was not a no-op")
    if "api_started" in stack and not stack["api_started"]:
        out.append(f"api_start: {stack.get('api_log', '')[-300:]}")
    if not evidence.get("api_checks") and not out:
        out.append("no API checks ran")
    out += [f"{c['name']}: {c['detail']}" for c in evidence.get("api_checks", []) if not c["ok"]]
    return out


if __name__ == "__main__":
    sys.exit("use `minerva build --engine offline`")
