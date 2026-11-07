"""Architecture experiments: the same model and brief, different primary-agent setups.

Every arm turns a project brief into a file tree, and every arm is graded the same way:
  gold_pass        the produced files, attributed to the GOLD plan's tasks by canonical path and run
                   through `integrate(gold plan)`, pass every check (an arm can't pass by planning less)
  gold_task_rate   share of gold tasks whose file passes its own contract (check_task)
  own_pass         the arm's own deliverable passed under its own plan (what its user would see)
Cost and speed, from the trace:
  calls, tok_in, tok_out       every model call counts, the manager's plan included
  wall_s                       measured end to end on this machine
  crit_tok_out / crit_s        the critical path: per dependency level the slowest call, summed over
                               levels (plan first). This is the latency a batching server (vLLM) approaches
                               when sibling calls really run concurrently. Measured wall clock cannot show
                               it on a local server that serves one request at a time.

Arms:
  mono           1 agent, 1 call: writes the whole project (generalist prompt, full conventions)
  mgr-G1         manager plan -> 1 generalist agent, one call per task, parallel per level
  mgr-G2         manager -> backend / frontend agents
  mgr-G4         manager -> 4 domain specialists (the current architecture)
  mgr-G9         manager -> 9 per-kind specialists
  gold-G4        reference plan -> 4 specialists (a perfect manager: the planning ceiling)
  mgr-G4-batch   manager -> 4 specialists, ONE call per (level, specialist) covering all its tasks
  mgr-G4-repair  mgr-G4 plus one repair round for tasks that failed their contract
  mgr-G4-serial  mgr-G4 dispatched one task at a time (the latency control)
  mgr-rnn        manager -> 4 specialists one task at a time, each step reading a bounded memory of what
                 earlier steps built (no extra model calls; compare with mgr-G4-serial, which has no memory)
  mgr-gru        mgr-rnn, but the memory drops what no remaining task needs
  mgr-lstm       mgr-rnn, but each step reads only what it depends on, plus the latest step
  mgr-slim1      mgr-G4 without the list of what teammates provide
  mgr-slim2      mgr-slim1 with a system prompt covering only the task's kind
  mgr-slim3      mgr-slim2 cut to the path, the tokens and the kind's conventions (needs schema-constrained output)
  mgr-combo-s<N> LSTM memory + run-check repair + prompt level N (0 is the full prompt)
  mgr-G4-runfix  mgr-G4, then up to two repair rounds driven by really running the project against the manager's plan
  mgr-G4-promptfix  mgr-G4-runfix with literal import lines and the `db` methods in the system prompt
  mgr-G4-shell   mgr-G4-promptfix with Shell.tsx written by code from the plan, so no model call for it
  mgr-G4-contract  mgr-G4-shell plus an exact contract that replaces the manager's free-text task detail
  mgr-G4-context   mgr-G4-contract plus the code each task depends on in its prompt
  mgr-1toN       one input, many outputs: every step gets only the brief, its path and the memory
  mgr-Nto1       many inputs, one output: every task goes into a single call that writes all the files
  mgr-seq2seq    encoder-decoder: one extra call compresses the plan into a context, then mgr-rnn decodes from it

RNN topologies map to arms as: one-to-one = mgr-G4-serial (no memory), one-to-many = mgr-1toN, many-to-one =
mgr-Nto1, many-to-many synced = mgr-rnn, encoder-decoder (many-to-many unsynced) = mgr-seq2seq.
  nested-rnn     mgr-rnn on a plan from the trained nested manager (saved plans; its calls aren't counted)
  team-nested    trained nested manager -> trained specialists, built outside the harness and graded from disk
  base-opus      `mono` on Claude Opus through the claude CLI: same prompt, same grading
  base-codex     `mono` on Codex through the codex CLI

The manager is greedy, so its plan for a project is the same in every arm: it is computed once per
project (`PlanCache`) and its calls, tokens and seconds are added to every manager arm. Running
`mgr-G4-repair` also yields the `mgr-G4` result (the state before the repair round).
"""

from __future__ import annotations

import asyncio
import re
import time
from collections import defaultdict
from dataclasses import asdict, dataclass, field

from pydantic import Field

from slm.baselines.monolith import MonolithProject, files_to_artifacts
from slm.contracts import (
    Artifact, ArtifactFile, Project, ProjectPlan, Strict, Task, check_task, integrate, provide_token,
    specialist_prompt, task_ok, use_token,
)
from slm.domains import DOMAINS, canonical_path
from slm.llm.base import LLMClient
from slm.llm.cli import BackendUnavailable
from slm.manager.manager import MANAGER_SYSTEM, user_prompt
from slm.manager.score import score_plan
from slm.pipeline.dispatch import run_plan
from slm.pipeline.oracle import CALL
from slm.arch.contract import context_prompt, contract_prompt, generate_shell
from slm.arch.teams import agent_for, minimal_system, system_for
from slm.specialists import system_prompt
from slm.trace import TraceEvent, Tracer

LOCAL_ARMS = ("mono", "mgr-G1", "mgr-G2", "mgr-G4", "mgr-G9", "gold-G4", "mgr-G4-batch", "mgr-G4-repair",
              "mgr-G4-serial", "mgr-G4-runfix", "mgr-G4-promptfix", "mgr-G4-shell", "mgr-G4-contract", "mgr-G4-context", "mgr-rnn", "mgr-gru", "mgr-lstm", "mgr-1toN", "mgr-Nto1", "mgr-seq2seq", "mgr-slim1", "mgr-slim2",
              "mgr-slim3", "mgr-combo-s0", "mgr-combo-s1", "mgr-combo-s2", "mgr-combo-s3", "nested-rnn")
BASELINES = ("base-opus", "base-codex")
ARMS = (*LOCAL_ARMS, *BASELINES)
MANAGED_PREFIXES = ("mgr-", "nested-")
IMPORTED_ARMS = ("opus-multiagent", "team-nested")  # built outside this harness, then graded from disk with `slm.arch grade-dir`
PLAN_LEVEL = -1
REPAIR_LEVEL = 1000
ENCODER_LEVEL = -2


@dataclass
class Result:
    arm: str
    project_id: str
    template_id: str | None
    gold_pass: bool = False
    gold_task_rate: float = 0.0
    own_pass: bool = False
    first_fail: str | None = None
    plan_valid: bool | None = None
    plan_recall: float | None = None
    plan_precision: float | None = None
    n_tasks: int = 0
    calls: int = 0
    tok_in: int = 0
    tok_out: int = 0
    wall_s: float = 0.0
    plan_s: float = 0.0
    crit_tok_out: int = 0
    crit_s: float = 0.0
    error: str | None = None
    by_domain: dict = field(default_factory=dict)
    files: list = field(default_factory=list, repr=False)  # what was graded; saved to disk, not to results.jsonl

    def as_dict(self) -> dict:
        d = asdict(self)
        d.pop("files")
        return d


@dataclass
class PlanStats:
    """One manager call (plus its retry) for one project, shared by every manager arm."""

    plan: ProjectPlan | None
    valid: bool
    recall: float
    precision: float
    seconds: float
    calls: int
    tok_in: int
    tok_out: int
    error: str | None = None

    def dump(self) -> dict:
        d = asdict(self)
        d["plan"] = self.plan.model_dump() if self.plan else None
        return d

    @classmethod
    def load(cls, d: dict) -> PlanStats:
        d = dict(d)
        d["plan"] = ProjectPlan.model_validate(d["plan"]) if d["plan"] else None
        return cls(**d)


# --- grading -----------------------------------------------------------------


def gold_grade(project: Project, files: list[ArtifactFile], res: Result) -> None:
    gold = project.plan
    assert gold is not None
    res.files = list(files)
    arts = files_to_artifacts(gold, files)
    d = integrate(project.id, gold, arts)
    res.gold_pass = d.ok
    res.first_fail = d.failures[0] if d.failures else None
    per_dom: dict[str, list[int]] = defaultdict(list)
    for t in gold.tasks:
        ok = t.id in arts and all(c.ok for c in check_task(gold, t, arts[t.id]))
        per_dom[t.domain].append(int(ok))
    flat = [x for v in per_dom.values() for x in v]
    res.gold_task_rate = sum(flat) / len(flat)
    res.by_domain = {k: sum(v) / len(v) for k, v in per_dom.items()}


def _merge(artifacts: dict[str, Artifact]) -> list[ArtifactFile]:
    by_path: dict[str, ArtifactFile] = {}
    for a in artifacts.values():
        for f in a.files:
            by_path[f.path] = f
    return list(by_path.values())


def critical_path(llm: list[TraceEvent]) -> tuple[int, float]:
    """(output tokens, seconds) along the critical path: the slowest call of each level, summed.

    Calls without a dep_level (the monolith) are their own level. Retries of the same call add up.
    """
    per_call: dict[tuple, list[TraceEvent]] = defaultdict(list)
    for e in llm:
        per_call[(e.dep_level, e.task_id, e.domain, e.callee)].append(e)
    levels: dict[int | None, list[tuple[int, float]]] = defaultdict(list)
    for (lv, *_), evs in per_call.items():
        levels[lv].append((sum(e.output_tokens for e in evs), sum(e.latency_ms for e in evs) / 1000))
    tok = sum(max(t for t, _ in v) for v in levels.values())
    sec = sum(max(s for _, s in v) for v in levels.values())
    return tok, sec


# --- planning ----------------------------------------------------------------


async def make_plan(project: Project, manager: LLMClient, tracer: Tracer) -> PlanStats:
    manager.tracer = tracer
    n0 = len(tracer.events()) if tracer.path.exists() else 0
    t0 = time.time()
    plan, error = None, None
    try:
        plan = await manager.acomplete(MANAGER_SYSTEM, user_prompt(project.description), ProjectPlan,
                                       caller="arch", callee="manager",
                                       ctx={"project_id": project.id, "mode": "plan", "dep_level": PLAN_LEVEL})
    except BackendUnavailable:
        raise
    except Exception as e:  # noqa: BLE001
        error = f"plan: {type(e).__name__}: {str(e)[:200]}"
    llm = [e for e in tracer.events()[n0:] if e.kind == "llm"]
    s = score_plan(plan, project.plan)
    return PlanStats(plan=plan, valid=s.valid, recall=s.task_recall, precision=s.task_precision,
                     seconds=time.time() - t0, calls=len(llm), tok_in=sum(e.input_tokens for e in llm),
                     tok_out=sum(e.output_tokens for e in llm), error=error)


# --- agents ------------------------------------------------------------------


class TeamClient(LLMClient):
    """Routes each dispatched task to its team agent's system prompt and keeps the artifact."""

    def __init__(self, inner: LLMClient, team: str):
        super().__init__(inner.model, inner.tracer)
        self.inner, self.team = inner, team
        self.artifacts: dict[str, Artifact] = {}
        self.backend_error: BackendUnavailable | None = None  # the dispatcher swallows task errors, so keep it

    def _raw(self, system, user, json_schema):  # pragma: no cover - delegated
        raise NotImplementedError

    def system_prompt(self, task: Task, agent: str) -> str:
        return system_for(self.team, agent)

    def task_prompt(self, plan: ProjectPlan, task: Task) -> str:
        return specialist_prompt(plan, task)

    def complete(self, system, user, schema, *, caller="user", callee="model", ctx=None):
        call = CALL.get()
        assert call is not None, "TeamClient runs inside the dispatcher"
        _, task = call
        agent = agent_for(self.team, task)
        try:
            out = self.inner.complete(self.system_prompt(task, agent), user, schema, caller=caller,
                                      callee=agent, ctx={**(ctx or {}), "adapter": agent})
        except BackendUnavailable as e:
            self.backend_error = e
            raise
        self.artifacts[task.id] = out
        return out


class ExactImportsClient(TeamClient):
    """G4, but told the literal import lines and `db` methods. Repairs go through here too, so they see them as well."""

    def system_prompt(self, task: Task, agent: str) -> str:
        return system_prompt(agent, exact_imports=True)


class GeneratedShellClient(ExactImportsClient):
    """The app shell comes from code, including in repairs, and every other task goes to its specialist."""

    def complete(self, system, user, schema, *, caller="user", callee="model", ctx=None):
        plan, task = CALL.get()
        if task.kind == "layout":
            self.artifacts[task.id] = generate_shell(plan, task)
            return self.artifacts[task.id]
        return super().complete(system, user, schema, caller=caller, callee=callee, ctx=ctx)


class ContractClient(GeneratedShellClient):
    """Sends the contract prompt. A repair prompt is already built from task_prompt, so it keeps its failure text."""

    def task_prompt(self, plan: ProjectPlan, task: Task) -> str:
        return contract_prompt(plan, task)

    def complete(self, system, user, schema, *, caller="user", callee="model", ctx=None):
        plan, task = CALL.get()
        prompt = user if caller == "repair" else self.task_prompt(plan, task)
        return super().complete(system, prompt, schema, caller=caller, callee=callee, ctx=ctx)


class ContextClient(ContractClient):
    """Also shows each task the code it depends on, as it stands when the task starts."""

    def task_prompt(self, plan: ProjectPlan, task: Task) -> str:
        return context_prompt(plan, task, self.artifacts)


RUN_REPAIR_ARMS = {"mgr-G4-runfix": TeamClient, "mgr-G4-promptfix": ExactImportsClient, "mgr-G4-shell": GeneratedShellClient,
                   "mgr-G4-contract": ContractClient, "mgr-G4-context": ContextClient}
SLIM_LEVELS = {"mgr-slim1": 1, "mgr-slim2": 2, "mgr-slim3": 3}


def slim_prompt(plan: ProjectPlan, task: Task, level: int) -> str:
    """The specialist prompt cut down by level. Every interface token stays: the integrator checks them all."""
    if level < 3:
        head = specialist_prompt(plan, task).split("The rest of the team provides:")[0]
        return head + "Return only the files for your task."
    use = sorted({use_token(s) for s in plan.requires(task)})
    provide = sorted({provide_token(s) for s in task.provides()})
    lines = [f"{task.kind} for `{task.target}`", f"Path: {canonical_path(task.domain, task.kind, task.target)}"]
    if use:
        lines += ["Use:", *use]
    return "\n".join([*lines, "Provide:", *provide])


class SlimClient(TeamClient):
    """Sends a smaller prompt for each task; level 2 and up scope the system prompt to the task's kind."""

    level = 1

    def system_prompt(self, task: Task, agent: str) -> str:
        if self.level >= 3:
            return minimal_system(task.domain, task.kind)
        return system_for("G9" if self.level == 2 else "G4", agent_for("G9" if self.level == 2 else "G4", task))

    def task_prompt(self, plan: ProjectPlan, task: Task) -> str:
        return slim_prompt(plan, task, self.level) if self.level else specialist_prompt(plan, task)

    def complete(self, system, user, schema, *, caller="user", callee="model", ctx=None):
        plan, task = CALL.get()
        return super().complete(system, self.task_prompt(plan, task), schema, caller=caller, callee=callee, ctx=ctx)


MEMORY_CHARS = 1200  # the hidden state's fixed size: the oldest entries are forgotten first
MEMORY_LINES_PER_FILE = 8
INTERFACE_LINE = re.compile(r"^\s*(export\s|def\s|async def\s|class\s|create table\b|@router\b)", re.IGNORECASE)


def remember(task: Task, artifact: Artifact) -> str:
    """One step's contribution to the memory: each file's path and the lines other code depends on."""
    parts = [f"{task.id} [{task.domain}/{task.kind}]:"]
    for f in artifact.files:
        lines = [x.strip()[:120] for x in f.content.splitlines() if INTERFACE_LINE.match(x)]
        parts.append(f"  {f.path}")
        parts += [f"    {x}" for x in lines[:MEMORY_LINES_PER_FILE]]
    return "\n".join(parts)


def render_memory(entries: list[str], budget: int = MEMORY_CHARS) -> str:
    """The newest entries that fit in `budget`, oldest first. An entry too big to fit whole is dropped."""
    kept: list[str] = []
    used = 0
    for entry in reversed(entries):
        if used + len(entry) > budget:
            break
        kept.append(entry)
        used += len(entry)
    if not kept:
        return ""
    return "\n\nAlready built by earlier steps (use these exact names):\n" + "\n".join(reversed(kept))


class RecurrentClient(TeamClient):
    """Feeds each step the memory of earlier steps, then adds its own output. Needs parallel=False."""

    def __init__(self, inner: LLMClient, team: str):
        super().__init__(inner, team)
        self.memory: list[tuple[Task, str]] = []  # (the step's task, what it left behind), oldest first
        self.step = 0

    def recall(self, plan: ProjectPlan, task: Task) -> list[str]:
        """What this step gets to read. The plain RNN reads everything; the budget forgets the oldest."""
        return [text for _, text in self.memory]

    def complete(self, system, user, schema, *, caller="user", callee="model", ctx=None):
        plan, task = CALL.get()
        # Each step waits for the one before, so it is its own level on the critical path.
        ctx = {**(ctx or {}), "dep_level": self.step}
        self.step += 1
        prompt = user + render_memory(self.recall(plan, task))
        try:
            out = super().complete(system, prompt, schema, caller=caller, callee=callee, ctx=ctx)
        except Exception:
            self.memory.append((task, f"{task.id} [{task.domain}/{task.kind}]: FAILED, no output"))
            raise
        self.memory.append((task, remember(task, out)))
        return out


class GatedClient(RecurrentClient):
    """GRU-like: one memory with an update gate that drops what no remaining task needs."""

    def recall(self, plan: ProjectPlan, task: Task) -> list[str]:
        done = {t.id for t, _ in self.memory}
        needed = {s for t in plan.tasks if t.id not in done for s in plan.requires(t)}
        return [text for t, text in self.memory if needed & set(t.provides())]


class LSTMClient(RecurrentClient):
    """LSTM-like: a long-term store read through an output gate (only what this task depends on), plus a
    short-term slot (the latest step). The rules come from the plan's symbols, not from learned weights."""

    def recall(self, plan: ProjectPlan, task: Task) -> list[str]:
        if not self.memory:
            return []
        needed = set(plan.requires(task))
        latest = self.memory[-1][1]
        direct = [text for t, text in self.memory if needed & set(t.provides())]
        # render_memory drops from the front, so what this task depends on survives a tight budget.
        return ([] if latest in direct else [latest]) + direct


class OneToManyClient(RecurrentClient):
    """One input: every step gets the same brief and the path to write, not its task's interfaces."""

    brief = ""

    def complete(self, system, user, schema, *, caller="user", callee="model", ctx=None):
        plan, task = CALL.get()
        path = canonical_path(task.domain, task.kind, task.target)
        prompt = f"Project brief:\n{self.brief}\nWrite the file at exactly: {path}\nReturn only that file."
        return super().complete(system, prompt, schema, caller=caller, callee=callee, ctx=ctx)


class Encoding(Strict):
    context: str = Field(description="The shared names and conventions every file must follow")


ENCODER_SYSTEM = f"""You are the design lead of a software team. Read the whole task list and write one compact
context the engineers will share: the exact names of tables, routes, functions and components, and how they connect.
Use at most {MEMORY_CHARS} characters. Reply with only JSON: {{"context": "<text>"}}."""


class EncoderDecoderClient(RecurrentClient):
    """The encoder's context is the decoder's starting state: every step reads it, then the usual memory."""

    context = ""

    def complete(self, system, user, schema, *, caller="user", callee="model", ctx=None):
        prefix = f"Shared context from the design lead:\n{self.context}\n\n" if self.context else ""
        return super().complete(system, prefix + user, schema, caller=caller, callee=callee, ctx=ctx)


async def encode(project: Project, plan: ProjectPlan, client: LLMClient, arm: str) -> str:
    """One model call that compresses the plan. If its output is invalid, decoding goes ahead without it."""
    tasks = "\n".join(f"- {t.id} [{t.domain}/{t.kind}] {t.target}: {', '.join(t.provides())}" for t in plan.tasks)
    try:
        out = await client.acomplete(ENCODER_SYSTEM, f"Project brief:\n{project.description}\n\nTasks:\n{tasks}", Encoding,
                                     caller="arch", callee="encoder",
                                     ctx={"mode": arm, "project_id": project.id, "dep_level": ENCODER_LEVEL})
    except BackendUnavailable:
        raise
    except Exception:  # noqa: BLE001
        return ""
    return out.context[:MEMORY_CHARS]


class ComboClient(SlimClient, LSTMClient):
    """A smaller prompt, then LSTM memory. Repair calls skip both: their prompt carries the failed checks, and
    they run side by side after the steps, so they neither read nor change the memory."""

    def complete(self, system, user, schema, *, caller="user", callee="model", ctx=None):
        if (ctx or {}).get("dep_level", -1) >= REPAIR_LEVEL:
            return TeamClient.complete(self, system, user, schema, caller=caller, callee=callee, ctx=ctx)
        return super().complete(system, user, schema, caller=caller, callee=callee, ctx=ctx)


COMBO_ARMS = {f"mgr-combo-s{n}": n for n in range(4)}
RECURRENT_ARMS = {"mgr-rnn": RecurrentClient, "nested-rnn": RecurrentClient, "mgr-gru": GatedClient, "mgr-lstm": LSTMClient,
                  "mgr-1toN": OneToManyClient, "mgr-seq2seq": EncoderDecoderClient}


async def run_dispatch(project: Project, plan: ProjectPlan, client: LLMClient, team: str, tracer: Tracer,
                       res: Result, *, parallel: bool = True, client_cls: type[TeamClient] = TeamClient,
                       **client_attrs) -> TeamClient:
    tc = client_cls(client, team)
    for name, value in client_attrs.items():
        setattr(tc, name, value)
    d = await run_plan(project.id, plan, {dm: tc for dm in DOMAINS}, tracer, mode=res.arm, parallel=parallel)
    if tc.backend_error is not None:
        raise tc.backend_error
    res.own_pass = d.ok
    gold_grade(project, _merge(tc.artifacts), res)
    return tc


def run_check(files: list[ArtifactFile], plan: ProjectPlan) -> dict:
    """Parse and really run a project. A toolchain failure isn't the model's, so it records no result."""
    from slm.bench.runcheck import GraderUnavailable, check_project

    try:
        return check_project(files, plan)
    except GraderUnavailable as e:
        raise BackendUnavailable(str(e)) from e


_PATH_IN_DETAIL = re.compile(r"src/[\w./-]+\.(?:py|sql|tsx?)")


def failures_by_task(plan: ProjectPlan, checks: list[dict]) -> dict[str, list[str]]:
    """Send each failed run check to the tasks that own it: the file its error names, plus the task its name implies."""
    by_path = {canonical_path(t.domain, t.kind, t.target): t.id for t in plan.tasks}
    kind = lambda *kinds: [t.id for t in plan.tasks if t.kind in kinds]  # noqa: E731
    out: dict[str, list[str]] = defaultdict(list)
    for c in checks:
        if c["ok"]:
            continue
        name, detail = c["name"], c.get("detail", "")
        owners = [by_path[p] for p in _PATH_IN_DETAIL.findall(detail) if p in by_path]
        head, _, rest = name.partition(":")
        if head in ("python", "typescript"):
            owners += [by_path[rest]] if rest in by_path else []
        elif head == "loads":
            owners += [by_path[f"src/database/{rest}"]] if f"src/database/{rest}" in by_path else kind("schema")
        elif head == "table":
            owners += [t.id for t in plan.tasks if t.kind == "schema" and t.target == rest]
        elif head in ("users_accepts_a_session", "any_table_exists"):
            owners += [t.id for t in plan.tasks if t.kind == "schema" and t.target == "users"] or kind("schema")
        elif head in ("create", "list", "fetch_one", "create_needs_session"):
            owners += [t.id for t in plan.tasks if t.kind == "rest" and any(s.endswith(f" {rest}") for s in t.provides())]
        elif head == "guard_blocks":
            owners += kind("guards")
        elif head == "oauth_module_imports":
            owners += kind("oauth")
        elif head == "app_imports" and not owners:
            owners += kind("rest", "session")
        elif head in ("shell_bundles", "shell_renders", "links") and not owners:
            owners += kind("layout")
        for task_id in dict.fromkeys(owners):
            out[task_id].append(f"{name} ({detail})" if detail else name)
    return dict(out)


async def run_check_repair(project: Project, plan: ProjectPlan, tc: TeamClient, res: Result, rounds: int = 2) -> None:
    """Run the project, repair what its failures point at, and keep the best version seen, so a fix that breaks more
    than it mends is thrown away. Checked against the arm's own plan: the benchmark's reference never reaches the model."""
    best, best_rate = dict(tc.artifacts), -1.0
    for number in range(rounds + 1):
        report = await asyncio.to_thread(run_check, _merge(tc.artifacts), plan)
        if report["rate"] > best_rate:
            best, best_rate = dict(tc.artifacts), report["rate"]
        if report["passed"] or number == rounds:
            break
        tc.artifacts = dict(best)
        why = failures_by_task(plan, report["checks"])
        for t in plan.tasks:  # missing output, or a broken contract, can leave the run check nothing to point at
            art = tc.artifacts.get(t.id)
            if art is None:
                why.setdefault(t.id, []).append("no valid output")
            else:
                why_not = [f"{c.name} ({c.detail})" for c in check_task(plan, t, art) if not c.ok]
                if why_not:
                    why.setdefault(t.id, []).extend(why_not)
        if not why:
            break
        await asyncio.gather(*[_repair(plan, plan.task(i), tc, project.id, res.arm, "; ".join(w), REPAIR_LEVEL + number)
                               for i, w in why.items()])
        if tc.backend_error is not None:
            raise tc.backend_error
    tc.artifacts = best
    res.own_pass = integrate(project.id, plan, tc.artifacts).ok
    gold_grade(project, _merge(tc.artifacts), res)


async def repair_round(project: Project, plan: ProjectPlan, tc: TeamClient, res: Result) -> None:
    failed = [t for t in plan.tasks if t.id not in tc.artifacts or not task_ok(plan, t, tc.artifacts[t.id])[0]]
    if failed:
        await asyncio.gather(*[_repair(plan, t, tc, project.id, res.arm) for t in failed])
        if tc.backend_error is not None:
            raise tc.backend_error
    res.own_pass = integrate(project.id, plan, tc.artifacts).ok
    gold_grade(project, _merge(tc.artifacts), res)


async def _repair(plan: ProjectPlan, task: Task, tc: TeamClient, project_id: str, mode: str, why: str | None = None,
                  level: int = REPAIR_LEVEL) -> None:
    prev = tc.artifacts.get(task.id)
    if why is None:
        why = "no valid output" if prev is None else "; ".join(
            f"{c.name} ({c.detail})" for c in check_task(plan, task, prev) if not c.ok)
    prompt = (tc.task_prompt(plan, task) + f"\n\nYour previous attempt failed these checks: {why}.\n"
              + (f"Previous files:\n{prev.model_dump_json()}\n" if prev else "")
              + "Return the corrected files.")
    CALL.set((plan, task))
    try:
        await tc.acomplete("", prompt, Artifact, caller="repair", callee="repair",
                           ctx={"mode": mode, "project_id": project_id, "task_id": task.id,
                                "domain": task.domain, "dep_level": level})
    except Exception:  # noqa: BLE001 - keep the first attempt
        pass


# --- batch: one call per (level, specialist) ---------------------------------


class BatchFiles(Strict):
    files: list[ArtifactFile]
    summary: str = Field(default="")


def batch_prompt(plan: ProjectPlan, tasks: list[Task]) -> str:
    parts = [f"Project: {plan.name} (stack: {plan.stack})", f"You have {len(tasks)} task(s). Write one file per task."]
    for t in tasks:
        body = specialist_prompt(plan, t).split("\nThe rest of the team provides:")[0]
        parts.append("---\n" + body.split("\n", 1)[1])
    team = "\n".join(f"- {t.id} [{t.domain}/{t.kind}] {t.target}: {', '.join(t.provides())}" for t in plan.tasks)
    parts.append(f"---\nThe whole team provides:\n{team}\nReturn only the files for your tasks.")
    return "\n".join(parts)


async def run_many_to_one(project: Project, plan: ProjectPlan, client: LLMClient, res: Result) -> None:
    """Every task goes into one call, which writes every file."""
    artifacts: dict[str, Artifact] = {}
    try:
        out = await client.acomplete(system_for("G1", "generalist"), batch_prompt(plan, plan.tasks), BatchFiles,
                                     caller="arch", callee="many-to-one",
                                     ctx={"mode": res.arm, "project_id": project.id, "dep_level": 0})
    except BackendUnavailable:
        raise
    except Exception as e:  # noqa: BLE001
        res.error = f"{type(e).__name__}: {str(e)[:200]}"
    else:
        by_path = {f.path: f for f in out.files}
        for t in plan.tasks:
            want = canonical_path(t.domain, t.kind, t.target)
            if want in by_path:
                artifacts[t.id] = Artifact(files=[by_path[want]], summary="many-to-one")
    res.own_pass = integrate(project.id, plan, artifacts).ok
    gold_grade(project, _merge(artifacts), res)


async def run_batch(project: Project, plan: ProjectPlan, client: LLMClient, res: Result) -> None:
    artifacts: dict[str, Artifact] = {}
    by_id = {t.id: t for t in plan.tasks}
    for level, ids in enumerate(plan.levels()):
        groups: dict[str, list[Task]] = defaultdict(list)
        for i in ids:
            groups[by_id[i].domain].append(by_id[i])

        async def one(domain: str, tasks: list[Task]) -> None:
            try:
                out = await client.acomplete(
                    system_for("G4", domain), batch_prompt(plan, tasks), BatchFiles, caller="arch",
                    callee=domain, ctx={"mode": res.arm, "project_id": project.id, "domain": domain,
                                        "adapter": domain, "dep_level": level})
            except BackendUnavailable:
                raise
            except Exception:  # noqa: BLE001
                return
            by_path = {f.path: f for f in out.files}
            for t in tasks:
                want = canonical_path(t.domain, t.kind, t.target)
                if want in by_path:
                    artifacts[t.id] = Artifact(files=[by_path[want]], summary="batch")

        await asyncio.gather(*[one(d, ts) for d, ts in groups.items()])
    res.own_pass = integrate(project.id, plan, artifacts).ok
    gold_grade(project, _merge(artifacts), res)


# --- monolith ----------------------------------------------------------------

MONO_RULES = """
Write the WHOLE project in one reply: every file of every specialist, at these paths:
src/database/<table>.sql (users plus one per entity) · src/auth/session.py · src/auth/oauth.py (only if the
brief asks for OAuth) · src/auth/guards.py · src/network/<entity>_api.py (one per entity) ·
src/network/<entity>_client.ts (for the form entity) · src/frontend/<Entity>Page.tsx (one per entity) ·
src/frontend/<Entity>Form.tsx · src/frontend/Shell.tsx. Collections are plural: /api/invoices, /invoices."""


async def run_mono(project: Project, client: LLMClient, res: Result) -> None:
    try:
        out = await client.acomplete(system_for("G1", "generalist") + MONO_RULES,
                                     f"Project brief:\n{project.description}", MonolithProject,
                                     caller="arch", callee="monolith",
                                     ctx={"mode": res.arm, "project_id": project.id})
        files = out.files
    except BackendUnavailable:
        raise
    except Exception as e:  # noqa: BLE001
        res.error, files = f"{type(e).__name__}: {str(e)[:200]}", []
    gold_grade(project, files, res)
    res.own_pass = res.gold_pass  # the monolith has no plan of its own


# --- one arm on one project ----------------------------------------------------


def _account(res: Result, tracer: Tracer, n0: int, t0: float, ps: PlanStats | None,
             plan_events: list[TraceEvent]) -> None:
    llm = [e for e in tracer.events()[n0:] if e.kind == "llm"]
    res.wall_s = time.time() - t0 + (ps.seconds if ps else 0.0)
    res.calls = len(llm) + (ps.calls if ps else 0)
    res.tok_in = sum(e.input_tokens for e in llm) + (ps.tok_in if ps else 0)
    res.tok_out = sum(e.output_tokens for e in llm) + (ps.tok_out if ps else 0)
    res.crit_tok_out, res.crit_s = critical_path(llm + plan_events)


async def run_arm(arm: str, project: Project, client: LLMClient, tracer: Tracer,
                  ps: PlanStats | None = None, plan_events: list[TraceEvent] | None = None) -> list[Result]:
    """Run one arm on one project. Manager arms need `ps` (the shared plan; see make_plan).

    Returns one Result, or two for mgr-G4-repair (mgr-G4 before the repair round, then after)."""
    if arm not in ARMS:
        raise ValueError(f"unknown arm {arm!r}; choose from {ARMS}")
    if arm.startswith(MANAGED_PREFIXES) and ps is None:
        raise ValueError(f"{arm} needs the project's PlanStats")
    plan_events = plan_events or []
    res = Result(arm=arm, project_id=project.id, template_id=project.template_id)
    client.tracer = tracer
    n0 = len(tracer.events()) if tracer.path.exists() else 0
    t0 = time.time()
    out = [res]
    use_ps = ps if arm.startswith(MANAGED_PREFIXES) else None
    if use_ps is not None:
        res.plan_valid, res.plan_recall, res.plan_precision = ps.valid, ps.recall, ps.precision
        res.plan_s, res.error = ps.seconds, ps.error
        res.n_tasks = len(ps.plan.tasks) if ps.plan else 0
    try:
        if arm == "mono" or arm in BASELINES:
            await run_mono(project, client, res)
        elif arm.startswith("gold-"):
            res.plan_valid, res.plan_recall, res.plan_precision = True, 1.0, 1.0
            res.n_tasks = len(project.plan.tasks)
            await run_dispatch(project, project.plan, client, "G4", tracer, res)
        elif ps.plan is None:
            gold_grade(project, [], res)
        elif arm == "mgr-G4-batch":
            await run_batch(project, ps.plan, client, res)
        elif arm in COMBO_ARMS:
            tc = await run_dispatch(project, ps.plan, client, "G4", tracer, res, parallel=False,
                                    client_cls=ComboClient, level=COMBO_ARMS[arm])
            await run_check_repair(project, ps.plan, tc, res)
        elif arm in RUN_REPAIR_ARMS:
            tc = await run_dispatch(project, ps.plan, client, "G4", tracer, res, client_cls=RUN_REPAIR_ARMS[arm])
            await run_check_repair(project, ps.plan, tc, res)
        elif arm in SLIM_LEVELS:
            await run_dispatch(project, ps.plan, client, "G4", tracer, res, client_cls=SlimClient,
                               level=SLIM_LEVELS[arm])
        elif arm == "mgr-Nto1":
            await run_many_to_one(project, ps.plan, client, res)
        elif arm == "mgr-1toN":
            await run_dispatch(project, ps.plan, client, "G4", tracer, res, parallel=False,
                               client_cls=OneToManyClient, brief=project.description)
        elif arm == "mgr-seq2seq":
            context = await encode(project, ps.plan, client, arm)
            await run_dispatch(project, ps.plan, client, "G4", tracer, res, parallel=False,
                               client_cls=EncoderDecoderClient, context=context)
        elif arm in RECURRENT_ARMS:
            await run_dispatch(project, ps.plan, client, "G4", tracer, res, parallel=False,
                               client_cls=RECURRENT_ARMS[arm])
        elif arm == "mgr-G4-repair":
            before = Result(**{**res.as_dict(), "arm": "mgr-G4"})
            tc = await run_dispatch(project, ps.plan, client, "G4", tracer, before)
            _account(before, tracer, n0, t0, use_ps, plan_events)
            res.own_pass = before.own_pass
            await repair_round(project, ps.plan, tc, res)
            out = [before, res]
        else:
            team = arm.split("-")[1]
            await run_dispatch(project, ps.plan, client, team, tracer, res, parallel=not arm.endswith("-serial"))
    except BackendUnavailable:
        raise
    except Exception as e:  # noqa: BLE001 - one broken run must not stop the grid
        res.error = f"{type(e).__name__}: {str(e)[:300]}"
    _account(res, tracer, n0, t0, use_ps, plan_events if use_ps else [])
    return out
