"""Manager SLM: a project brief in, a ProjectPlan out. One prompt format for SFT and inference."""

from __future__ import annotations

from slm.contracts import Project, ProjectPlan
from slm.llm.base import LLMClient

_RULES = """You are the manager of a software team with four specialists:
- database: Postgres schemas (kind "schema").
- auth: cookie sessions ("session"), OAuth hand-off ("oauth"), route guard ("guards").
- network: FastAPI routers ("rest") and typed TypeScript clients ("client").
- frontend: React pages ("page"), create forms ("form"), the app shell ("layout").

Split a project brief into the tasks each specialist must do. Reply with ONLY JSON:
{"name": "<short name>", "stack": "fastapi+react+postgres", "tasks": [...]}.

Each task is {"id": "t1", "domain": <domain>, "kind": <kind>, "target": <slug>, "detail": "<one line>",
"deps": ["<earlier task id>", ...]}.

Rules:
- Every project needs work from ALL FOUR specialists; use the exact domain and kind names above.
- One "database/schema" task per table, including "users" whenever auth is used.
- One "network/rest" task per entity, plus one "network/client" task.
- One "frontend/page" task per entity, one "frontend/form", one "frontend/layout" (last).
- One "auth/session" task, "auth/oauth" only if the brief asks for OAuth, one "auth/guards" after the pages.
- "deps" lists the tasks whose outputs this task consumes (its tables, endpoints, session, pages).
  Only reference tasks listed EARLIER, so independent work can run in parallel.
- "target" is a lowercase slug: for entity work, the entity exactly as the brief names it, SINGULAR
  ("order", never "orders"); otherwise "users", "session", "oauth", "routes" or "shell".
- "users" is only a table: no REST, client, page or form task targets "users".
- "detail" is one line a specialist can act on."""


def _example() -> str:
    """One worked brief -> plan, rendered by the same generator as the gold data. Its entities (note,
    label) appear in no benchmark template, so the example never leaks a test answer."""
    from slm.bench.catalog import Template_, build_plan

    tpl = Template_("example", "notes app", "a notes app for a small team", ("note", "label"), "note", False)
    plan = build_plan(tpl).model_dump_json(exclude_none=True)
    return (f"\n\nExample. Brief entities: note, label (no OAuth). Plan:\n{plan}\n"
            "Note the singular targets (\"note\", not \"notes\") and that every dep points to an earlier task.")


MANAGER_SYSTEM = _RULES + _example()


def user_prompt(description: str) -> str:
    return f"Project brief:\n{description}\n\nPlan:"


def plan(description: str, client: LLMClient, ctx: dict | None = None) -> ProjectPlan:
    """Ask the manager for a plan. Invalid JSON/plans raise SchemaValidationFailed after one retry."""
    return client.complete(
        MANAGER_SYSTEM, user_prompt(description), ProjectPlan, caller="user", callee="manager", ctx=ctx
    )


def format_example(project: Project) -> tuple[str, str, str]:
    """(system, user, completion) for SFT and inference alike. Needs a gold plan."""
    if project.plan is None:
        raise ValueError(f"project {project.id} has no gold plan")
    return MANAGER_SYSTEM, user_prompt(project.description), project.plan.model_dump_json(exclude_none=True)
