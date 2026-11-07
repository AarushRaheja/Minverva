"""The runtime: manager plan -> four specialists (parallel per dependency level) -> integrator.

Contract (slm/trace.py, FROZEN kinds):
- one kind="plan" event per project when the manager plans (or one gold-plan event);
- one kind="route" and one kind="task" event per task;
- exactly one kind="final" event per project, deciding `output` ("pass" / "fail:<check>").
Task failures never raise: they are recorded and the integrator reports what is missing.
"""

from __future__ import annotations

import asyncio
import time
from typing import Callable

from slm.contracts import (
    Artifact, ArtifactFile, Deliverable, Project, ProjectPlan, Task, integrate, specialist_prompt,
    specialist_system, task_ok,
)
from slm.llm.base import LLMClient
from slm.manager.manager import MANAGER_SYSTEM, user_prompt
from slm.manager.spec import SPEC_SYSTEM, ProjectSpec, normalize_spec, spec_task_prompts, to_plan
from slm.pipeline.finish import MAX_REPAIRS, code_artifact, finish_artifact, repair_prompt, written_by_code
from slm.pipeline.oracle import CALL
from slm.pipeline.router import route
from slm.trace import Tracer


SPEC_PATH = "SPEC.json"  # the manager's nested plan, handed to the user with the code


def _err(e: BaseException) -> str:
    return f"{type(e).__name__}: {str(e)[:300]}"


def _ctx(mode: str, project_id: str, task: Task, dep_level: int, adapter: str) -> dict:
    return {"mode": mode, "project_id": project_id, "task_id": task.id, "domain": task.domain,
            "dep_level": dep_level, "adapter": adapter}


async def _run_task(
    plan: ProjectPlan, task: Task, dep_level: int, clients: dict[str, LLMClient], tracer: Tracer | None,
    mode: str, project_id: str, prompts: dict[str, str] | None = None,
) -> tuple[str, Artifact | None]:
    client = clients[task.domain]
    single = mode == "single"  # one generalist serves every task: never re-address it to spec-*
    adapter = route(plan, task, tracer=tracer, mode=mode, project_id=project_id, dep_level=dep_level,
                    served=client.model if single else None)
    if not single and hasattr(client, "for_model"):  # adapter-addressed clients get the adapter as the model
        client = client.for_model(adapter)
    CALL.set((plan, task))
    t0 = time.time()
    artifact, detail, ok = None, "", False
    try:
        ctx = _ctx(mode, project_id, task, dep_level, adapter)
        prompt = prompts[task.id] if prompts else specialist_prompt(plan, task)

        async def ask(text: str) -> Artifact:
            got = await client.acomplete(specialist_system(task.domain), text, Artifact, caller="dispatch",
                                         callee=adapter, ctx=ctx)
            return finish_artifact(task, got) if prompts else got

        if prompts and written_by_code(task):
            artifact = code_artifact(plan, task)
        else:
            artifact = await ask(prompt)
        ok, detail = task_ok(plan, task, artifact)
        for _ in range(MAX_REPAIRS if prompts else 0):  # only the nested path has repair
            if ok:
                break
            artifact = await ask(repair_prompt(prompt, artifact.model_dump_json(), detail))
            ok, detail = task_ok(plan, task, artifact)
    except Exception as e:  # noqa: BLE001 - a failed task degrades the product, it does not abort the run
        detail = _err(e)
    if tracer is not None:
        tracer.record(
            kind="task", caller="dispatch", callee=adapter, ok=ok, error=None if ok else detail,
            output="ok" if ok else detail, t_start=t0, t_end=time.time(),
            **_ctx(mode, project_id, task, dep_level, adapter),
        )
    return task.id, artifact


def _final(tracer: Tracer | None, project_id: str, mode: str, t0: float,
           deliverable: Deliverable | None, error: str | None) -> None:
    if tracer is None:
        return
    output = None
    if deliverable is not None:
        output = "pass" if deliverable.ok else f"fail:{deliverable.failures[0] if deliverable.failures else 'empty'}"
    tracer.record(
        kind="final", caller="dispatch", callee="integrator", mode=mode, project_id=project_id,
        ok=error is None, error=error, output=output, t_start=t0, t_end=time.time(),
    )


async def run_plan(
    project_id: str, plan: ProjectPlan, clients: dict[str, LLMClient], tracer: Tracer | None = None,
    *, mode: str = "specialists", parallel: bool = True, prompts: dict[str, str] | None = None,
) -> Deliverable:
    """Dispatch every task to its domain specialist, then integrate. Never raises."""
    t0 = time.time()
    artifacts: dict[str, Artifact] = {}
    by_id = {t.id: t for t in plan.tasks}
    try:
        for level, ids in enumerate(plan.levels()):
            calls = [_run_task(plan, by_id[i], level, clients, tracer, mode, project_id, prompts) for i in ids]
            done = await asyncio.gather(*calls) if parallel else [await c for c in calls]
            for tid, art in done:
                if art is not None:
                    artifacts[tid] = art
        deliverable = integrate(project_id, plan, artifacts)
    except Exception as e:  # noqa: BLE001
        _final(tracer, project_id, mode, t0, None, _err(e))
        raise
    _final(tracer, project_id, mode, t0, deliverable, None)
    return deliverable


async def solve_project(
    project: Project, *, manager_client: LLMClient | None, specialist_clients: dict[str, LLMClient],
    tracer: Tracer | None = None, gold_plan: bool = False, mode: str = "specialists",
    parallel: bool = True, nested: bool = False,
) -> tuple[ProjectPlan | None, Deliverable | None]:
    """Plan (manager or gold) then dispatch. Returns (plan, deliverable); (None, None) when planning fails.

    nested=True asks the manager for a ProjectSpec and runs the flat plan it compiles to. Only the
    spec's tasks reach specialists; the whole spec ships with the deliverable as SPEC_PATH.
    """
    t0 = time.time()
    spec: ProjectSpec | None = None
    if gold_plan:
        plan_obj = project.plan
        if plan_obj is None:
            raise ValueError(f"project {project.id} has no gold plan")
        if tracer is not None:
            tracer.record(kind="plan", caller="gold", callee="plan", ok=True, mode=mode,
                          project_id=project.id, output=str(len(plan_obj.tasks)))
    else:
        assert manager_client is not None, "manager_client is required unless gold_plan=True"
        try:
            ctx = {"project_id": project.id, "mode": mode}
            if nested:
                spec = normalize_spec(await manager_client.acomplete(
                    SPEC_SYSTEM, user_prompt(project.description), ProjectSpec,
                    caller="dispatch", callee="manager", ctx=ctx,
                ))
                plan_obj = to_plan(spec)  # a spec that does not compile is a failed plan
            else:
                plan_obj = await manager_client.acomplete(
                    MANAGER_SYSTEM, user_prompt(project.description), ProjectPlan,
                    caller="dispatch", callee="manager", ctx=ctx,
                )
        except Exception as e:  # noqa: BLE001
            if tracer is not None:
                tracer.record(kind="plan", caller="dispatch", callee="manager", ok=False, mode=mode,
                              project_id=project.id, error=_err(e))
            _final(tracer, project.id, mode, t0, None, f"plan failed: {_err(e)}")
            return None, None
        if tracer is not None:
            tracer.record(kind="plan", caller="dispatch", callee="manager", ok=True, mode=mode,
                          project_id=project.id, output=str(len(plan_obj.tasks)))
    try:
        deliverable = await run_plan(project.id, plan_obj, specialist_clients, tracer, mode=mode,
                                     parallel=parallel, prompts=spec_task_prompts(spec) if spec else None)
    except Exception:  # noqa: BLE001 - _final already recorded the failure
        return plan_obj, None
    if spec is not None:
        deliverable.files.append(ArtifactFile(path=SPEC_PATH, content=spec.model_dump_json(indent=2)))
    return plan_obj, deliverable


def solve(project: Project, *, manager_client: LLMClient | None, specialist_clients: dict[str, LLMClient],
          tracer: Tracer | None = None, gold_plan: bool = False, mode: str = "specialists",
          parallel: bool = True, nested: bool = False) -> tuple[ProjectPlan | None, Deliverable | None]:
    """Sync wrapper for scripts and the CLI."""
    return asyncio.run(solve_project(
        project, manager_client=manager_client, specialist_clients=specialist_clients, tracer=tracer,
        gold_plan=gold_plan, mode=mode, parallel=parallel, nested=nested,
    ))


Runner = Callable[[Project], Deliverable]
