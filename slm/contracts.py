"""FROZEN shared contracts for the manager + four-domain-specialist architecture.

The pipeline, in one line:

    project brief ─► manager SLM ─► ProjectPlan (tasks tagged by domain, with dependencies)
                                  ─► four specialist SLMs (database, auth, network, frontend)
                                  ─► integrate() ─► Deliverable (one file tree + glue + checks)

What lives here, and why it is shared:
  - Task / ProjectPlan: the manager's output and the benchmark's gold plan. `requires_of` is
    recomputed from the plan, so nobody stores interface symbols twice.
  - Artifact: one specialist's files. `check_task` proves a task's provided/consumed symbols.
  - integrate(): the deterministic integrator. Merges artifacts, generates the application glue,
    and returns a Deliverable whose `checks` are the end-to-end score.
  - specialist_system() / specialist_prompt(): the prompts each domain adapter was trained with.
  - Modal names and the Volume layout.

`slm.domains` holds the per-domain catalog (kinds, symbols, canonical paths, contract tokens);
this file holds the models and the integration rules.
"""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from slm.domains import (
    ADAPTER,
    DOMAINS,
    KINDS,
    Domain,
    canonical_path,
    detail_for,
    provides_of,
    provide_token,
    requires_of,
    use_token,
)


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


SLUG = re.compile(r"^[a-z][a-z0-9_]*$")


# --- The manager's output -----------------------------------------------------


class Task(Strict):
    """One unit of work, owned by exactly one specialist."""

    id: str = Field(description="Unique task id, e.g. 't3'")
    domain: Domain = Field(description="Which specialist does it: database | auth | network | frontend")
    kind: str = Field(description="Task kind within the domain, e.g. 'schema', 'rest', 'page'")
    target: str = Field(description="Entity or surface it is about, e.g. 'orders', 'users', 'session'")
    detail: str = Field(description="One line: what the specialist must build")
    deps: list[str] = Field(default=[], description="Ids of tasks whose outputs this task consumes")

    @model_validator(mode="after")
    def _valid(self) -> Task:
        if not SLUG.match(self.target):
            raise ValueError(f"task {self.id}: target must be a slug, got {self.target!r}")
        if self.kind not in KINDS[self.domain]:
            raise ValueError(
                f"task {self.id}: kind {self.kind!r} is not a {self.domain} kind ({KINDS[self.domain]})"
            )
        if self.id in self.deps:
            raise ValueError(f"task {self.id} depends on itself")
        return self

    @property
    def adapter_name(self) -> str:
        return ADAPTER[self.domain]

    def provides(self) -> list[str]:
        return provides_of(self.domain, self.kind, self.target)


class ProjectPlan(Strict):
    """The manager's decomposition of a project brief, or the gold plan of a benchmark item."""

    name: str = Field(description="Short project name, e.g. 'invoice tracker'")
    stack: str = Field(default="fastapi+react+postgres", description="Target stack")
    tasks: list[Task]

    @model_validator(mode="after")
    def _well_formed(self) -> ProjectPlan:
        ids = [t.id for t in self.tasks]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate task ids")
        seen: set[str] = set()
        for t in self.tasks:  # tasks must be topologically ordered
            for d in t.deps:
                if d not in seen:
                    raise ValueError(f"task {t.id} depends on {d!r} before it is defined")
            seen.add(t.id)
        missing = [d for d in DOMAINS if not any(t.domain == d for t in self.tasks)]
        if missing:
            raise ValueError(
                f"a plan must use all four specialists; no tasks for {missing}. "
                "Every project needs database, auth, network and frontend work."
            )
        return self

    def levels(self) -> list[list[str]]:
        """Task ids grouped into dependency levels; every task in a level can be dispatched at once."""
        level: dict[str, int] = {}
        for t in self.tasks:
            level[t.id] = 1 + max((level[d] for d in t.deps), default=-1)
        out: list[list[str]] = [[] for _ in range(max(level.values(), default=-1) + 1)]
        for tid, lv in level.items():
            out[lv].append(tid)
        return out

    def providers(self) -> dict[str, str]:
        """symbol -> the task id that exports it (first provider wins)."""
        out: dict[str, str] = {}
        for t in self.tasks:
            for s in t.provides():
                out.setdefault(s, t.id)
        return out

    def routes(self) -> tuple[str, ...]:
        return tuple(
            s.split(":", 1)[1] for s in self.providers() if s.startswith("route:")
        )

    def components(self) -> tuple[str, ...]:
        return tuple(s.split(":", 1)[1] for s in self.providers() if s.startswith("component:"))

    def task(self, tid: str) -> Task:
        return next(t for t in self.tasks if t.id == tid)

    def requires(self, task: Task) -> list[str]:
        """What `task` consumes, with the plan's page surfaces filled in for the layout/guards."""
        return requires_of(
            task.domain, task.kind, task.target,
            routes=self.routes() if task.kind == "layout" else (),
            components=self.components() if task.kind == "layout" else (),
        )


# --- Specialist output --------------------------------------------------------


class ArtifactFile(Strict):
    path: str = Field(description="Repository-relative path, e.g. src/network/orders_api.py")
    content: str


class Artifact(Strict):
    """One specialist's deliverable for one task. The model returns only files + a summary."""

    files: list[ArtifactFile]
    summary: str = Field(default="", description="One line on what was built")


class Check(Strict):
    name: str
    ok: bool
    detail: str = ""


class Deliverable(Strict):
    """The integrated final product handed to the user."""

    project_id: str
    entry: str
    files: list[ArtifactFile]
    wiring: list[str] = []
    checks: list[Check] = []

    @property
    def ok(self) -> bool:
        return bool(self.checks) and all(c.ok for c in self.checks)

    @property
    def failures(self) -> list[str]:
        return [c.name for c in self.checks if not c.ok]

    def read(self, path: str) -> str | None:
        return next((f.content for f in self.files if f.path == path), None)


# --- Task-level contract checking --------------------------------------------


def check_task(plan: ProjectPlan, task: Task, artifact: Artifact) -> list[Check]:
    """A task is done when its primary file exists and it exports/consumes every symbol it promised."""
    checks: list[Check] = []
    want = canonical_path(task.domain, task.kind, task.target)
    paths = [f.path for f in artifact.files]
    checks.append(Check(
        name=f"layout:{task.id}", ok=want in paths,
        detail="" if want in paths else f"expected {want}, got {paths[:3]}",
    ))
    text = artifact.files[paths.index(want)].content if want in paths else \
        "\n".join(f.content for f in artifact.files)
    for sym in provides_of(task.domain, task.kind, task.target):
        tok = provide_token(sym)
        checks.append(Check(name=f"provides:{task.id}:{sym}", ok=tok in text,
                            detail="" if tok in text else f"missing {tok!r}"))
    for sym in plan.requires(task):
        tok = use_token(sym)
        checks.append(Check(name=f"uses:{task.id}:{sym}", ok=tok in text,
                            detail="" if tok in text else f"missing {tok!r}"))
    return checks


def task_ok(plan: ProjectPlan, task: Task, artifact: Artifact) -> tuple[bool, str]:
    """(ok, first failure name) - what the dispatcher records on the trace."""
    checks = check_task(plan, task, artifact)
    bad = [c for c in checks if not c.ok]
    return (not bad, "" if not bad else bad[0].name + (": " + bad[0].detail if bad[0].detail else ""))


# --- Integration --------------------------------------------------------------


def _pascal_safe(slug: str) -> str:
    return "".join(p[:1].upper() + p[1:] for p in slug.split("_"))


def app_files(plan: ProjectPlan) -> list[ArtifactFile]:
    """Glue the integrator writes so the artifacts become one runnable application."""
    rest = [t for t in plan.tasks if t.domain == "network" and t.kind == "rest"]
    has_session = any(t.domain == "auth" and t.kind == "session" for t in plan.tasks)
    has_guards = any(t.domain == "auth" and t.kind == "guards" for t in plan.tasks)
    has_db = any(t.domain == "database" for t in plan.tasks)
    has_pages = any(t.kind == "page" for t in plan.tasks)

    lines = ["from fastapi import FastAPI"]
    if has_session:
        lines.append("from src.auth.session import require_session")
    if has_guards:
        lines.append("from src.auth.guards import require_route_guard")
    if has_db:
        lines += ["from src.database.db import db"]
    for t in rest:
        lines.append(f"from src.network.{t.target}_api import router as {t.target}_router")
    lines += ["", f'app = FastAPI(title="{plan.name}")']
    if has_guards:
        lines.append('app.middleware("http")(require_route_guard)')
    for t in rest:
        lines.append(f"app.include_router({t.target}_router)")
    if has_pages:
        lines += ["", "# Frontend pages are built from src/frontend/ and served as static assets."]
    app_py = "\n".join(lines) + "\n"

    files = [
        ArtifactFile(path="src/app.py", content=app_py),
        ArtifactFile(
            path="src/main.py",
            content="import uvicorn\n\nfrom src.app import app\n\n"
                    'if __name__ == "__main__":\n    uvicorn.run(app, host="0.0.0.0", port=8000)\n',
        ),
        ArtifactFile(
            path="requirements.txt",
            content="fastapi\nuvicorn\nasyncpg\n",
        ),
    ]
    if has_db:
        files.append(ArtifactFile(
            path="src/database/db.py",
            content=(
                "import asyncio\nimport os\n\nimport asyncpg\n\n"
                'DSN = os.environ.get("DATABASE_URL", "postgresql://localhost/app")\n\n\n'
                "class Database:\n"
                '    """Connects on first use, because a pool has to be created inside a running event loop."""\n\n'
                "    def __init__(self):\n"
                "        self._pool = None\n"
                "        self._lock = asyncio.Lock()\n\n"
                "    async def _connected(self):\n"
                "        async with self._lock:\n"
                "            if self._pool is None:\n"
                "                self._pool = await asyncpg.create_pool(DSN)\n"
                "        return self._pool\n\n"
                "    async def fetch(self, sql: str, *args) -> list[dict]:\n"
                "        pool = await self._connected()\n"
                "        return [dict(row) for row in await pool.fetch(sql, *args)]\n\n"
                "    async def fetchrow(self, sql: str, *args) -> dict | None:\n"
                "        pool = await self._connected()\n"
                "        row = await pool.fetchrow(sql, *args)\n"
                "        return dict(row) if row else None\n\n\n"
                "db = Database()\n"
            ),
        ))
    by_domain: dict[str, list[str]] = {}
    for t in plan.tasks:
        by_domain.setdefault(t.domain, []).append(t.id)
    readme = [f"# {plan.name}", "", f"Stack: {plan.stack}", "", "## Tasks"]
    readme += [f"- `{t.id}` [{t.domain}/{t.kind}] {t.detail}" for t in plan.tasks]
    readme += ["", "## Domains"] + [f"- {d}: {', '.join(v)}" for d, v in by_domain.items()]
    files.append(ArtifactFile(path="README.md", content="\n".join(readme) + "\n"))
    return files


_IMPORT = re.compile(r"^from (src[\w.]*) import", re.MULTILINE)


def integrate(project_id: str, plan: ProjectPlan, artifacts: dict[str, Artifact], *,
              host_kinds: frozenset[str] = frozenset()) -> Deliverable:
    """Merge the four specialists' artifacts, add glue, and check the seams between domains.

    Tasks of `host_kinds` are delivered by something other than a specialist (Minerva's frontend agent and integrator),
    so they are not expected here. They stay in the plan, because other tasks read the plan's routes and symbols."""
    files: dict[str, str] = {}
    conflicts: set[str] = set()
    wiring: list[str] = []
    for t in plan.tasks:
        art = artifacts.get(t.id)
        if art is None:
            continue
        for f in art.files:
            if f.path in files and files[f.path] != f.content:
                conflicts.add(f.path)
            files.setdefault(f.path, f.content)

    checks: list[Check] = []

    missing = [t.id for t in plan.tasks if t.kind not in host_kinds
               and (not artifacts.get(t.id) or not artifacts[t.id].files)]
    checks.append(Check(name="all_tasks_delivered", ok=not missing, detail=", ".join(missing)))
    checks.append(Check(name="no_path_conflicts", ok=not conflicts, detail=", ".join(sorted(conflicts))))

    for t in plan.tasks:
        art = artifacts.get(t.id)
        if art is not None and t.kind not in host_kinds:
            checks.extend(check_task(plan, t, art))

    providers = plan.providers()
    unsatisfied = [f"{t.id}->{s}" for t in plan.tasks for s in plan.requires(t) if s not in providers]
    checks.append(Check(name="requires_satisfied", ok=not unsatisfied, detail=", ".join(unsatisfied)))
    for t in plan.tasks:
        for s in plan.requires(t):
            if s in providers:
                wiring.append(f"{t.id} <- {providers[s]} via {s}")

    endpoints = {s.split(" ", 1)[1] for s in providers if s.startswith("endpoint:")}
    used = {
        m for path, content in files.items() if path.startswith("src/frontend/")
        for m in re.findall(r'"(/api/[^"]+)"', content)
    }
    unresolved = sorted(used - endpoints)
    checks.append(Check(name="frontend_endpoints_resolve", ok=not unresolved,
                        detail=", ".join(unresolved)))

    tables = {s.split(":", 1)[1] for s in providers if s.startswith("table:")}
    referenced: set[str] = set()
    for path, content in files.items():
        if path.startswith(("src/network/", "src/auth/")):
            referenced |= set(re.findall(r"(?:FROM|INTO|REFERENCES)\s+([a-z_][a-z0-9_]*)", content))
    undefined = sorted(referenced - tables)
    checks.append(Check(name="tables_defined", ok=not undefined, detail=", ".join(undefined)))

    glue = app_files(plan)
    for f in glue:
        files.setdefault(f.path, f.content)
    checks.append(Check(name="app_glue_present", ok="src/app.py" in files and "src/main.py" in files))

    def exists(module: str) -> bool:
        base = module.replace(".", "/")
        return f"{base}.py" in files or any(p.startswith(base + "/") for p in files)

    broken = sorted({m for path, content in files.items() if path.endswith(".py")
                     for m in _IMPORT.findall(content) if not exists(m)})
    checks.append(Check(name="imports_resolve", ok=not broken, detail=", ".join(broken)))

    if any(t.kind == "guards" for t in plan.tasks):
        guarded = any("require_route_guard" in c for p, c in files.items() if p == "src/app.py")
        checks.append(Check(name="guards_wired", ok=guarded))

    return Deliverable(
        project_id=project_id,
        entry="src/main.py",
        files=[ArtifactFile(path=p, content=c) for p, c in sorted(files.items())],
        wiring=wiring,
        checks=checks,
    )


# --- Specialist prompts: identical at train and serve time --------------------


def specialist_system(domain: Domain) -> str:
    """The specialist's system prompt, rendered from its definition in slm/specialists.py."""
    from slm.specialists import system_prompt

    return system_prompt(domain)


def specialist_prompt(plan: ProjectPlan, task: Task) -> str:
    """Everything the specialist needs: the brief, its task, its interfaces and its teammates'."""
    mine_in = "\n".join(f"- {s} (use token: {use_token(s)})" for s in plan.requires(task)) or "- none"
    mine_out = "\n".join(f"- {s} (provide token: {provide_token(s)})" for s in task.provides())
    team = "\n".join(
        f"- {t.id} [{t.domain}/{t.kind}] {t.target}: {', '.join(t.provides())}"
        for t in plan.tasks if t.id != task.id
    ) or "- none"
    path = canonical_path(task.domain, task.kind, task.target)
    return (
        f"Project: {plan.name} (stack: {plan.stack})\n"
        f"Your task {task.id} [{task.domain}/{task.kind}] on `{task.target}`: {task.detail}\n"
        f"Write the primary file at exactly: {path}\n"
        f"Interfaces you must consume:\n{mine_in}\n"
        f"Interfaces you must provide:\n{mine_out}\n"
        f"The rest of the team provides:\n{team}\n"
        "Return only the files for your task."
    )


class TrainExample(Strict):
    """One line of a per-domain training file written by WS1 (slm/bench/build.py), read by WS2."""

    domain: Domain
    kind: str
    target: str | None = None  # entity/surface; lets the trainer score a produced artifact offline
    prompt: str
    completion: str  # Artifact(...).model_dump_json()
    split: Literal["train", "eval"]
    project_id: str | None = None


# --- Benchmark items ----------------------------------------------------------


class Project(Strict):
    """One benchmark item: a brief for the manager plus the gold plan the specialists were trained on."""

    id: str
    source: Literal["synthetic"]
    split: Literal["train", "dev", "test"]
    description: str
    plan: ProjectPlan | None = None  # gold plan
    n_tasks: int | None = None
    depth: int | None = None  # dependency levels in the gold plan
    template_id: str | None = None


# --- Modal ------------------------------------------------------------------

MODAL_VOLUME = "slm-vol"  # v2 Volume, mounted at /vol
VOL = "/vol"
BASE_MODEL = "Qwen/Qwen3-0.6B"  # every domain specialist is a LoRA on this base
MANAGER_BASE = "Qwen/Qwen3-1.7B"  # the manager plans on a slightly bigger base
PATHS = {
    "projects": "/vol/data/projects/{name}.jsonl",  # Project lines
    "manager_data": "/vol/data/manager/{name}.jsonl",  # {system, prompt, completion} rows
    "domain_data": "/vol/data/domains/{name}.jsonl",  # TrainExample lines, one file per domain
    "adapter": "/vol/adapters/{seed}/{adapter_name}",  # PEFT dir, bf16
    "registry": "/vol/adapters/registry.json",  # list[RegistryEntry]
    "manager": "/vol/manager/{run}",
    "traces": "/vol/traces/{run_id}.jsonl",
    "results": "/vol/results/{name}.json",
}


class RegistryEntry(Strict):
    adapter_name: str
    domain: str
    seed: int
    path: str
    train_examples: int
    gate_task_ok: float  # held-out share of tasks whose artifact passes check_task
    train_seconds: float
    gpu: str
    data_version: int | None = None
    escalated: bool = False
