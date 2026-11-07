"""The gold artifacts must really compile and behave, not only contain the right tokens.

The integrator's checks are token searches, so it passed gold code that could not compile. Specialists
learn from this code, so it is held to a higher bar here. Needs fastapi and httpx, which the local env
deliberately omits, so the behavior tests skip without them:

    uv run --with fastapi --with httpx pytest tests/test_gold_runs.py
"""

from __future__ import annotations

import sys
import types

import pytest

from slm.bench.catalog import TRAIN_TEMPLATES, build_plan, gold_artifacts
from slm.bench.variety import generate_varied
from slm.contracts import integrate

SEED = 20261101


def _deliverable(plan):
    return integrate("p", plan, gold_artifacts(plan))


def _plans():
    yield from (build_plan(t) for t in TRAIN_TEMPLATES)
    yield from (p.plan for p in generate_varied(60, "test", SEED))


def test_every_gold_python_file_compiles():
    for plan in _plans():
        for f in _deliverable(plan).files:
            if f.path.endswith(".py"):
                compile(f.content, f.path, "exec")


def test_gold_typescript_has_no_template_escape_left_in_it():
    for plan in _plans():
        for f in _deliverable(plan).files:
            if f.path.endswith((".ts", ".tsx")):
                assert "import {{" not in f.content and "$" not in f.content, f.path


class _FakeDb:
    """Stands in for src.database.db.db: the one session token 'good' belongs to user 1."""

    async def fetch(self, sql, *args):
        return [{"id": 1, "title": "row"}]

    async def fetchrow(self, sql, *args):
        if "users" in sql:
            return {"id": 1, "email": "a@b.c"} if args[0] == "good" else None
        return {"id": 1, "title": "row"}


@pytest.fixture
def client(tmp_path, monkeypatch):
    pytest.importorskip("fastapi")
    pytest.importorskip("httpx")
    from fastapi.testclient import TestClient

    plan = build_plan(TRAIN_TEMPLATES[0])
    for f in _deliverable(plan).files:
        path = tmp_path / f.path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f.content)
    monkeypatch.syspath_prepend(str(tmp_path))
    for name in [m for m in sys.modules if m == "src" or m.startswith("src.")]:
        monkeypatch.delitem(sys.modules, name)
    fake = types.ModuleType("src.database.db")
    fake.db = _FakeDb()
    monkeypatch.setitem(sys.modules, "src.database.db", fake)
    import src.app

    yield TestClient(src.app.app, raise_server_exceptions=False), plan
    for name in [m for m in sys.modules if m == "src" or m.startswith("src.")]:
        sys.modules.pop(name, None)


def _api_paths(plan):
    return [s.split(" ", 1) for s in plan.providers() if s.startswith("endpoint:")]


def _call(c, symbol_method, path, **kw):
    method = symbol_method.split(":")[1].lower()
    url = path.replace("{item_id}", "1")
    return getattr(c, method)(url, **({"json": {"title": "x"}} if method == "post" else {}), **kw)


def test_every_endpoint_rejects_a_signed_out_caller_with_401(client):
    c, plan = client
    c.cookies.clear()
    for method, path in _api_paths(plan):
        assert _call(c, method, path).status_code == 401, (method, path)


def test_every_endpoint_serves_a_signed_in_caller(client):
    c, plan = client
    c.cookies.set("app_session", "good")
    for method, path in _api_paths(plan):
        assert _call(c, method, path).status_code == 200, (method, path)


def test_an_unknown_session_token_is_rejected_with_401(client):
    c, plan = client
    c.cookies.set("app_session", "stolen")
    method, path = _api_paths(plan)[0]
    assert _call(c, method, path).status_code == 401


def test_route_guard_answers_401_on_a_protected_page(client):
    c, plan = client
    c.cookies.clear()
    assert c.get(plan.routes()[0]).status_code == 401
