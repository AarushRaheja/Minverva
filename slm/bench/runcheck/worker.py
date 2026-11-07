"""Runs inside the sandbox with the grader's Python. Writes a JSON report; never trusts the code under test."""
import asyncio
import json
import os
import subprocess
import sys
import tempfile
import traceback
from pathlib import Path

tree, spec_path, frontend, out_path = map(Path, sys.argv[1:5])
spec = json.loads(spec_path.read_text())
checks = []


def add(group, name, ok, detail=""):
    checks.append({"group": group, "name": name, "ok": bool(ok), "detail": str(detail)[:300]})


def rejected(status):
    """Refused for being signed out: 401, 403, or the unhandled PermissionError the rules call for. A 404, 405 or
    422 means the request failed for some other reason, which says nothing about access."""
    return status in (401, 403) or status >= 500


def short(e):
    return f"{type(e).__name__}: {e}"


def where(e):
    """The generated file and line an exception came from, so a repair can go to whoever owns it."""
    frames = [f for f in traceback.extract_tb(e.__traceback__) if f.filename.startswith(str(tree))]
    return f" at {Path(frames[-1].filename).relative_to(tree).as_posix()}:{frames[-1].lineno}" if frames else ""


def finish(**extra):
    out_path.write_text(json.dumps({"checks": checks, **extra}))
    os._exit(0)  # generated code may leave threads or loops running


for f in sorted(tree.rglob("*.py")):
    rel = f.relative_to(tree).as_posix()
    if rel in ("src/app.py", "src/main.py", "src/database/db.py"):
        continue
    try:  # compile, not ast.parse, which accepts errors like `async with` outside an async function
        compile(f.read_text(), rel, "exec", dont_inherit=True)
        add("parse", f"python:{rel}", True)
    except Exception as e:  # noqa: BLE001 - generated code can break the compiler in several ways
        add("parse", f"python:{rel}", False, short(e))

try:
    import asyncpg
    import pgserver
    pgdata = tempfile.mkdtemp(prefix="pg", dir=os.environ["TMPDIR"])
    server = pgserver.get_server(pgdata, cleanup_mode="stop")
    dsn = server.get_uri()
    os.environ["SLM_PG_DSN"] = dsn
except Exception as e:  # noqa: BLE001
    finish(infrastructure_error=f"postgres would not start: {short(e)}\n{traceback.format_exc()[-400:]}")


def missing_tables(tables, broken):
    """Fail each planned table the project has no sign of. Names are free, so any other table can stand in for one,
    and a file that wouldn't load has already lost its point."""
    planned = {n for want in spec["tables"] for n in want["names"]}
    spare = len(set(tables) - planned) + broken
    for want in spec["tables"]:
        if set(tables) & set(want["names"]):
            continue
        if spare:
            spare -= 1
        else:
            add("database", f"table:{want['target']}", False, "no table for it")


async def load_schema():
    conn = await asyncpg.connect(dsn)
    pending = sorted(tree.glob("src/database/*.sql"))
    failed = {}
    while pending:  # any order, as long as references can eventually resolve
        progress = False
        for f in list(pending):
            try:
                async with conn.transaction():
                    await conn.execute(f.read_text())
                pending.remove(f)
                failed.pop(f, None)
                progress = True
                add("database", f"loads:{f.name}", True)
            except Exception as e:  # noqa: BLE001
                failed[f] = short(e)
        if not progress:
            break
    for f, why in failed.items():
        add("database", f"loads:{f.name}", False, why)
    if not (await conn.fetch("SELECT 1 FROM pg_tables WHERE schemaname = 'public'")):
        add("database", "any_table_exists", False, "no table was created")
    token, uid = "probe-token", None
    try:
        uid = await conn.fetchval(
            "INSERT INTO users (email, password_hash, session_token) VALUES ($1, $2, $3) RETURNING id", "a@b.c", "x", token)
        add("database", "users_accepts_a_session", True)
    except Exception as e:  # noqa: BLE001
        add("database", "users_accepts_a_session", False, short(e))
    tables = await conn.fetch("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
    await conn.close()
    tables = [r["tablename"] for r in tables]
    missing_tables(tables, len(failed))
    return uid, token, tables


try:
    uid, token, _tables = asyncio.run(load_schema())
except Exception as e:  # noqa: BLE001
    finish(infrastructure_error=f"could not talk to postgres: {short(e)}")

# --- the API, through the real app ---------------------------------------------------
sys.path.insert(0, str(tree))
os.chdir(tree)
app = None
try:
    from src.app import app
    add("api", "app_imports", True)
except BaseException as e:  # noqa: BLE001 - generated code can raise anything, SystemExit included
    add("api", "app_imports", False, short(e) + where(e))

if app is None:
    for a in spec["apis"]:
        for step in ("create", "list", "fetch_one"):
            add("api", f"{step}:{a['collection']}", False, "the app does not import")
    add("auth", "requires_a_session", False, "the app does not import")
else:
    from fastapi.testclient import TestClient
    with TestClient(app, raise_server_exceptions=False, cookies={"app_session": token}) as signed_in, \
            TestClient(app, raise_server_exceptions=False) as signed_out, \
            TestClient(app, cookies={"app_session": token}) as raising:
        def problem(r, method, path, **kw):
            """A 500 says nothing, so replay the failed request to get the real exception."""
            if r.status_code >= 500:
                try:
                    getattr(raising, method)(path, **kw)
                except BaseException as e:  # noqa: BLE001
                    return f"{r.status_code} {short(e)}{where(e)}"
            return f"{r.status_code} {r.text[:120]}"

        def attempt(name, group, fn):
            try:
                return fn()
            except BaseException as e:  # noqa: BLE001
                add(group, name, False, short(e))
                return None

        for a in spec["apis"]:
            base = a["collection"]
            title = f"probe {a['target']}"
            r = attempt(f"create:{base}", "api", lambda: signed_in.post(base, json={"title": title}))
            row = None
            if r is not None:
                try:
                    row = r.json() if r.status_code < 300 else None
                except ValueError:
                    row = None
                ok = isinstance(row, dict) and row.get("title") == title and "id" in row
                add("api", f"create:{base}", ok, "" if ok else problem(r, "post", base, json={"title": title}))
            r = attempt(f"list:{base}", "api", lambda: signed_in.get(base))
            if r is not None:
                try:
                    rows = r.json() if r.status_code < 300 else None
                except ValueError:
                    rows = None
                ok = isinstance(rows, list) and any(isinstance(x, dict) and x.get("title") == title for x in rows)
                add("api", f"list:{base}", ok, "" if ok else problem(r, "get", base))
            if isinstance(row, dict) and "id" in row:
                r = attempt(f"fetch_one:{base}", "api", lambda: signed_in.get(f"{base}/{row['id']}"))
                if r is not None:
                    try:
                        one = r.json() if r.status_code < 300 else None
                    except ValueError:
                        one = None
                    ok = isinstance(one, dict) and one.get("title") == title
                    add("api", f"fetch_one:{base}", ok, "" if ok else problem(r, "get", f"{base}/{row['id']}"))
            else:
                add("api", f"fetch_one:{base}", False, "nothing was created to fetch")
            r = attempt(f"create_needs_session:{base}", "auth", lambda: signed_out.post(base, json={"title": "intruder"}))
            if r is not None:
                add("auth", f"create_needs_session:{base}", rejected(r.status_code), r.status_code)
        if spec["guarded"]:
            for page in spec["pages"]:
                r = attempt(f"guard_blocks:{page}", "auth", lambda: signed_out.get(page))
                if r is not None:
                    add("auth", f"guard_blocks:{page}", rejected(r.status_code), r.status_code)
        if spec["oauth"]:
            try:
                import importlib
                mod = importlib.import_module("src.auth.oauth")
                add("auth", "oauth_module_imports", callable(getattr(mod, "oauth_start", None)))
            except BaseException as e:  # noqa: BLE001
                add("auth", "oauth_module_imports", False, short(e))

# --- the frontend ---------------------------------------------------------------------
try:
    p = subprocess.run(["node", str(frontend), str(tree), str(spec_path)], capture_output=True, text=True, timeout=90,
                       env=os.environ)
    lines = [json.loads(x) for x in p.stdout.splitlines() if x.startswith("{")]
    if not lines:
        finish(infrastructure_error=f"frontend check produced nothing: {(p.stderr or p.stdout)[-500:]}")
    for c in lines:
        add(c["group"], c["name"], c["ok"], c.get("detail", ""))
except subprocess.TimeoutExpired:
    add("frontend", "renders", False, "timed out")
finish()
