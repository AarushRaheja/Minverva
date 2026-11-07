"""Baselines for the four-specialist pipeline.

- monolith: ONE model call writes the whole project (no manager, no specialists). Its files are
  attributed to tasks by canonical path and graded with the same integrator, so the comparison
  isolates what the decomposition plus specialization buys.
- single: one generalist model serves every task of the manager's plan (`single_clients`), i.e.
  the pipeline without domain specialization.
"""

from __future__ import annotations

import time
from typing import Literal

from pydantic import BaseModel, Field

from slm.contracts import (
    Artifact, ArtifactFile, Deliverable, Project, ProjectPlan, Strict, integrate,
)
from slm.domains import DOMAINS, canonical_path
from slm.llm.base import LLMClient, SchemaValidationFailed
from slm.trace import Tracer

Mode = Literal["monolith"]

SYSTEM = """You are a senior full-stack engineer. Build the whole product in one pass.
Reply with only JSON: {"files": [{"path": "<path>", "content": "<file>"}], "summary": "<one line>"}.

Layout:
- src/database/<table>.sql          Postgres schema: CREATE TABLE <table>
- src/auth/session.py               cookie sessions: def require_session
- src/auth/guards.py                route guard: def require_route_guard
- src/network/<entity>_api.py       FastAPI router: @router.get("/api/<entities>") handlers
- src/network/<entity>_client.ts    typed client: export async function list<Entity>
- src/frontend/<Entity>Page.tsx     React page: export const route = "/<entities>"
Include every table, endpoint, page and form the brief asks for."""


class MonolithProject(Strict):
    files: list[ArtifactFile]
    summary: str = Field(default="", description="One line on what was built")


def files_to_artifacts(plan: ProjectPlan, files: list[ArtifactFile]) -> dict[str, Artifact]:
    """Attribute a flat file list to tasks by canonical path; unmatched files are dropped."""
    by_path = {f.path: f for f in files}
    out: dict[str, Artifact] = {}
    for t in plan.tasks:
        want = canonical_path(t.domain, t.kind, t.target)
        if want in by_path:
            out[t.id] = Artifact(files=[by_path[want]], summary="monolith")
    return out


def run_monolith(
    projects: list[Project], client: LLMClient, tracer: Tracer | None = None,
) -> list[Deliverable]:
    """One call per project; graded through integrate() against the project's gold plan."""
    if tracer is not None:
        client.tracer = tracer
    out: list[Deliverable] = []
    for p in projects:
        t0 = time.time()
        if p.plan is None:
            raise ValueError(f"project {p.id} has no gold plan to grade against")
        ctx = {"mode": "monolith", "project_id": p.id}
        try:
            got = client.complete(SYSTEM, f"Project brief:\n{p.description}", MonolithProject,
                                  caller="user", callee="monolith", ctx=ctx)
            artifacts = files_to_artifacts(p.plan, got.files)
            deliverable = integrate(p.id, p.plan, artifacts)
            error = None
        except (SchemaValidationFailed, ValueError) as e:
            deliverable = integrate(p.id, p.plan, {})
            error = f"{type(e).__name__}: {e}"[:300]
        if tracer is not None:
            output = "pass" if deliverable.ok else f"fail:{deliverable.failures[0]}"
            tracer.record(kind="final", caller="user", callee="monolith", mode="monolith",
                          project_id=p.id, ok=error is None, error=error,
                          output=None if error else output,
                          t_start=t0, t_end=time.time(), model=client.model)
        out.append(deliverable)
    return out


def single_clients(client: LLMClient) -> dict[str, LLMClient]:
    """The 'single generalist' arm: every domain is served by the same client."""
    return {d: client for d in DOMAINS}
