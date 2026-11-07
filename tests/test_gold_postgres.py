"""A generated project must work against a real Postgres, using the db.py the integrator writes.

Needs the Postgres server binaries, fastapi, httpx and asyncpg, and skips without them:

    uv run --with fastapi --with httpx --with asyncpg pytest tests/test_gold_postgres.py
"""

from __future__ import annotations

import asyncio
import shutil
import socket
import subprocess
import sys

import pytest

from slm.bench.catalog import gold_artifacts
from slm.bench.variety import generate_varied
from slm.contracts import integrate

SEED = 20261101


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("localhost", 0))
        return s.getsockname()[1]


@pytest.fixture
def postgres(tmp_path):
    if not (shutil.which("initdb") and shutil.which("pg_ctl")):
        pytest.skip("Postgres server binaries are not installed")
    data, port = tmp_path / "pg", _free_port()
    subprocess.run(["initdb", "-D", str(data), "-A", "trust", "-U", "postgres"], check=True,
                   capture_output=True)
    opts = f"-p {port} -c listen_addresses=localhost -c unix_socket_directories=''"
    subprocess.run(["pg_ctl", "-D", str(data), "-o", opts, "-l", str(tmp_path / "pg.log"), "-w", "start"],
                   check=True, capture_output=True)
    yield f"postgresql://postgres@localhost:{port}/postgres"
    subprocess.run(["pg_ctl", "-D", str(data), "-m", "fast", "stop"], check=False, capture_output=True)


def _purge_src() -> None:
    for name in [m for m in sys.modules if m == "src" or m.startswith("src.")]:
        del sys.modules[name]


async def _setup(asyncpg, dsn: str, sql_files: list[str]) -> None:
    conn = await asyncpg.connect(dsn)
    for sql in sql_files:
        await conn.execute(sql)
    await conn.execute("INSERT INTO users (email, password_hash, session_token) VALUES ('a@b.c', 'x', 'good')")
    await conn.close()


def test_generated_project_stores_and_serves_rows(postgres, tmp_path, monkeypatch):
    asyncpg = pytest.importorskip("asyncpg")
    pytest.importorskip("fastapi")
    pytest.importorskip("httpx")
    from fastapi.testclient import TestClient

    project = next(p for p in generate_varied(40, "train", SEED)
                   if sum(t.kind == "rest" for t in p.plan.tasks) == 2)
    deliverable = integrate(project.id, project.plan, gold_artifacts(project.plan))
    assert deliverable.ok, deliverable.failures
    app_dir = tmp_path / "app"
    for f in deliverable.files:
        path = app_dir / f.path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f.content)

    # In plan order, so users exists before the tables that reference it.
    schemas = [deliverable.read(f"src/database/{t.target}.sql") for t in project.plan.tasks
               if t.kind == "schema"]
    asyncio.run(_setup(asyncpg, postgres, schemas))

    monkeypatch.setenv("DATABASE_URL", postgres)
    monkeypatch.syspath_prepend(str(app_dir))
    _purge_src()
    try:
        import src.app

        entity = next(t.target for t in project.plan.tasks if t.kind == "form")
        base = next(s.split(" ", 1)[1] for s in project.plan.providers()
                    if s.startswith("endpoint:POST") and entity in s)
        with TestClient(src.app.app, raise_server_exceptions=True) as c:
            assert c.get(base).status_code == 401
            c.cookies.set("app_session", "good")
            created = c.post(base, json={"title": "first row"})
            assert created.status_code == 200, created.text
            assert created.json()["title"] == "first row" and created.json()["owner_id"] == 1
            rows = c.get(base)
            assert [r["title"] for r in rows.json()] == ["first row"]
            one = c.get(f"{base}/{created.json()['id']}")
            assert one.status_code == 200 and one.json()["title"] == "first row"
    finally:
        _purge_src()
