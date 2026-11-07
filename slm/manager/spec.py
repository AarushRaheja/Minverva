"""The nested project spec: a brief becomes domains > groups > tasks > steps, with tests at each level.

    ProjectSpec          architecture, system tests
      DomainSpec         database | auth | network | frontend: summary, integration tests
        TaskGroup        a subheading, e.g. "REST APIs"
          SpecTask       one specialist's unit of work: acceptance criteria, dependencies
            Step         one interface symbol to deliver, with one unit test

The nesting has fixed depth, not recursion, so its size is predictable for a small model.

Only SpecTasks are executed. `to_plan` compiles a spec to the existing ProjectPlan: canonical order,
t1..tN ids. Specialist prompts contain those ids and that order, so for gold data
`to_plan(gold_spec(plan)) == plan` exactly, and the specialists, dispatcher and integrator are
untouched. Tests name the symbols they verify, so test coverage can be checked by a program.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from slm.contracts import ProjectPlan, Strict, Task
from slm.domains import (
    DOMAINS, Domain, api_base, canonical_path, detail_for, page_route, pascal, plural, provide_token, provides_of,
    use_token,
)
from slm.manager.score import PlanScore, score_plan

PREFIX: dict[str, str] = {"database": "DB", "auth": "AUTH", "network": "NET", "frontend": "FE"}

# Where each kind sits in the canonical ProjectPlan (the order slm.bench.catalog.build_plan adds them).
_RANK = {"schema": 0, "session": 1, "oauth": 2, "rest": 3, "client": 4, "page": 5, "form": 6,
         "guards": 7, "layout": 8}


class SpecTest(Strict):
    id: str
    scope: Literal["unit", "integration", "system"]
    description: str
    preconditions: list[str] = Field(default=[], description="State required before the test runs")
    expected: str
    verifies: list[str] = Field(min_length=1, description="Interface symbols this test exercises")


class Step(Strict):
    id: str = Field(description="Hierarchical id, e.g. NET-1.1.2")
    heading: str
    test: SpecTest


class SpecTask(Strict):
    id: str = Field(description="Hierarchical id, e.g. NET-1.1")
    kind: str
    target: str
    detail: str
    acceptance: str = Field(description="Measurable criterion for calling this task done")
    deps: list[str] = Field(default=[], description="Ids of earlier tasks this task consumes")
    steps: list[Step] = Field(min_length=1)


class TaskGroup(Strict):
    id: str = Field(description="Hierarchical id, e.g. NET-1")
    heading: str
    tasks: list[SpecTask] = Field(min_length=1)


class DomainSpec(Strict):
    summary: str
    integration_tests: list[SpecTest] = Field(min_length=1)
    groups: list[TaskGroup] = Field(min_length=1)


class ProjectSpec(Strict):
    name: str
    stack: str = "fastapi+react+postgres"
    architecture: str
    system_tests: list[SpecTest] = Field(min_length=1)
    database: DomainSpec
    auth: DomainSpec
    network: DomainSpec
    frontend: DomainSpec

    def domain(self, name: str) -> DomainSpec:
        return getattr(self, name)

    def tasks(self) -> list[tuple[Domain, SpecTask]]:
        return [(d, t) for d in DOMAINS for g in self.domain(d).groups for t in g.tasks]  # type: ignore[misc]


# --- Removing OAuth ------------------------------------------------------------


def without_oauth_plan(plan: ProjectPlan) -> ProjectPlan:
    """The plan with OAuth tasks removed and t1..tN renumbered. Nothing else changes."""
    kept = [t for t in plan.tasks if t.kind != "oauth"]
    if len(kept) == len(plan.tasks):
        return plan
    new_id = {t.id: f"t{i}" for i, t in enumerate(kept, 1)}
    tasks = [t.model_copy(update={"id": new_id[t.id], "deps": sorted(new_id[d] for d in t.deps if d in new_id)})
             for t in kept]
    return ProjectPlan(name=plan.name, stack=plan.stack, tasks=tasks)


def without_oauth(spec: ProjectSpec) -> ProjectSpec:
    """Remove OAuth from a spec and keep the manager's own text and tests everywhere else."""
    data = spec.model_dump()
    removed = {t["id"] for g in data["auth"]["groups"] for t in g["tasks"] if t["kind"] == "oauth"}
    removed |= {t["id"] for d in DOMAINS for g in data[d]["groups"] for t in g["tasks"] if t["kind"] == "oauth"}

    def keep_tests(tests: list[dict]) -> list[dict]:
        kept = []
        for test in tests:
            verifies = [s for s in test["verifies"] if not s.startswith("provider:")]
            if verifies:
                kept.append({**test, "verifies": verifies})
        return kept

    data["system_tests"] = keep_tests(data["system_tests"]) or data["system_tests"]
    for d in DOMAINS:
        section = data[d]
        section["integration_tests"] = keep_tests(section["integration_tests"]) or section["integration_tests"]
        for group in section["groups"]:
            group["tasks"] = [t for t in group["tasks"] if t["kind"] != "oauth"]
            for task in group["tasks"]:
                task["deps"] = [x for x in task["deps"] if x not in removed]
        section["groups"] = [g for g in section["groups"] if g["tasks"]]
    return ProjectSpec.model_validate(data)


# --- Repairing plural targets --------------------------------------------------

_ENTITY_KINDS = {"schema", "rest", "client", "page", "form"}
_RESERVED_TARGETS = {"users", "session", "oauth", "routes", "shell"}


def singular(word: str) -> str:
    """campers -> camper, boxes -> box. A word that only looks plural (status, boss) is left alone."""
    if not word.endswith("s") or word.endswith(("ss", "us", "is")):
        return word
    stem = word[:-2] if word.endswith(("sses", "xes", "ches")) else word[:-1]
    return stem if plural(stem) == word else word


def normalize_spec(spec: ProjectSpec) -> ProjectSpec:
    """Remove OAuth, then repair plural targets and a form that disagrees with the client.

    The manager copies plurals from the brief, and downstream names derive from the target:
    `campers` becomes `/api/camperses` in the plan while the specialist writes `/api/campers`, and the
    parts stop connecting. Its text can also mix both forms, so a repaired plan keeps the manager's tasks
    and dependencies but has its text rewritten by `gold_spec`. A plan with no plural target is untouched.
    """
    spec = without_oauth(spec)
    plan = to_plan(spec)
    client = next((singular(t.target) for t in plan.tasks if t.kind == "client"), None)

    def fixed(t: Task) -> str:
        if t.kind == "form" and client:  # a form can only use the client that exists
            return client
        return singular(t.target) if t.kind in _ENTITY_KINDS and t.target not in _RESERVED_TARGETS else t.target

    if all(fixed(t) == t.target for t in plan.tasks):
        return spec
    tasks = [t.model_copy(update={"target": fixed(t), "detail": detail_for(t.domain, t.kind, fixed(t))})
             for t in plan.tasks]
    return gold_spec(ProjectPlan(name=plan.name, stack=plan.stack, tasks=tasks))


# --- Spec -> the plan the dispatcher runs -------------------------------------


def to_plan(spec: ProjectSpec) -> ProjectPlan:
    """Compile to a ProjectPlan. Raises ValueError for unknown deps, bad kinds or a bad order."""
    pairs = spec.tasks()
    ordered = sorted(pairs, key=lambda p: _RANK.get(p[1].kind, len(_RANK)))  # sorted() is stable
    new_id = {t.id: f"t{i}" for i, (_, t) in enumerate(ordered, 1)}
    if len(new_id) != len(pairs):
        raise ValueError("duplicate task ids in spec")
    tasks = []
    for domain, t in ordered:
        unknown = [d for d in t.deps if d not in new_id]
        if unknown:
            raise ValueError(f"task {t.id} depends on unknown task(s) {unknown}")
        tasks.append(Task(id=new_id[t.id], domain=domain, kind=t.kind, target=t.target,
                          detail=t.detail, deps=sorted(new_id[d] for d in t.deps)))
    return ProjectPlan(name=spec.name, stack=spec.stack, tasks=tasks)


# --- Spec -> the prompt each specialist receives ------------------------------


def task_ids(spec: ProjectSpec) -> dict[str, str]:
    """Spec task id -> the t1..tN id `to_plan` gives it."""
    ordered = sorted(spec.tasks(), key=lambda p: _RANK.get(p[1].kind, len(_RANK)))
    return {t.id: f"t{i}" for i, (_, t) in enumerate(ordered, 1)}


def _steps_text(task: SpecTask) -> str:
    lines = []
    for step in task.steps:
        lines.append(f"- {step.id} {step.heading}")
        if step.test.preconditions:
            lines.append(f"  Given: {'; '.join(step.test.preconditions)}")
        lines.append(f"  Test: {step.test.description}")
        lines.append(f"  Expected: {step.test.expected}")
    return "\n".join(lines)


def spec_task_prompts(spec: ProjectSpec) -> dict[str, str]:
    """Plan task id -> its specialist's prompt: one task from that specialist's category.

    It holds the task, its subtasks and their tests, and the few interface names the task connects
    to. Nothing about other tasks is included.
    """
    plan = to_plan(spec)
    ids = task_ids(spec)
    prompts = {}
    for domain, task in spec.tasks():
        flat = plan.task(ids[task.id])
        consume = "\n".join(f"- {s} (use token: {use_token(s)})" for s in plan.requires(flat)) or "- none"
        provide = "\n".join(f"- {s} (provide token: {provide_token(s)})" for s in flat.provides())
        # The guard's job is the page routes, which no other interface in its prompt names.
        routes = f"Page routes to protect: {', '.join(plan.routes())}\n" if task.kind == "guards" else ""
        prompts[flat.id] = (
            f"Project: {spec.name} (stack: {spec.stack})\n"
            f"Your task {task.id} [{domain}/{task.kind}] on `{task.target}`: {task.detail}\n"
            f"Write the primary file at exactly: {canonical_path(domain, task.kind, task.target)}\n"
            f"Done when: {task.acceptance}\n"
            f"Subtasks:\n{_steps_text(task)}\n"
            f"Interfaces you must consume:\n{consume}\n"
            f"Interfaces you must provide:\n{provide}\n"
            f"{routes}"
            "Return only the files for your task."
        )
    return prompts


# --- Gold spec: deterministic and true of the gold artifacts ------------------


def _a(noun: str) -> str:
    """'a receipt', 'an assessment'. Entity slugs in the catalog have regular vowel sounds."""
    return f"{'an' if noun[0] in 'aeiou' else 'a'} {noun.replace('_', ' ')}"


def _step_text(sym: str) -> tuple[str, str, list[str], str]:
    """(heading, test description, preconditions, expected) for one provided symbol."""
    kind, name = sym.split(":", 1)
    if kind == "table":
        cols = "email and session_token" if name == "users" else "owner_id and created_at"
        pre = [] if name == "users" else ["The users table exists"]
        return (f"Create the {name} table", f"Apply the {name} schema to a database.", pre,
                f"CREATE TABLE {name} succeeds and the table has {cols} columns.")
    if kind == "endpoint":
        method, path = name.split(" ", 1)
        if path.endswith("{item_id}"):
            return (f"Fetch one row at {path}", f"Send GET {path} with the id of an existing row.",
                    ["A row exists"], "The response is the row with that id.")
        if method == "POST":
            return (f"Create rows at {path}", f"Send POST {path} with a title and a valid session.",
                    ["A signed-in user"], "The response is the new row, owned by the session user.")
        return (f"List rows at {path}", f"Send GET {path} when two rows exist.",
                ["Two rows exist"], "The response lists both rows, newest id first.")
    if kind == "client":
        p = pascal(name)
        return (f"Typed client for {name}", f"Call list{p} and create{p} against a stubbed fetch.",
                [], f"list{p} sends GET {api_base(name)} and create{p} sends POST {api_base(name)}.")
    if kind == "guard" and name == "session":
        return ("Session dependency", "Call require_session without the app_session cookie.", [],
                "require_session raises an HTTPException with status 401.")
    if kind == "guard":
        return ("Route guard", "Request a protected route with no session cookie.", [],
                "require_route_guard calls require_session and the request gets a 401 response.")
    if kind == "provider":
        return ("OAuth start", "Call oauth_start with a request.", [],
                "oauth_start returns a redirect to the provider's authorize URL.")
    if kind == "route":
        return (f"Page route {name}", "Import the page module.", [],
                f'The module exports route = "{name}".')
    if kind == "component":
        return (f"{name} component", f"Render {name} with a stubbed fetch returning two rows.", [],
                f"{name} renders one list item per row.")
    if kind == "form":
        return (f"{name} component", f"Submit {name} with a title.", [],
                f"{name} calls the typed client's create function once.")
    if kind == "layout":
        return ("App shell", "Render Shell.", [], "Shell links every page and renders each page component.")
    raise ValueError(f"unknown symbol {sym!r}")


def _groups_of(domain: str, tasks: list[Task]) -> list[tuple[str, list[Task]]]:
    """Fixed subheadings per domain; a group with no tasks is left out."""
    of = lambda *kinds: [t for t in tasks if t.kind in kinds]  # noqa: E731
    if domain == "database":
        return [("Accounts", [t for t in tasks if t.target == "users"]),
                ("Domain tables", [t for t in tasks if t.target != "users"])]
    if domain == "auth":
        return [("Sign-in", of("session", "oauth")), ("Route protection", of("guards"))]
    if domain == "network":
        return [("REST APIs", of("rest")), ("Typed clients", of("client"))]
    return [("Pages", of("page")), ("Forms", of("form")), ("App shell", of("layout"))]


def _acceptance(plan: ProjectPlan, t: Task) -> str:
    return (f"{canonical_path(t.domain, t.kind, t.target)} exists, provides {len(t.provides())} and "
            f"consumes {len(plan.requires(t))} interface symbols, and check_task reports no failures.")


def _integration_test(domain: str, plan: ProjectPlan) -> SpecTest:
    prefix = PREFIX[domain]
    syms = [s for t in plan.tasks if t.domain == domain for s in t.provides()]
    form = next(t.target for t in plan.tasks if t.kind == "form")
    if domain == "database":
        desc, pre = "Apply every schema file, with users first.", []
        exp = f"All {len(syms)} tables exist and every owner_id references users."
    elif domain == "auth":
        desc, pre = "Request a protected route with and without a valid session cookie.", ["A signed-in user"]
        exp = "The signed-in request succeeds and the signed-out request is rejected."
    elif domain == "network":
        base = api_base(form)
        syms = [f"client:{form}", f"endpoint:POST {base}", f"endpoint:GET {base}"]
        desc, pre = f"Create {_a(form)} through the typed client, then list {base}.", ["A signed-in user"]
        exp = f"The new {form} appears in the list response."
    else:
        desc, pre = "Render Shell and follow the link to every page.", []
        exp = "Every page route renders its component inside the shell."
    return SpecTest(id=f"IT-{prefix}-1", scope="integration", description=desc, preconditions=pre,
                    expected=exp, verifies=syms)


def _system_tests(plan: ProjectPlan) -> list[SpecTest]:
    form = next(t.target for t in plan.tasks if t.kind == "form")
    base, route = api_base(form), page_route(form)
    routes = [f"route:{r}" for r in plan.routes()]
    out = [
        SpecTest(id="ST-1", scope="system",
                 description=f"Sign in, create {_a(form)} through its form, then open {route}.",
                 preconditions=["The app is running on an empty database", "A registered user"],
                 expected=f"The new {form} is stored and listed on {route}.",
                 verifies=[f"form:{pascal(form)}Form", f"client:{form}", f"endpoint:POST {base}",
                           f"table:{form}", f"route:{route}"]),
        SpecTest(id="ST-2", scope="system",
                 description="Visit every page route without signing in.",
                 preconditions=["The app is running"],
                 expected="Every page request is rejected by the route guard.",
                 verifies=["guard:routes", "guard:session", *routes]),
    ]
    if any(t.kind == "oauth" for t in plan.tasks):
        out.append(SpecTest(id="ST-3", scope="system",
                            description="Start the OAuth sign-in flow from a signed-out browser.",
                            preconditions=["The app is running"],
                            expected="The browser is redirected to the provider's authorize URL.",
                            verifies=["provider:oauth"]))
    return out


def _summary(domain: str, plan: ProjectPlan) -> str:
    targets = [t.target for t in plan.tasks if t.domain == domain and t.kind in ("schema", "rest", "page")]
    if domain == "database":
        return f"Postgres tables: {', '.join(targets)}."
    if domain == "auth":
        extra = ", an OAuth hand-off" if any(t.kind == "oauth" for t in plan.tasks) else ""
        return f"Cookie sessions on the users table{extra} and a route guard over every page."
    if domain == "network":
        return f"FastAPI routers for {', '.join(targets)}, and one typed TypeScript client."
    return f"React pages for {', '.join(targets)}, one create form, and an app shell."


def _architecture(plan: ProjectPlan) -> str:
    return (f"{plan.name}: a React frontend calls FastAPI routers through a typed client; Postgres "
            f"stores {sum(t.domain == 'database' for t in plan.tasks)} tables; cookie sessions protect "
            "the API and every page.")


def gold_spec(plan: ProjectPlan) -> ProjectSpec:
    """The reference spec for a gold plan. Every statement holds for the gold artifacts."""
    ids: dict[str, str] = {}
    layout: dict[str, list[tuple[str, str, list[Task]]]] = {}
    for d in DOMAINS:
        tasks = [t for t in plan.tasks if t.domain == d]
        groups = [g for g in _groups_of(d, tasks) if g[1]]
        layout[d] = []
        for gi, (heading, members) in enumerate(groups, 1):
            gid = f"{PREFIX[d]}-{gi}"
            layout[d].append((gid, heading, members))
            for ti, t in enumerate(members, 1):
                ids[t.id] = f"{gid}.{ti}"

    def spec_task(t: Task) -> SpecTask:
        tid = ids[t.id]
        steps = []
        for si, sym in enumerate(provides_of(t.domain, t.kind, t.target), 1):
            heading, desc, pre, exp = _step_text(sym)
            sid = f"{tid}.{si}"
            steps.append(Step(id=sid, heading=heading, test=SpecTest(
                id=f"UT-{sid}", scope="unit", description=desc, preconditions=pre, expected=exp,
                verifies=[sym])))
        return SpecTask(id=tid, kind=t.kind, target=t.target, detail=t.detail,
                        acceptance=_acceptance(plan, t), deps=[ids[d] for d in t.deps], steps=steps)

    def domain_spec(d: str) -> DomainSpec:
        return DomainSpec(
            summary=_summary(d, plan),
            integration_tests=[_integration_test(d, plan)],
            groups=[TaskGroup(id=gid, heading=h, tasks=[spec_task(t) for t in members])
                    for gid, h, members in layout[d]],
        )

    return ProjectSpec(name=plan.name, stack=plan.stack, architecture=_architecture(plan),
                       system_tests=_system_tests(plan),
                       **{d: domain_spec(d) for d in DOMAINS})


# --- Scoring ------------------------------------------------------------------


class SpecScore(BaseModel):
    parsed: bool  # JSON matched the ProjectSpec shape
    compiled: bool  # to_plan produced a valid ProjectPlan
    plan: PlanScore  # the same plan metrics the flat manager is scored on
    symbol_coverage: float  # share of the plan's provided symbols with a unit test on a step
    tests_scoped: float  # share of tests with the scope their level requires
    known_refs: float  # share of test references that name a symbol the plan really has


def _empty_plan_score() -> PlanScore:
    return PlanScore(valid=False, deps_satisfied=False, domain_coverage=0.0, task_recall=0.0,
                     task_precision=0.0, isomorphic=False)


def score_spec_json(text: str, gold: ProjectPlan) -> SpecScore:
    """Score raw model text against a gold plan. Unparseable text scores zero."""
    empty = SpecScore(parsed=False, compiled=False, plan=_empty_plan_score(), symbol_coverage=0.0,
                      tests_scoped=0.0, known_refs=0.0)
    try:
        spec = ProjectSpec.model_validate_json(text)
    except ValueError:
        return empty
    try:
        plan: ProjectPlan | None = to_plan(spec)
    except ValueError:
        plan = None

    tests: list[tuple[str, SpecTest]] = [("system", t) for t in spec.system_tests]
    for d in DOMAINS:
        tests += [("integration", t) for t in spec.domain(d).integration_tests]
    unit_covered: set[str] = set()
    for _, task in spec.tasks():
        for step in task.steps:
            tests.append(("unit", step.test))
            if step.test.scope == "unit":
                unit_covered |= set(step.test.verifies)
    scoped = sum(t.scope == want for want, t in tests) / len(tests)

    if plan is None:
        return empty.model_copy(update={"parsed": True, "tests_scoped": scoped})
    known = set(plan.providers())
    refs = [s for _, t in tests for s in t.verifies]
    return SpecScore(
        parsed=True,
        compiled=True,
        plan=score_plan(plan, gold),
        symbol_coverage=len(unit_covered & known) / len(known) if known else 0.0,
        tests_scoped=scoped,
        known_refs=sum(s in known for s in refs) / len(refs) if refs else 0.0,
    )


def summarize_specs(scores: list[SpecScore]) -> dict[str, float]:
    n = max(len(scores), 1)
    return {
        "n": len(scores),
        "parsed": sum(s.parsed for s in scores) / n,
        "compiled": sum(s.compiled for s in scores) / n,
        "isomorphic": sum(s.plan.isomorphic for s in scores) / n,
        "task_recall": sum(s.plan.task_recall for s in scores) / n,
        "task_precision": sum(s.plan.task_precision for s in scores) / n,
        "symbol_coverage": sum(s.symbol_coverage for s in scores) / n,
        "tests_scoped": sum(s.tests_scoped for s in scores) / n,
        "known_refs": sum(s.known_refs for s in scores) / n,
    }


# --- Prompt and training rows -------------------------------------------------

SPEC_SYSTEM = """You are the manager of a software team with four specialists:
- database: Postgres schemas (kind "schema").
- auth: cookie sessions ("session"), OAuth hand-off ("oauth"), route guard ("guards").
- network: FastAPI routers ("rest") and typed TypeScript clients ("client").
- frontend: React pages ("page"), create forms ("form"), the app shell ("layout").

Turn a one-line project brief into a nested spec. Reply with ONLY JSON:
{"name", "stack": "fastapi+react+postgres", "architecture", "system_tests": [test],
 "database": section, "auth": section, "network": section, "frontend": section}
section = {"summary", "integration_tests": [test], "groups": [{"id", "heading", "tasks": [task]}]}
task = {"id", "kind", "target", "detail", "acceptance", "deps": [task id], "steps": [step]}
step = {"id", "heading", "test": test}
test = {"id", "scope", "description", "preconditions": [text], "expected", "verifies": [symbol]}

Tasks:
- One "schema" per entity plus one for "users". One "rest" and one "page" per entity.
- One "session", "guards", "form", "client" and "layout". "oauth" only if the brief asks for OAuth.
- "form" and "client" target the entity the brief's form creates.
- "target" is the entity slug; otherwise "users", "session", "oauth", "routes" or "shell".
- "deps" lists earlier tasks whose outputs this task consumes.

Ids: groups DB-1, AUTH-1, NET-1, FE-1; tasks DB-1.1; steps DB-1.1.1; tests UT-<step id>, IT-DB-1, ST-1.

Each task has one step per symbol it provides, and each step has one "unit" test verifying that symbol.
Symbols: table:<entity>; endpoint:GET /api/<plural>, endpoint:POST /api/<plural>,
endpoint:GET /api/<plural>/{item_id}; client:<entity>; guard:session; guard:routes; provider:oauth;
route:/<plural>, component:<Entity>Page; form:<Entity>Form; layout:shell.
Each section has an "integration" test and the project has "system" tests, each verifying real symbols."""


def format_spec_example(description: str, plan: ProjectPlan) -> tuple[str, str]:
    """(user, completion) for one training row. The system prompt is SPEC_SYSTEM."""
    from slm.manager.manager import user_prompt

    return user_prompt(description), gold_spec(plan).model_dump_json(exclude_none=True)
