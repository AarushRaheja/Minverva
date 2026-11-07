"""What the backend really offers the frontend, derived from the plan by code rather than by a model."""

from __future__ import annotations

from dataclasses import dataclass

from slm.contracts import ProjectPlan
from slm.domains import api_base, page_route, pascal, plural
from slm.manager.spec import ProjectSpec, gold_spec, normalize_spec, to_plan
from slm.domains import detail_for

# Postgres rejects these as bare table names, and the manager does emit them (`order`, `case`, `analysis`).
RESERVED_TABLES = frozenset({
    "all", "analyse", "analysis", "and", "any", "array", "as", "asc", "case", "cast", "check", "collate", "column",
    "constraint", "create", "default", "desc", "distinct", "do", "else", "end", "except", "false", "for", "foreign",
    "from", "grant", "group", "having", "in", "into", "limit", "not", "null", "offset", "on", "only", "or", "order",
    "placing", "primary", "references", "select", "table", "then", "to", "true", "union", "unique", "user", "using",
    "when", "where", "window", "with",
})
_ENTITY_KINDS = {"schema", "rest", "client", "page", "form"}


@dataclass(frozen=True)
class Entity:
    slug: str

    @property
    def pascal(self) -> str:
        return pascal(self.slug)

    @property
    def base(self) -> str:
        return api_base(self.slug)

    @property
    def route(self) -> str:
        return page_route(self.slug)

    @property
    def tid(self) -> str:
        return self.slug.replace("_", "-")

    @property
    def label(self) -> str:
        return plural(self.slug).replace("_", " ").title()


@dataclass(frozen=True)
class AppContract:
    name: str
    brief: str
    entities: tuple[Entity, ...]
    primary: Entity  # the entity the manager's form creates: first in the navigation
    look: str = ""  # "how should it look": read only by the frontend pipeline, never by the manager

    @property
    def guarded_pages(self) -> tuple[str, ...]:
        return tuple(e.route for e in self.entities)


def prepare_spec(raw: str) -> ProjectSpec:
    """Validate the manager's output and repair what code can repair: OAuth, plurals, reserved table names."""
    spec = normalize_spec(ProjectSpec.model_validate_json(raw))
    plan = to_plan(spec)

    def fixed(kind: str, target: str) -> str:
        return f"{target}_record" if kind in _ENTITY_KINDS and target in RESERVED_TABLES else target

    if all(fixed(t.kind, t.target) == t.target for t in plan.tasks):
        return spec
    tasks = [t.model_copy(update={"target": fixed(t.kind, t.target),
                                  "detail": detail_for(t.domain, t.kind, fixed(t.kind, t.target))})
             for t in plan.tasks]
    return gold_spec(ProjectPlan(name=plan.name, stack=plan.stack, tasks=tasks))


def contract_from_plan(plan: ProjectPlan, brief: str, look: str = "") -> AppContract:
    entities = tuple(Entity(t.target) for t in plan.tasks if t.domain == "network" and t.kind == "rest")
    if not entities:
        raise ValueError("the plan has no REST entity, so there is nothing for a frontend to show")
    form = next((t.target for t in plan.tasks if t.kind == "form"), entities[0].slug)
    primary = next((e for e in entities if e.slug == form), entities[0])
    return AppContract(name=plan.name, brief=brief, entities=entities, primary=primary, look=look.strip())


def render_api_client(contract: AppContract) -> str:
    """frontend/src/api.ts. The compiler then rejects a UI that invents a field or an endpoint."""
    lines = [
        "// Written by the integrator from the backend's real endpoints. The UI's only route to the server.",
        "export type Row = { id: number; owner_id: number; title: string; created_at: string };",
        "export type User = { id: number; email: string };",
        "",
        "export class ApiError extends Error {",
        "  constructor(message: string, readonly status: number) {",
        "    super(message);",
        "  }",
        "}",
        "",
        "async function request<T>(path: string, init?: RequestInit): Promise<T> {",
        "  const response = await fetch(path, {",
        "    credentials: \"same-origin\",",
        "    headers: init?.body ? { \"Content-Type\": \"application/json\" } : undefined,",
        "    ...init,",
        "  });",
        "  if (!response.ok) {",
        "    const body = await response.json().catch(() => null);",
        "    throw new ApiError(body?.detail ?? `Request failed (${response.status})`, response.status);",
        "  }",
        "  return response.json();",
        "}",
        "",
        "export async function currentUser(): Promise<User | null> {",
        "  return (await request<{ user: User | null }>(\"/api/auth/me\")).user;",
        "}",
        "",
        "export async function signIn(email: string, password: string): Promise<User> {",
        "  return request<User>(\"/api/auth/login\", { method: \"POST\", body: JSON.stringify({ email, password }) });",
        "}",
        "",
        "export async function signUp(email: string, password: string): Promise<User> {",
        "  return request<User>(\"/api/auth/signup\", { method: \"POST\", body: JSON.stringify({ email, password }) });",
        "}",
        "",
        "/** Ends the session, then reloads, which shows the sign-in form. */",
        "export async function signOut(): Promise<void> {",
        "  await request(\"/api/auth/logout\", { method: \"POST\" });",
        "  window.location.reload();",
        "}",
    ]
    for e in contract.entities:
        lines += [
            "",
            f"export type {e.pascal} = Row;",
            "",
            f"export async function list{e.pascal}(): Promise<{e.pascal}[]> {{",
            f"  return request<{e.pascal}[]>(\"{e.base}\");",
            "}",
            "",
            f"export async function create{e.pascal}(title: string): Promise<{e.pascal}> {{",
            f"  return request<{e.pascal}>(\"{e.base}\", {{ method: \"POST\", body: JSON.stringify({{ title }}) }});",
            "}",
            "",
            f"export async function get{e.pascal}(id: number): Promise<{e.pascal}> {{",
            f"  return request<{e.pascal}>(`{e.base}/${{id}}`);",
            "}",
        ]
    return "\n".join(lines) + "\n"
