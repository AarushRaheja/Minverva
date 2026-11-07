"""Launch a generated project the way a person or a preview tool would, from nothing.

    uv run python scripts/check_preview.py [project dir]

Local, so only for trusted trees: a gold fixture by default, or a project whose backend matches gold.
Copies the tree first, so the given project is left untouched.
"""

from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from http.cookiejar import CookieJar
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from minerva import vendored  # noqa: E402,F401
from frontendslm.generation import FIXED_CSS  # noqa: E402

from minerva.bridge.contract import contract_from_plan  # noqa: E402
from minerva.bridge.reference_ui import render_reference_ui  # noqa: E402
from minerva.integrator.assemble import HOST_KINDS, assemble, write_tree  # noqa: E402
from slm.bench.catalog import TRAIN_TEMPLATES, build_plan, gold_artifacts  # noqa: E402
from slm.manager.spec import without_oauth_plan  # noqa: E402


def fixture(directory: Path) -> str:
    plan = without_oauth_plan(build_plan(TRAIN_TEMPLATES[0]))
    contract = contract_from_plan(plan, "A preview self-test")
    backend = {k: v for k, v in gold_artifacts(plan).items() if plan.task(k).kind not in HOST_KINDS}
    write_tree(assemble("preview", plan, None, backend, contract, render_reference_ui(contract), FIXED_CSS).files, directory)
    return contract.entities[0].base


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class App:
    def __init__(self, command, cwd, env):
        self.port = free_port()
        self.log = tempfile.NamedTemporaryFile("w+", suffix=".log", delete=False)
        clean = {k: v for k, v in os.environ.items() if k not in ("DATABASE_URL", "APP_ENV", "VIRTUAL_ENV")}
        self.process = subprocess.Popen(command, cwd=cwd, env={**clean, "PORT": str(self.port), **env}, stdout=self.log,
                                        stderr=subprocess.STDOUT, start_new_session=True)
        self.jar = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(CookieJar()))

    def call(self, path, body=None):
        request = urllib.request.Request(f"http://127.0.0.1:{self.port}{path}", data=json.dumps(body).encode() if body else None,
                                         headers={"content-type": "application/json"} if body else {})
        try:
            with self.jar.open(request, timeout=20) as r:
                return r.status, r.read().decode()
        except urllib.error.HTTPError as e:
            return e.code, e.read().decode()

    def wait(self, seconds=420):
        end = time.time() + seconds
        while time.time() < end:
            if self.process.poll() is not None:
                return False
            try:
                self.call("/api/auth/me")
                return True
            except OSError:
                time.sleep(0.5)
        return False

    def output(self):
        self.log.flush()
        return Path(self.log.name).read_text()

    def stop(self):
        if self.process.poll() is None:
            os.killpg(self.process.pid, 15)
            try:
                self.process.wait(20)
            except subprocess.TimeoutExpired:
                os.killpg(self.process.pid, 9)


def leaked(project: Path) -> list[str]:
    """Any process still running from this project's folder, once the app has stopped."""
    time.sleep(1.5)
    found = subprocess.run(["pgrep", "-f", str(project / ".data")], capture_output=True, text=True).stdout.split()
    for pid in found:  # a failed check must not leave its own server behind
        subprocess.run(["kill", "-INT", pid], capture_output=True)
    return [f"{len(found)} database process(es) left running after stop"] if found else []


def journey(app: App, base: str, title: str) -> list[str]:
    bad = []
    status, _ = app.call("/")
    if status != 200:
        bad.append(f"GET / gave {status}")
    status, body = app.call("/api/auth/signup", {"email": "owner@example.com", "password": "password1"})
    if status != 200:
        status, body = app.call("/api/auth/login", {"email": "owner@example.com", "password": "password1"})
    if status != 200:
        return bad + [f"sign-in gave {status}: {body[:200]}"]
    status, body = app.call(base, {"title": title})
    if status != 200:
        bad.append(f"create gave {status}: {body[:200]}")
    status, body = app.call(base)
    if status != 200 or title not in body:
        bad.append(f"list gave {status}: {body[:200]}")
    return bad


def run_case(name, source, base, build_copy, check):
    with tempfile.TemporaryDirectory(prefix="pv") as tmp:
        project = Path(tmp) / "p"
        shutil.copytree(source, project, ignore=shutil.ignore_patterns(".data", ".venv", "node_modules", "dist"))
        started = time.time()
        try:
            detail = check(project, base)
        except Exception as error:  # noqa: BLE001
            detail = [f"{type(error).__name__}: {error}"]
        row = {"name": name, "ok": not detail, "seconds": round(time.time() - started, 1), "detail": detail}
        print(("OK  " if not detail else "BAD ") + f"{name:<44} {row['seconds']:>6}s {json.dumps(detail)[:400]}", flush=True)
        return row


def venv(project: Path, python: str) -> Path:
    subprocess.run(["uv", "venv", "-q", "--python", python, str(project / ".venv")], check=True)
    subprocess.run(["uv", "pip", "install", "-q", "--python", str(project / ".venv/bin/python"), "-r", str(project / "requirements.txt")], check=True)
    return project / ".venv/bin/python"


def python_path(version: str) -> str:
    return subprocess.run(["uv", "python", "find", version], check=True, capture_output=True, text=True).stdout.strip()


def case_make_preview(version: str, expect_dir: str):
    def check(project, base):
        python = python_path(version)
        app = App(["make", "preview", f"PYTHON={python}"], project, {})
        try:
            if not app.wait():
                return [f"never started: {app.output()[-600:]}"]
            bad = journey(app, base, "survives restart")
        finally:
            app.stop()
        bad += leaked(project)
        if bad:
            return bad + [app.output()[-400:]]
        if not (project / ".data" / expect_dir).exists():
            return [f"expected the {expect_dir} database, found {[p.name for p in (project / '.data').iterdir()]}"]
        again = App(["make", "preview", f"PYTHON={python}"], project, {})
        try:
            if not again.wait():
                return [f"restart failed: {again.output()[-600:]}"]
            bad = journey(again, base, "second")
        finally:
            again.stop()
        return bad + leaked(project)
    return check


def case_bare_uvicorn(project, base):
    """A preview tool that knows nothing about the Makefile: only requirements installed, nothing built."""
    python = venv(project, "3.12")
    port = free_port()
    app = App([str(python), "-m", "uvicorn", "src.app:app", "--port", str(port)], project, {})
    app.port = port
    try:
        if not app.wait():
            return [f"never started: {app.output()[-600:]}"]
        bad = journey(app, base, "bare")
    finally:
        app.stop()
    return bad + leaked(project)


def case_existing_server_missing_database(project, base):
    data = project.parent / "server"
    port = free_port()
    subprocess.run(["initdb", "-D", str(data), "-A", "trust", "-U", "postgres"], check=True, capture_output=True)
    subprocess.run(["pg_ctl", "-D", str(data), "-w", "-l", str(project.parent / "log"), "-o", f"-p {port} -c listen_addresses=127.0.0.1 -c unix_socket_directories=''", "start"],
                   check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        python = venv(project, "3.12")
        app = App([str(python), "-m", "src.main"], project, {"DATABASE_URL": f"postgresql://postgres@127.0.0.1:{port}/brand_new"})
        try:
            if not app.wait():
                return [f"never started: {app.output()[-600:]}"]
            bad = journey(app, base, "own server")
            if (project / ".data").exists():
                bad.append("started a preview database despite DATABASE_URL")
            return bad
        finally:
            app.stop()
    finally:
        subprocess.run(["pg_ctl", "-D", str(data), "-m", "fast", "stop"], capture_output=True)


def expect_refusal(env: dict, phrase: str, forbid: str = ""):
    def check(project, base):
        python = venv(project, "3.12")
        app = App([str(python), "-m", "src.main"], project, env)
        try:
            app.process.wait(40)
        except subprocess.TimeoutExpired:
            app.stop()
            return ["kept running instead of stopping"]
        output = app.output()
        bad = [] if phrase in output else [f"no clear message: {output[-500:]}"]
        if forbid and forbid in output:
            bad.append("printed the password")
        if (project / ".data").exists():
            bad.append("fell back to a preview database")
        return bad
    return check


def main() -> int:
    with tempfile.TemporaryDirectory() as holder:
        if len(sys.argv) > 1:
            source = Path(sys.argv[1]).resolve()
            base = json.loads(json.dumps(sorted((source / "src/network").glob("*_api.py"))[0].read_text().split('@router.get("')[1].split('"')[0]))
        else:
            source = Path(holder) / "fixture"
            base = fixture(source)
        cases = [
            ("make preview, Python 3.12: embedded pgserver", case_make_preview("3.12", "pgserver")),
            ("make preview, Python 3.14: system Postgres", case_make_preview("3.14", "postgres")),
            ("bare uvicorn: nothing set up or built", case_bare_uvicorn),
            ("own server, database does not exist yet", case_existing_server_missing_database),
            ("unreachable server: stops, keeps secret", expect_refusal({"DATABASE_URL": "postgresql://u:hunter2secret@127.0.0.1:1/app"}, "Could not reach the database", "hunter2secret")),
            ("production with no DATABASE_URL: refuses", expect_refusal({"APP_ENV": "production"}, "DATABASE_URL is required")),
        ]
        rows = [run_case(name, source, base, None, check) for name, check in cases]
    print(f"{sum(r['ok'] for r in rows)}/{len(rows)} behaved as expected")
    if len(sys.argv) == 1:
        Path("results/consolidation/preview.json").write_text(json.dumps(rows, indent=1))
    return 0 if all(r["ok"] for r in rows) else 1


if __name__ == "__main__":
    sys.exit(main())
