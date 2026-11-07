"""Broken versions of a gold project: one small, behavior-changing defect per version."""

from __future__ import annotations

import re
from dataclasses import dataclass

from slm.contracts import ProjectPlan
from slm.domains import api_base, component, page_route, pascal, plural


@dataclass(frozen=True)
class Mutant:
    id: str
    path: str
    content: str


def _swap(content: str, old: str, new: str, mutant_id: str, count: int = 1) -> str:
    if old not in content:
        raise ValueError(f"{mutant_id}: pattern not found: {old!r}")
    return content.replace(old, new, count)


def mutants_for(plan: ProjectPlan, files: dict[str, str]) -> list[Mutant]:
    out: list[Mutant] = []

    def add(mid: str, path: str, *pairs: tuple[str, str]) -> None:
        content = files[path]
        for old, new in pairs:
            content = _swap(content, old, new, mid)
        out.append(Mutant(mid, path, content))

    for t in plan.tasks:
        e = t.target
        if t.kind == "schema" and e == "users":
            p = "src/database/users.sql"
            add("users_no_session_token", p, ("  session_token TEXT,\n", ""))
            add("users_no_email", p, ("  email TEXT NOT NULL UNIQUE,\n", ""))
        elif t.kind == "schema":
            p = f"src/database/{e}.sql"
            add(f"schema_no_fk:{e}", p, (" REFERENCES users (id)", ""))
            add(f"schema_no_owner:{e}", p, ("  owner_id BIGINT NOT NULL REFERENCES users (id),\n", ""),
                (f"CREATE INDEX {e}_owner_idx ON {e} (owner_id);\n", ""))
            add(f"schema_no_title:{e}", p, ("  title TEXT NOT NULL,\n", ""))
        elif t.kind == "session":
            p = "src/auth/session.py"
            cookie = "    token = request.cookies.get(SESSION_COOKIE)\n"
            add("session_bypass", p, (cookie, '    return {"id": 2, "email": "anon"}\n' + cookie))
            add("session_wrong_cookie", p, ('SESSION_COOKIE = "app_session"', 'SESSION_COOKIE = "other"'))
            add("session_any_user", p, ('"SELECT * FROM users WHERE session_token = $1", token',
                                        '"SELECT * FROM users WHERE $1::text IS NOT NULL ORDER BY id LIMIT 1", token'))
            add("session_wrong_status", p, ('status_code=401, detail="signed out"', 'status_code=403, detail="signed out"'))
        elif t.kind == "oauth":
            add("oauth_no_redirect", "src/auth/oauth.py", ('{"redirect": AUTHORIZE_URL,', '{"redirect": "/",'))
        elif t.kind == "guards":
            p = "src/auth/guards.py"
            add("guards_noop", p, ("if request.url.path in PROTECTED_ROUTES:", "if False:"))
            routes = re.search(r"PROTECTED_ROUTES = \[(.*)\]", files[p])[1]
            add("guards_empty", p, (f"PROTECTED_ROUTES = [{routes}]", "PROTECTED_ROUTES = []"))
            parts = routes.split(", ")
            if len(parts) > 1:
                add("guards_drop_route", p, (f"PROTECTED_ROUTES = [{routes}]",
                                             f"PROTECTED_ROUTES = [{', '.join(parts[:-1])}]"))
        elif t.kind == "rest":
            p, base, many = f"src/network/{e}_api.py", api_base(e), plural(e)
            signature = f"async def list_{many}(user: dict = Depends(require_session)):"
            add(f"list_unordered:{e}", p, ("ORDER BY id DESC", "ORDER BY id ASC"))
            add(f"list_empty:{e}", p, (f'return await db.fetch("SELECT * FROM {e} ORDER BY id DESC")', "return []"))
            add(f"list_open:{e}", p, (signature, f"async def list_{many}():"))
            add(f"list_wrong_path:{e}", p, (f'@router.get("{base}")', f'@router.get("{base}_x")'))
            add(f"create_wrong_path:{e}", p, (f'@router.post("{base}")', f'@router.post("{base}_x")'))
            add(f"create_no_title:{e}", p, ('payload.get("title")', '"untitled"'))
            add(f"create_wrong_owner:{e}", p, ('user["id"], payload', "1, payload"))
            add(f"get_ignores_id:{e}", p, (f'"SELECT * FROM {e} WHERE id = $1", item_id',
                                           f'"SELECT * FROM {e} WHERE $1::bigint IS NOT NULL ORDER BY id LIMIT 1", item_id'))
            add(f"get_open:{e}", p, (f"async def get_{e}(item_id: int, user: dict = Depends(require_session)):",
                                     f"async def get_{e}(item_id: int):"))
        elif t.kind == "client":
            p, base = f"src/network/{e}_client.ts", api_base(e)
            add("client_wrong_list_path", p, (f'await fetch("{base}");', f'await fetch("{base}_x");'))
            add("client_post_as_put", p, ('method: "POST"', 'method: "PUT"'))
            add("client_no_body", p, ("    body: JSON.stringify(payload),\n", ""))
        elif t.kind == "page":
            p, comp = f"src/frontend/{component(e, 'page')}.tsx", component(e, "page")
            route, base = page_route(e), api_base(e)
            add(f"page_wrong_route:{comp}", p, (f'export const route = "{route}"', f'export const route = "{route}_x"'))
            add(f"page_wrong_fetch:{comp}", p, (f'fetch("{base}")', f'fetch("{base}_x")'))
            add(f"page_first_row_only:{comp}", p, ("{rows.map(", "{rows.slice(0, 1).map("))
            add(f"page_ignores_rows:{comp}", p, (".then(setRows)", ".then(() => undefined)"))
        elif t.kind == "form":
            p, call = f"src/frontend/{component(e, 'form')}.tsx", f'create{pascal(e)}({{ title: "new {e}" }});'
            add("form_no_create", p, (call, ""))
            add("form_creates_twice", p, (call, call + " " + call))
        elif t.kind == "layout":
            p, pages = "src/frontend/Shell.tsx", [x.target for x in plan.tasks if x.kind == "page"]
            last = pages[-1]
            add("shell_missing_link", p, (f'        <a href="{page_route(last)}">{pascal(last)}</a><br />\n', ""))
            add("shell_missing_page", p, (f"        <{component(last, 'page')} />\n", ""))
    return out
