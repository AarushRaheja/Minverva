"""Project templates and the gold artifacts each domain specialist is expected to produce.

`gold_artifact(plan, task)` is the reference answer for one task: it is what the specialist
adapters are trained on (via slm/bench/build.py) and what `OracleSpecialist` returns, so a gold
plan + gold artifacts must integrate cleanly (`oracle.py` and the tests assert exactly that).

Rendering uses string.Template so JSX braces need no escaping.
"""

from __future__ import annotations

from dataclasses import dataclass
from string import Template

from slm.contracts import Artifact, ArtifactFile, ProjectPlan, Task
from slm.domains import (
    api_base, canonical_path, component, detail_for, pascal, page_route, plural, provides_of,
)

STACK = "fastapi+react+postgres"


@dataclass(frozen=True)
class Template_:
    id: str
    name: str
    article: str  # "an invoice tracker for a design studio"
    entities: tuple[str, ...]
    form: str  # which entity gets the create form
    oauth: bool


# Training pool.
TRAIN_TEMPLATES: list[Template_] = [
    Template_("invoice_tracker", "invoice tracker", "an invoice tracker for a design studio",
              ("invoice", "client"), "invoice", True),
    Template_("issue_board", "issue board", "an issue board for an engineering team",
              ("issue", "project"), "issue", False),
    Template_("room_booking", "room booking service", "a room booking service for an office",
              ("booking", "room"), "booking", True),
    Template_("course_platform", "course platform", "a course platform with enrollments",
              ("course", "enrollment"), "enrollment", True),
    Template_("expense_log", "expense log", "an expense log for freelancers",
              ("expense", "tag"), "expense", True),
    Template_("stock_room", "inventory service", "an inventory service for a stock room",
              ("item", "supplier"), "item", False),
    Template_("chat_service", "chat service", "a chat service with channels",
              ("message", "channel"), "message", True),
    Template_("survey_tool", "survey tool", "a survey tool for internal feedback",
              ("survey", "response"), "survey", False),
]

# Held-out pool: only split="test" items use these, so the specialists and the manager are
# scored on entities and wordings they were never trained on.
HELDOUT_TEMPLATES: list[Template_] = [
    Template_("ticket_desk", "support ticket desk", "a support ticket desk for a SaaS product",
              ("ticket", "agent"), "ticket", True),
    Template_("recipe_box", "recipe box", "a recipe box for home cooks",
              ("recipe", "collection"), "recipe", False),
]

_BRIEF = Template(
    "Build $article (stack: $stack).\n\n"
    "Requirements:\n"
    "- Database: one Postgres table per entity ($entities) plus a users table for accounts.\n"
    "- Auth: cookie sessions backed by the users table; $oauth_text a route guard so signed-out\n"
    "  users cannot reach any page.\n"
    "- Network: REST endpoints for every entity (list, create, fetch one) behind session auth, and a\n"
    "  typed TypeScript client for $form.\n"
    "- Frontend: a React page per entity ($pages), one create form for $form, and an app shell that\n"
    "  links every page.\n"
    "Split the work across the four specialists and return the plan."
)


def render_description(tpl: Template_) -> str:
    return _BRIEF.substitute(
        article=tpl.article,
        stack=STACK,
        entities=", ".join(tpl.entities),
        oauth_text="an OAuth sign-in hand-off plus" if tpl.oauth else "no OAuth (sessions only), plus",
        form=tpl.form,
        pages=", ".join(page_route(e) for e in tpl.entities),
    )


# --- Gold plan -----------------------------------------------------------------


def build_plan(tpl: Template_) -> ProjectPlan:
    """The reference decomposition: tables -> sessions -> routers/clients -> pages -> guards/shell."""
    tasks: list[Task] = []
    providers: dict[str, str] = {}

    def add(domain: str, kind: str, target: str) -> Task:
        from slm.domains import requires_of

        routes = tuple(
            s.split(":", 1)[1] for s in providers if s.startswith("route:")
        )
        comps = tuple(
            s.split(":", 1)[1] for s in providers if s.startswith("component:")
        )
        req = requires_of(domain, kind, target, routes=routes, components=comps)
        missing = [s for s in req if s not in providers]
        if missing:
            raise AssertionError(f"gold plan orders tasks badly: {domain}/{kind}/{target} needs {missing}")
        t = Task(
            id=f"t{len(tasks) + 1}", domain=domain, kind=kind, target=target,
            detail=detail_for(domain, kind, target),
            deps=sorted({providers[s] for s in req}),
        )
        for s in t.provides():
            providers.setdefault(s, t.id)
        tasks.append(t)
        return t

    add("database", "schema", "users")
    for e in tpl.entities:
        add("database", "schema", e)
    add("auth", "session", "session")
    if tpl.oauth:
        add("auth", "oauth", "oauth")
    for e in tpl.entities:
        add("network", "rest", e)
    add("network", "client", tpl.form)
    for e in tpl.entities:
        add("frontend", "page", e)
    add("frontend", "form", tpl.form)
    add("auth", "guards", "routes")
    add("frontend", "layout", "shell")
    return ProjectPlan(name=tpl.name, stack=STACK, tasks=tasks)


# --- Gold artifacts ------------------------------------------------------------

_SCHEMA = Template("""-- $path
CREATE TABLE $table (
  id BIGSERIAL PRIMARY KEY,
  owner_id BIGINT NOT NULL REFERENCES users (id),
  title TEXT NOT NULL,
  amount_cents INTEGER NOT NULL DEFAULT 0,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX ${table}_owner_idx ON $table (owner_id);
""")

_USERS = Template("""-- $path
CREATE TABLE users (
  id BIGSERIAL PRIMARY KEY,
  email TEXT NOT NULL UNIQUE,
  password_hash TEXT NOT NULL,
  session_token TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
""")

_SESSION = Template("""# $path
from fastapi import Request

from src.database.db import db

SESSION_COOKIE = "app_session"


async def require_session(request: Request) -> dict:
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        raise PermissionError("signed out")
    user = await db.fetchrow("SELECT * FROM users WHERE session_token = $$1", token)
    if user is None:
        raise PermissionError("unknown session")
    return dict(user)
""")

_OAUTH = Template("""# $path
from src.auth.session import require_session

AUTHORIZE_URL = "https://accounts.example.com/authorize"
TOKEN_URL = "https://accounts.example.com/token"


async def oauth_start(request):
    \"\"\"Begin the provider hand-off; the callback below mints the session.\"\"\"
    return {"redirect": AUTHORIZE_URL, "state": request.headers.get("x-request-id")}


async def oauth_callback(request):
    user = await require_session(request)
    return {"signed_in": user["email"]}
""")

_GUARDS = Template("""# $path
from src.auth.session import require_session

PROTECTED_ROUTES = [$routes]


async def require_route_guard(request, call_next):
    if request.url.path in PROTECTED_ROUTES:
        await require_session(request)
    return await call_next(request)
""")

_REST = Template("""# $path
from fastapi import APIRouter, Depends

from src.auth.session import require_session
from src.database.db import db

router = APIRouter(tags=["$entity"])


@router.get("$base")
async def list_$entities():
    return await db.fetch("SELECT * FROM $table ORDER BY id DESC")


@router.post("$base")
async def create_$entity(payload: dict, user: dict = Depends(require_session)):
    return await db.fetchrow(
        "INSERT INTO $table (owner_id, title) VALUES ($$1, $$2) RETURNING *",
        user["id"], payload.get("title"),
    )


@router.get("$base/{item_id}")
async def get_$entity(item_id: int):
    return await db.fetchrow("SELECT * FROM $table WHERE id = $$1", item_id)
""")

_CLIENT = Template("""// $path
export type $Pascal = { id: number; title: string };

type New$Pascal = Omit<$Pascal, "id">;

export async function list$Pascal$comp(): Promise<$Pascal[]> {
  const res = await fetch("$base");
  return res.json();
}

export async function create$Pascal(payload: New$Pascal): Promise<$Pascal> {
  const res = await fetch("$base", { method: "POST", body: JSON.stringify(payload) });
  return res.json();
}
""")

_PAGE = Template("""// $path
import { useEffect, useState } from "react";

export const route = "$route";

export function $Comp() {
  const [rows, setRows] = useState<$Pascal[]>([]);

  useEffect(() => {
    fetch("$base")
      .then((res) => res.json())
      .then(setRows);
  }, []);

  return (
    <section>
      <h1>$Pascal</h1>
      <ul>
        {rows.map((row) => (
          <li key={row.id}>{row.title}</li>
        ))}
      </ul>
    </section>
  );
}
""")

_FORM = Template("""// $path
import { create$Pascal } from "../network/${entity}_client";

export function $Comp() {
  return (
    <form
      onSubmit={(event) => {
        event.preventDefault();
        create$Pascal({ title: "new $entity" });
      }}
    >
      <input name="title" placeholder="$Pascal title" />
      <button type="submit">Save</button>
    </form>
  );
}
""")

_LAYOUT = Template("""// $path
$imports

export function Shell() {
  return (
    <div>
      <nav>
$links
      </nav>
      <main>
$pages
      </main>
    </div>
  );
}
""")


def gold_artifact(plan: ProjectPlan, task: Task) -> Artifact:
    """The reference artifact for one task, rendered from its kind and the plan's interfaces."""
    path = canonical_path(task.domain, task.kind, task.target)
    e = task.target

    if task.domain == "database":
        body = _USERS if e == "users" else _SCHEMA
        content = body.substitute(path=path, table=e)
        summary = f"Postgres table {e}"

    elif task.domain == "auth" and task.kind == "session":
        content = _SESSION.substitute(path=path)
        summary = "cookie sessions on the users table"

    elif task.domain == "auth" and task.kind == "oauth":
        content = _OAUTH.substitute(path=path)
        summary = "OAuth hand-off minting a session"

    elif task.domain == "auth":  # guards
        routes = ", ".join(f'"{r}"' for r in plan.routes())
        content = _GUARDS.substitute(path=path, routes=routes)
        summary = "route guard over every page"

    elif task.domain == "network" and task.kind == "rest":
        content = _REST.substitute(
            path=path, entity=e, entities=plural(e), table=e, base=api_base(e),
        )
        summary = f"REST router for {e}"

    elif task.domain == "network":  # client
        content = _CLIENT.substitute(
            path=path, entity=e, Pascal=pascal(e), base=api_base(e), comp="",
        )
        summary = f"typed client for {e}"

    elif task.kind == "page":
        content = _PAGE.substitute(
            path=path, route=page_route(e), base=api_base(e),
            Pascal=pascal(e), Comp=component(e, "page"),
        )
        summary = f"React page {page_route(e)}"

    elif task.kind == "form":
        content = _FORM.substitute(path=path, entity=e, Pascal=pascal(e), Comp=component(e, "form"))
        summary = f"create form for {e}"

    else:  # layout
        pages = [t for t in plan.tasks if t.kind == "page"]
        imports = "\n".join(f'import {{ {component(t.target, "page")} }} from "./{pascal(t.target)}Page";'
                            for t in pages)
        links = "\n".join(f'        <a href="{page_route(t.target)}">{pascal(t.target)}</a><br />'
                          for t in pages)
        rendered = "\n".join(f"        <{component(t.target, 'page')} />" for t in pages)
        content = _LAYOUT.substitute(path=path, imports=imports, links=links, pages=rendered)
        summary = "app shell linking every page"

    return Artifact(files=[ArtifactFile(path=path, content=content)], summary=summary)


def gold_artifacts(plan: ProjectPlan) -> dict[str, Artifact]:
    """task id -> reference artifact. Gold plan + these must integrate with every check green."""
    return {t.id: gold_artifact(plan, t) for t in plan.tasks}


def plan_summary(plan: ProjectPlan) -> str:
    """Human-readable dump used by the CLI (`slm bench sample`)."""
    lines = [f"{plan.name}  ({plan.stack})  {len(plan.tasks)} tasks, {len(plan.levels())} levels"]
    for t in plan.tasks:
        lines.append(f"  {t.id:>3} [{t.domain:8}/{t.kind:6}] {t.target:10} deps={t.deps} "
                     f"provides={provides_of(t.domain, t.kind, t.target)}")
    return "\n".join(lines)
