"""The four specialist domains: task kinds, interface symbols, file layout, contract tokens.

Pure strings, no pydantic, no imports from slm.contracts (contracts imports this module).
Everything here is a pure function of (domain, kind, target), so the data generator, the
specialist prompts, the integrator and the grader all agree by construction.
"""

from __future__ import annotations

from typing import Literal

Domain = Literal["network", "auth", "frontend", "database"]

# Order is also the order the manager prompt lists the team in.
DOMAINS: tuple[str, ...] = ("database", "auth", "network", "frontend")

# One LoRA adapter (Qwen3-0.6B) per domain, trained on that domain's task data.
ADAPTER: dict[str, str] = {
    "database": "spec-database",
    "auth": "spec-auth",
    "network": "spec-network",
    "frontend": "spec-frontend",
}

KINDS: dict[str, tuple[str, ...]] = {
    "database": ("schema",),
    "auth": ("session", "oauth", "guards"),
    "network": ("rest", "client"),
    "frontend": ("page", "form", "layout"),
}

# Extensions used by the canonical path of each kind.
_EXT = {"schema": "sql", "session": "py", "oauth": "py", "guards": "py",
        "rest": "py", "client": "ts", "page": "tsx", "form": "tsx", "layout": "tsx"}


def pascal(name: str) -> str:
    """orders -> Orders, line_item -> LineItem"""
    return "".join(part[:1].upper() + part[1:] for part in name.split("_") if part)


def plural(entity: str) -> str:
    """Entity slug -> REST collection segment. Deliberately naive: the catalog keeps slugs regular."""
    return entity + ("es" if entity.endswith(("s", "x", "ch")) else "s")


def api_base(entity: str) -> str:
    return f"/api/{plural(entity)}"


def page_route(entity: str) -> str:
    return f"/{plural(entity)}"


def component(entity: str, kind: str) -> str:
    return f"{pascal(entity)}{kind[:1].upper() + kind[1:]}"


def canonical_path(domain: str, kind: str, target: str) -> str:
    """The one path a task's primary file must live at. The integrator's glue imports these."""
    if domain == "database":
        return f"src/database/{target}.sql"
    if domain == "network":
        if kind == "rest":
            return f"src/network/{target}_api.py"
        return f"src/network/{target}_client.ts"
    if domain == "auth":
        return {"session": "src/auth/session.py", "oauth": "src/auth/oauth.py",
                "guards": "src/auth/guards.py"}[kind]
    if domain == "frontend":
        if kind == "layout":
            return "src/frontend/Shell.tsx"
        return f"src/frontend/{pascal(target)}{kind[:1].upper() + kind[1:]}.tsx"
    raise ValueError(f"unknown domain {domain!r}")


def detail_for(domain: str, kind: str, target: str) -> str:
    """Canonical one-line task spec (the generator's gold plans use exactly these)."""
    if domain == "database":
        return f"Postgres table `{target}` with an id, owner, timestamps and the columns the API needs."
    if domain == "network":
        if kind == "rest":
            return (f"REST endpoints for `{target}`: GET and POST {api_base(target)}, "
                    f"GET {api_base(target)}/{{item_id}}; every handler requires a session.")
        return f"Typed TypeScript client for `{target}` with list/create functions over {api_base(target)}."
    if domain == "auth":
        return {
            "session": "Session cookie auth: a `require_session` dependency that loads the user row.",
            "oauth": "OAuth start/callback flow that mints the session after the provider returns.",
            "guards": "Route guard that rejects signed-out users for every protected frontend route.",
        }[kind]
    return {
        "page": f"React page at {page_route(target)} that fetches {api_base(target)} and renders rows.",
        "form": f"React form component that creates a `{target}` through the typed client.",
        "layout": "App shell: navigation to every page and the page components rendered inside it.",
    }[kind]


def provides_of(domain: str, kind: str, target: str) -> list[str]:
    """Interface symbols this task exports to the rest of the project."""
    if domain == "database":
        return [f"table:{target}"]
    if domain == "network":
        if kind == "rest":
            base = api_base(target)
            return [f"endpoint:GET {base}", f"endpoint:POST {base}", f"endpoint:GET {base}/{{item_id}}"]
        return [f"client:{target}"]
    if domain == "auth":
        return {"session": ["guard:session"], "oauth": ["provider:oauth"],
                "guards": ["guard:routes"]}[kind]
    if kind == "page":
        return [f"route:{page_route(target)}", f"component:{component(target, 'page')}"]
    if kind == "form":
        return [f"form:{component(target, 'form')}"]
    return ["layout:shell"]


def requires_of(domain: str, kind: str, target: str, *, routes: tuple[str, ...] = (),
                components: tuple[str, ...] = ()) -> list[str]:
    """Interface symbols this task consumes. `routes`/`components` are the plan's page surfaces."""
    if domain == "database":
        return []
    if domain == "network":
        if kind == "rest":
            return [f"table:{target}", "guard:session"]
        return [f"endpoint:GET {api_base(target)}", f"endpoint:POST {api_base(target)}"]
    if domain == "auth":
        return {"session": ["table:users"], "oauth": ["guard:session"], "guards": ["guard:session"]}[kind]
    if kind == "page":
        return [f"endpoint:GET {api_base(target)}"]
    if kind == "form":  # the typed client already owns the POST path
        return [f"client:{target}"]
    return [f"route:{r}" for r in routes] + [f"component:{c}" for c in components]


def provide_token(symbol: str) -> str:
    """The exact code token that proves a task exports `symbol`."""
    kind, name = symbol.split(":", 1)
    if kind == "table":
        return f"CREATE TABLE {name}"
    if kind == "endpoint":
        method, path = name.split(" ", 1)
        return f'@router.{method.lower()}("{path}")'
    if kind == "client":
        return f"export async function list{pascal(name)}("
    if kind == "guard":
        return {"session": "def require_session", "routes": "def require_route_guard"}[name]
    if kind == "provider":
        return "def oauth_start"
    if kind == "route":
        return f'export const route = "{name}"'
    if kind in ("component", "form"):
        return f"export function {name}("
    if kind == "layout":
        return "export function Shell("
    raise ValueError(f"unknown symbol {symbol!r}")


def use_token(symbol: str) -> str:
    """The exact code token that proves a task consumes `symbol`."""
    kind, name = symbol.split(":", 1)
    if kind == "table":
        return f"FROM {name}"
    if kind == "endpoint":
        return f'"{name.split(" ", 1)[1]}"'
    if kind == "client":
        return f"{name}_client"
    if kind == "guard":
        return {"session": "require_session", "routes": "require_route_guard"}[name]
    if kind == "provider":
        return "oauth_start"
    if kind == "route":
        return f'"{name}"'
    if kind in ("component", "form"):
        return f"<{name} "
    if kind == "layout":
        return "Shell"
    raise ValueError(f"unknown symbol {symbol!r}")
