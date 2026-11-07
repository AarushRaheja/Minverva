"""Files the integrator writes itself, so that the specialists' output becomes a project that runs."""

from __future__ import annotations

ACCOUNTS = '''"""Email and password accounts. Written by the integrator; see README.md before deploying."""
import hashlib
import hmac
import os
import secrets

from fastapi import APIRouter, HTTPException, Request, Response

from src.database.db import db

COOKIE = "app_session"
router = APIRouter(prefix="/api/auth", tags=["auth"])


def _hash(password: str, salt: bytes | None = None) -> str:
    salt = salt or os.urandom(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=2**14, r=8, p=1)
    return f"{salt.hex()}${digest.hex()}"


def _verify(password: str, stored: str) -> bool:
    salt, _, _digest = stored.partition("$")
    try:
        return hmac.compare_digest(_hash(password, bytes.fromhex(salt)), stored)
    except ValueError:
        return False


def _credentials(payload: dict) -> tuple[str, str]:
    email, password = payload.get("email"), payload.get("password")
    if not isinstance(email, str) or "@" not in email or not isinstance(password, str) or len(password) < 8:
        raise HTTPException(status_code=400, detail="Enter an email and a password of at least 8 characters")
    return email.strip().lower(), password


async def _start_session(response: Response, user_id: int) -> None:
    token = secrets.token_urlsafe(32)
    await db.fetchrow("UPDATE users SET session_token = $1 WHERE id = $2 RETURNING id", token, user_id)
    secure = os.environ.get("COOKIE_SECURE", "0") == "1"
    response.set_cookie(COOKIE, token, httponly=True, samesite="lax", secure=secure, path="/")


@router.post("/signup")
async def signup(payload: dict, response: Response):
    email, password = _credentials(payload)
    if await db.fetchrow("SELECT id FROM users WHERE email = $1", email):
        raise HTTPException(status_code=409, detail="That email already has an account")
    user = await db.fetchrow(
        "INSERT INTO users (email, password_hash) VALUES ($1, $2) RETURNING id, email", email, _hash(password))
    await _start_session(response, user["id"])
    return {"id": user["id"], "email": user["email"]}


@router.post("/login")
async def login(payload: dict, response: Response):
    email, password = _credentials(payload)
    user = await db.fetchrow("SELECT id, email, password_hash FROM users WHERE email = $1", email)
    if user is None or not _verify(password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Wrong email or password")
    await _start_session(response, user["id"])
    return {"id": user["id"], "email": user["email"]}


@router.post("/logout")
async def logout(request: Request, response: Response):
    token = request.cookies.get(COOKIE)
    if token:
        await db.fetchrow("UPDATE users SET session_token = NULL WHERE session_token = $1 RETURNING id", token)
    response.delete_cookie(COOKIE, path="/")
    return {"ok": True}


@router.get("/me")
async def me(request: Request):
    token = request.cookies.get(COOKIE)
    user = await db.fetchrow("SELECT id, email FROM users WHERE session_token = $1", token) if token else None
    return {"user": user}
'''

SPA = r'''"""Serve the built frontend, and build it on first start if needed. Written by the integrator."""
import asyncio
import logging
import os
import shutil
import subprocess
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse

FRONTEND = Path(__file__).resolve().parent.parent / "frontend"
DIST = (FRONTEND / "dist").resolve()
log = logging.getLogger("uvicorn.error")


def _build() -> None:
    if (DIST / "index.html").is_file() or os.environ.get("APP_ENV") == "production" \
            or os.environ.get("AUTO_BUILD_FRONTEND") == "0":
        return
    npm = shutil.which("npm")
    if npm is None:
        log.warning("The frontend is not built and npm was not found. Install Node 22, then run `make preview`.")
        return
    commands = [[npm, "run", "build"]]
    if not (FRONTEND / "node_modules").exists():
        commands.insert(0, [npm, "ci", "--no-audit", "--no-fund"])
    log.info("Building the frontend for the first time; this can take a minute.")
    for command in commands:
        done = subprocess.run(command, cwd=FRONTEND, capture_output=True, text=True)
        if done.returncode != 0:
            log.warning("Could not build the frontend:\n%s", (done.stdout + done.stderr)[-2000:])
            return


async def build_frontend() -> None:
    await asyncio.to_thread(_build)


def mount_spa(app: FastAPI) -> None:
    @app.get("/{path:path}", include_in_schema=False)
    async def spa(path: str):
        if path == "api" or path.startswith("api/"):
            raise HTTPException(status_code=404, detail="Not found")
        target = (DIST / path).resolve()
        if path and target.is_file() and target.is_relative_to(DIST):
            return FileResponse(target)
        index = DIST / "index.html"
        if not index.is_file():
            raise HTTPException(status_code=503, detail="The frontend is not built: run `make preview`")
        return FileResponse(index)
'''

MIGRATE = r'''"""Apply src/database/*.sql in order, users first. Safe to run twice. Written by the integrator."""
import asyncio
from pathlib import Path

import asyncpg

SCHEMAS = Path(__file__).resolve().parent
LOCK = 727001  # two servers starting together must not apply the same file twice


async def apply_migrations(url: str) -> None:
    conn = await asyncpg.connect(url)
    try:
        await conn.execute("SELECT pg_advisory_lock($1)", LOCK)
        await conn.execute("CREATE TABLE IF NOT EXISTS schema_migrations (name TEXT PRIMARY KEY)")
        done = {row["name"] for row in await conn.fetch("SELECT name FROM schema_migrations")}
        for path in sorted(SCHEMAS.glob("*.sql"), key=lambda p: (p.stem != "users", p.name)):
            if path.name in done:
                continue
            async with conn.transaction():
                await conn.execute(path.read_text())
                await conn.execute("INSERT INTO schema_migrations (name) VALUES ($1)", path.name)
            print(f"applied {path.name}", flush=True)
    finally:
        await conn.close()


async def main() -> None:
    from src.database.bootstrap import prepare

    await prepare()


if __name__ == "__main__":
    asyncio.run(main())
'''

BOOTSTRAP = r'''"""Get the database ready when the app starts, however it was launched. Written by the integrator.

DATABASE_URL set:   use that server, creating the database if it is missing. If it can't be reached, stop.
DATABASE_URL unset: start a private Postgres in .data/, for previews. Refused when APP_ENV=production.
Either way, the schema files are then applied.
"""
import asyncio
import atexit
import logging
import os
import re
import shutil
import socket
import subprocess
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

import asyncpg

from src.database import db as database
from src.database.migrate import apply_migrations

DATA = Path(__file__).resolve().parents[2] / ".data"
log = logging.getLogger("uvicorn.error")
_server = None  # keeps pgserver's handle alive for as long as the app runs
_stop_command: list[str] | None = None


def _pgserver_url() -> str | None:
    global _server
    try:
        import pgserver
    except ImportError:  # it has no builds for Python 3.13 or later
        return None
    directory = DATA / "pgserver"
    directory.mkdir(parents=True, exist_ok=True)
    _server = pgserver.get_server(directory, cleanup_mode="stop")
    return _server.get_uri()


def _system_url() -> str | None:
    initdb, pg_ctl = shutil.which("initdb"), shutil.which("pg_ctl")
    if not initdb or not pg_ctl:
        return None
    directory = DATA / "postgres"
    port_file = DATA / "postgres.port"
    quiet = {"stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL}
    if not (directory / "PG_VERSION").exists():
        directory.mkdir(parents=True, exist_ok=True)
        subprocess.run([initdb, "-D", str(directory), "-A", "trust", "-U", "postgres", "-E", "UTF8"], check=True, **quiet)
    global _stop_command
    _stop_command = [pg_ctl, "-D", str(directory), "-m", "fast", "stop"]
    if subprocess.run([pg_ctl, "-D", str(directory), "status"], **quiet).returncode == 0 and port_file.exists():
        port = int(port_file.read_text())  # left running by an earlier start that was killed
    else:
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            port = s.getsockname()[1]
        options = f"-p {port} -c listen_addresses=127.0.0.1 -c unix_socket_directories=''"
        subprocess.run([pg_ctl, "-D", str(directory), "-w", "-l", str(DATA / "postgres.log"), "-o", options, "start"],
                       check=True, **quiet)
        port_file.write_text(str(port))
    return f"postgresql://postgres@127.0.0.1:{port}/postgres"


def _preview_url() -> str:
    if os.environ.get("APP_ENV") == "production":
        raise RuntimeError("DATABASE_URL is required when APP_ENV=production")
    url = _pgserver_url() or _system_url()
    if url is None:
        raise RuntimeError("No database found. Set DATABASE_URL, or use Python 3.11 or 3.12, "
                           "or install Postgres so that initdb and pg_ctl are on your PATH.")
    log.warning("DATABASE_URL is not set: using a private preview database in .data/. Do not use this in production.")
    return url


def _where(url: str) -> str:
    return urlsplit(url).hostname or "a local socket"  # never the URL itself: it can hold a password


async def _create_if_missing(url: str) -> None:
    try:
        await (await asyncpg.connect(url)).close()
        return
    except asyncpg.InvalidCatalogNameError:
        pass
    except (OSError, asyncpg.PostgresError, asyncpg.InterfaceError) as error:
        raise RuntimeError(f"Could not reach the database at {_where(url)} ({type(error).__name__}). Check DATABASE_URL.") from None
    parts = urlsplit(url)
    name = parts.path.lstrip("/")
    if not re.fullmatch(r"[A-Za-z0-9_-]+", name):
        raise RuntimeError(f"Database {name!r} does not exist. Create it yourself: its name is unusual.")
    conn = await asyncpg.connect(urlunsplit(parts._replace(path="/postgres")))
    try:
        await conn.execute(f'CREATE DATABASE "{name}"')
        log.info("Created database %s", name)
    except asyncpg.DuplicateDatabaseError:
        pass  # another server got there first
    finally:
        await conn.close()


def _stop_preview_database() -> None:
    global _server, _stop_command
    if _server is not None:
        _server.cleanup()
        _server = None
    if _stop_command is not None:
        subprocess.run(_stop_command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        _stop_command = None


async def shutdown() -> None:
    """A startup hook's partner: uvicorn re-raises the stop signal once it is done, so atexit alone never runs."""
    await asyncio.to_thread(_stop_preview_database)


atexit.register(_stop_preview_database)  # for `python -m src.database.migrate`, which has no shutdown event


async def prepare() -> None:
    url = os.environ.get("DATABASE_URL") or await asyncio.to_thread(_preview_url)
    await _create_if_missing(url)
    await apply_migrations(url)
    os.environ["DATABASE_URL"] = database.DSN = url
'''

MAIN = '''import os

import uvicorn

from src.app import app

if __name__ == "__main__":
    uvicorn.run(app, host=os.environ.get("HOST", "127.0.0.1"), port=int(os.environ.get("PORT", "8000")))
'''

REQUIREMENTS = 'fastapi==0.115.12\nuvicorn==0.34.3\nasyncpg==0.30.0\npgserver==0.1.4; python_version < "3.13"\n'

ENV_EXAMPLE = """# Leave DATABASE_URL unset to use a private preview database in .data/.
# DATABASE_URL=postgresql://user:password@localhost/app

# production: DATABASE_URL becomes required, and the frontend must already be built.
# APP_ENV=production

# Set to 1 when serving over HTTPS, so the session cookie is only sent over TLS.
COOKIE_SECURE=0
"""

MAKEFILE = """# pgserver, the embedded preview database, only has builds for Python 3.11 and 3.12.
PYTHON ?= $(shell command -v python3.12 || command -v python3.11 || command -v python3)

-include .env
export

.PHONY: preview run install build migrate dev

preview: .venv/.installed frontend/dist/index.html
\t.venv/bin/python -m src.main

run: preview

install: .venv/.installed frontend/node_modules/.installed

build: frontend/dist/index.html

migrate: .venv/.installed
\t.venv/bin/python -m src.database.migrate

dev: frontend/node_modules/.installed
\tcd frontend && npm run dev

.venv/.installed: requirements.txt
\ttest -x .venv/bin/python || $(PYTHON) -m venv .venv
\t.venv/bin/pip install --quiet -r requirements.txt
\ttouch $@

frontend/node_modules/.installed: frontend/package-lock.json
\tcd frontend && npm ci --no-audit --no-fund
\ttouch $@

frontend/dist/index.html: frontend/node_modules/.installed $(wildcard frontend/src/*)
\tcd frontend && npm run build
"""

GITIGNORE = ".venv/\n__pycache__/\nnode_modules/\ndist/\n.env\n.data/\n"
