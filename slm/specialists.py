"""The four specialist SLMs, defined in one place.

Each specialist is one LoRA adapter on Qwen3-0.6B. This module says what each one is for, which
task kinds it owns, what every kind reads and writes, and the house conventions its code follows.
Its system prompt (`system_prompt`) is rendered from this spec, so changing a specialist means
editing it here, and the same text is used for training and for serving.

The interface contract itself (paths, symbols, exact tokens) stays in `slm/domains.py`. Conventions
here are the *style* the gold artifacts in `slm/bench/catalog.py` follow; `must_contain` lists the
literal snippets every gold artifact of that kind contains (tests/test_specialists.py checks that),
so the prompt never promises something the training data does not show.

Placeholders in `path`, `conventions` and `must_contain`: {target}, {Pascal} (PascalCase target),
{plural} (REST collection), {route} (/{plural}), {api} (/api/{plural}).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from slm.domains import ADAPTER, KINDS, api_base, page_route, pascal, plural

BASE = "Qwen/Qwen3-0.6B"


@dataclass(frozen=True)
class KindSpec:
    kind: str
    builds: str  # one line: what a task of this kind produces
    path: str  # canonical primary file (must match domains.canonical_path)
    reads: str  # what it consumes, in words (exact symbols come with each task prompt)
    writes: str  # what it exports, in words
    conventions: tuple[str, ...]
    must_contain: tuple[str, ...] = ()


@dataclass(frozen=True)
class Specialist:
    domain: str
    title: str
    mission: str
    owns: str  # the files no other specialist writes
    never: tuple[str, ...]  # out of scope: what belongs to a teammate
    kinds: tuple[KindSpec, ...]
    language: str
    base_model: str = BASE
    shared: tuple[str, ...] = field(default=())  # project-wide modules it may import

    @property
    def adapter(self) -> str:
        return ADAPTER[self.domain]

    def kind(self, kind: str) -> KindSpec:
        return next(k for k in self.kinds if k.kind == kind)


def fill(text: str, target: str) -> str:
    return text.format(target=target, Pascal=pascal(target), plural=plural(target),
                       route=page_route(target), api=api_base(target))


DATABASE = Specialist(
    domain="database",
    title="Database specialist",
    mission="Owns the Postgres schema: one table per file, the columns the API and pages read, and "
            "ownership back to users.",
    owns="src/database/<table>.sql",
    language="Postgres SQL",
    never=("queries or ORM code (network)", "session or password logic (auth)", "migrations tooling"),
    kinds=(
        KindSpec(
            kind="schema",
            builds="one CREATE TABLE statement for one table",
            path="src/database/{target}.sql",
            reads="nothing; schemas are the first dependency level",
            writes="the table `{target}`",
            conventions=(
                "first line is a `-- <path>` comment",
                "`id BIGSERIAL PRIMARY KEY` first, `created_at TIMESTAMPTZ NOT NULL DEFAULT now()` last",
                "the users table has `email TEXT NOT NULL UNIQUE`, `password_hash TEXT NOT NULL` and "
                "`session_token TEXT`",
                "every other table has `owner_id BIGINT NOT NULL REFERENCES users (id)`, a "
                "`title TEXT NOT NULL` column, and an index `<table>_owner_idx` on owner_id",
            ),
            must_contain=("-- src/database/{target}.sql", "CREATE TABLE {target} (",
                          "id BIGSERIAL PRIMARY KEY", "created_at TIMESTAMPTZ NOT NULL DEFAULT now()"),
        ),
    ),
)

AUTH = Specialist(
    domain="auth",
    title="Auth specialist",
    mission="Owns who the user is: cookie sessions over the users table, the OAuth hand-off, and the "
            "guard that keeps signed-out users off every page.",
    owns="src/auth/session.py, src/auth/oauth.py, src/auth/guards.py",
    language="Python (FastAPI)",
    shared=("src.database.db.db (asyncpg-style pool: fetch, fetchrow)",),
    never=("table definitions (database)", "REST routers (network)", "React code (frontend)"),
    kinds=(
        KindSpec(
            kind="session",
            builds="the session dependency every protected handler uses",
            path="src/auth/session.py",
            reads="the users table",
            writes="`require_session`",
            conventions=(
                "`async def require_session(request: Request) -> dict` reads the `app_session` cookie",
                "looks the user up with `SELECT * FROM users WHERE session_token = $1` through "
                "`from src.database.db import db`",
                "raises PermissionError when signed out or the token is unknown; returns the user row as a dict",
            ),
            must_contain=("from src.database.db import db", 'SESSION_COOKIE = "app_session"',
                          "async def require_session(request: Request) -> dict:", "FROM users"),
        ),
        KindSpec(
            kind="oauth",
            builds="the OAuth start/callback hand-off",
            path="src/auth/oauth.py",
            reads="`require_session`",
            writes="`oauth_start`",
            conventions=(
                "`async def oauth_start(request)` returns the provider redirect and a state value",
                "`async def oauth_callback(request)` uses require_session to mint and return the signed-in user",
                "provider URLs are module constants AUTHORIZE_URL and TOKEN_URL",
            ),
            must_contain=("from src.auth.session import require_session", "async def oauth_start(request):",
                          "async def oauth_callback(request):"),
        ),
        KindSpec(
            kind="guards",
            builds="the route guard middleware",
            path="src/auth/guards.py",
            reads="`require_session` and every page route in the plan",
            writes="`require_route_guard`",
            conventions=(
                "`PROTECTED_ROUTES` lists every page route of the project as strings",
                "`async def require_route_guard(request, call_next)` calls require_session for protected "
                "paths, then `call_next(request)`",
            ),
            must_contain=("from src.auth.session import require_session", "PROTECTED_ROUTES = [",
                          "async def require_route_guard(request, call_next):"),
        ),
    ),
)

NETWORK = Specialist(
    domain="network",
    title="Network specialist",
    mission="Owns the wire between the database and the UI: one FastAPI router per entity and the typed "
            "TypeScript client the frontend calls.",
    owns="src/network/<entity>_api.py, src/network/<entity>_client.ts",
    language="Python (FastAPI) and TypeScript",
    shared=("src.database.db.db", "src.auth.session.require_session"),
    never=("CREATE TABLE (database)", "cookie or OAuth logic (auth)", "components or pages (frontend)"),
    kinds=(
        KindSpec(
            kind="rest",
            builds="list / create / fetch-one endpoints for one entity",
            path="src/network/{target}_api.py",
            reads="the `{target}` table and `require_session`",
            writes="GET and POST {api}, GET {api}/{{item_id}}",
            conventions=(
                "`router = APIRouter(tags=[\"<entity>\"])`, imports `Depends`, `require_session` and `db`",
                "decorators use the exact paths, e.g. `@router.get(\"{api}\")`",
                "POST takes `payload: dict, user: dict = Depends(require_session)` and inserts "
                "`owner_id` and `title`, `RETURNING *`",
                "SQL uses positional parameters ($1, $2) and reads `FROM <table>`",
            ),
            must_contain=("from src.auth.session import require_session", "from src.database.db import db",
                          "router = APIRouter(", '@router.get("{api}")', '@router.post("{api}")',
                          '@router.get("{api}/{{item_id}}")', "Depends(require_session)", "FROM {target}"),
        ),
        KindSpec(
            kind="client",
            builds="a typed fetch client for one entity",
            path="src/network/{target}_client.ts",
            reads="GET and POST {api}",
            writes="`list{Pascal}` and `create{Pascal}`",
            conventions=(
                "`export type {Pascal} = {{ id: number; title: string }}`",
                "`export async function list{Pascal}(): Promise<{Pascal}[]>` and "
                "`export async function create{Pascal}(payload)` both `fetch(\"{api}\")`",
            ),
            must_contain=("export type {Pascal} = {{ id: number; title: string }};",
                          "export async function list{Pascal}(", "export async function create{Pascal}(",
                          'fetch("{api}"'),
        ),
    ),
)

FRONTEND = Specialist(
    domain="frontend",
    title="Frontend specialist",
    mission="Owns what the user sees: a React page per entity, the create form, and the app shell that "
            "links every page.",
    owns="src/frontend/<Entity>Page.tsx, src/frontend/<Entity>Form.tsx, src/frontend/Shell.tsx",
    language="React + TypeScript",
    never=("fetch paths that no endpoint serves (network)", "auth checks (the guard covers routes)",
           "SQL (database)"),
    kinds=(
        KindSpec(
            kind="page",
            builds="a list page for one entity",
            path="src/frontend/{Pascal}Page.tsx",
            reads="GET {api}",
            writes="route {route} and the `{Pascal}Page` component",
            conventions=(
                "`export const route = \"{route}\"` and `export function {Pascal}Page()`",
                "loads rows with `useEffect` + `fetch(\"{api}\")` into `useState`, renders each row's title "
                "in a list keyed by id",
            ),
            must_contain=('export const route = "{route}";', "export function {Pascal}Page(",
                          'fetch("{api}")', "useEffect", "key={{row.id}}"),
        ),
        KindSpec(
            kind="form",
            builds="the create form for one entity",
            path="src/frontend/{Pascal}Form.tsx",
            reads="the typed `{target}` client",
            writes="the `{Pascal}Form` component",
            conventions=(
                "imports `create{Pascal}` from \"../network/{target}_client\" (never calls fetch directly)",
                "`export function {Pascal}Form()` renders a form whose onSubmit prevents the default and "
                "calls create{Pascal}",
            ),
            must_contain=('import {{ create{Pascal} }} from "../network/{target}_client";',
                          "export function {Pascal}Form(", "event.preventDefault();"),
        ),
        KindSpec(
            kind="layout",
            builds="the app shell",
            path="src/frontend/Shell.tsx",
            reads="every page route and page component in the plan",
            writes="`Shell`",
            conventions=(
                "imports every page component from \"./<Entity>Page\"",
                "`export function Shell()` renders a nav link per page route, then every page component",
            ),
            must_contain=("export function Shell(", "<nav>", "<main>"),
        ),
    ),
)

SPECIALISTS: dict[str, Specialist] = {s.domain: s for s in (DATABASE, AUTH, NETWORK, FRONTEND)}

_DB_METHODS = ("`db` is an object, not a module. Call `await db.fetch(sql, *args)` for a list of rows, "
               "`await db.fetchrow(sql, *args)` for one row or None and `await db.execute(sql, *args)` to change data, "
               "directly on `db`. It has no fetch_all or fetch_one.")

# Literal imports for the arm that measures clearer wording. `shared` keeps its wording because the earlier arms, the
# baselines and the training data all used it, and changing it would make them incomparable.
EXACT_IMPORTS = {
    "auth": f"Import the database with exactly: `from src.database.db import db`. {_DB_METHODS}",
    "network": "Import with exactly: `from src.database.db import db` and "
               f"`from src.auth.session import require_session`. {_DB_METHODS}",
}

REPLY_FORMAT = ('Reply with only JSON: {"files": [{"path": "<path>", "content": "<file>"}], '
                '"summary": "<one line>"}.')


def system_prompt(domain: str, exact_imports: bool = False) -> str:
    """The specialist's system prompt (train == serve). Kind-level placeholders stay generic here;
    the task prompt carries the concrete path and interface tokens. `exact_imports` is for mgr-G4-promptfix only."""
    s = SPECIALISTS[domain]
    lines = [
        f"You are the {domain} specialist on a four-person software team (database, auth, network, "
        f"frontend). {s.mission}",
        f"You write {s.language}. You own {s.owns}.",
    ]
    if s.shared:
        lines.append(EXACT_IMPORTS[domain] if exact_imports else "You may import: " + "; ".join(s.shared) + ".")
    lines.append("Not your job: " + "; ".join(s.never) + ".")
    for k in s.kinds:
        conv = "; ".join(_generic(c) for c in k.conventions)
        lines.append(f"[{k.kind}] {k.builds}. Reads {_generic(k.reads)}; exports {_generic(k.writes)}. {conv}.")
    lines.append("Build exactly the one task you are given, at the path given, using every interface "
                 "token listed. " + REPLY_FORMAT)
    return "\n".join(lines)


def _generic(text: str) -> str:
    """Render kind-level placeholders for the system prompt (no specific entity)."""
    return text.format(target="<entity>", Pascal="<Entity>", plural="<entities>",
                       route="/<entities>", api="/api/<entities>")


def describe() -> str:
    """Markdown card per specialist (used by `slm specialists`)."""
    out = []
    for s in SPECIALISTS.values():
        out.append(f"## {s.title} · `{s.adapter}` on {s.base_model}\n\n{s.mission}\n\n"
                   f"- Owns: {s.owns}\n- Language: {s.language}\n- Not its job: {'; '.join(s.never)}\n")
        for k in s.kinds:
            out.append(f"### {s.domain}/{k.kind}: {k.builds}\n- File: `{_generic(k.path)}`\n"
                       f"- Reads: {_generic(k.reads)}\n- Exports: {_generic(k.writes)}\n"
                       + "".join(f"- {_generic(c)}\n" for c in k.conventions))
    return "\n".join(out)


assert all(tuple(k.kind for k in s.kinds) == KINDS[d] for d, s in SPECIALISTS.items()), "spec drifted from KINDS"
