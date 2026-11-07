"""Latency window (claude-3 task 3, AR2): does wall clock track the level count or the task count?

One gold plan is dispatched in three shapes that send byte-identical prompts, because `deps` only
schedule tasks (specialists never see each other's artifacts):
  planned  the plan's own dependency levels
  flat     no deps: every task in one level
  chain    each task waits for the previous one: one task per level
Each shape runs parallel and serial, with 1 or more copies of the project in flight at once.

Critical-path formula: a parallel schedule waits for the slowest task of each level, so
    predicted parallel wall = sum over levels of max(task seconds in that level)
    predicted serial wall   = sum of all task seconds
with task seconds taken from uncontended runs (serial, concurrency 1). Reading the report:
`s_per_level` near `s_per_task` with `r2_levels` near 1 and `serial_spread` near 0 supports
"wall clock tracks the level count, not the task count"; `ratio` > 1 is contention or dispatch
overhead, and `concurrency_slowdown` is what extra projects in flight cost. Everything is
computed from trace events, keyed by the project ids this module writes.
"""

from __future__ import annotations

import asyncio
import statistics
from collections import defaultdict

from pydantic import BaseModel

from slm.contracts import ProjectPlan
from slm.llm.base import LLMClient
from slm.pipeline.dispatch import run_plan
from slm.trace import TraceEvent, Tracer

SHAPES = ("planned", "flat", "chain")
L4_USD_PER_HOUR = 0.80  # the rate modal_apps/train_app.py budgets with
IDLE_MINUTES = 10  # serve_app's scaledown_window: the server bills this long after the last request


def reshape(plan: ProjectPlan, shape: str) -> ProjectPlan:
    """Same tasks and prompts, different schedule: deps only decide the dependency levels."""
    if shape == "planned":
        return plan
    ids = [t.id for t in plan.tasks]
    if shape == "flat":
        deps = [[] for _ in ids]
    elif shape == "chain":
        deps = [[ids[i - 1]] if i else [] for i in range(len(ids))]
    else:
        raise ValueError(f"unknown shape {shape!r}; use one of {SHAPES}")
    tasks = [{**t.model_dump(), "deps": d} for t, d in zip(plan.tasks, deps)]
    return ProjectPlan.model_validate({**plan.model_dump(), "tasks": tasks})


def critical_path(plan: ProjectPlan, seconds: dict[str, float]) -> float:
    """Predicted parallel wall clock: each level waits for its slowest task."""
    return sum(max(seconds[t] for t in level) for level in plan.levels())


def project_id(shape: str, parallel: bool, concurrency: int, rep: int, copy: int) -> str:
    return f"win:{shape}:{'par' if parallel else 'ser'}:c{concurrency}:r{rep}:{copy}"


def parse_project_id(pid: str | None) -> tuple[str, bool, int] | None:
    """(shape, parallel, concurrency) of a window run's project id; None for anything else."""
    parts = (pid or "").split(":")
    if len(parts) != 6 or parts[0] != "win":
        return None
    return parts[1], parts[2] == "par", int(parts[3][1:])


async def run_window(
    plan: ProjectPlan, clients: dict[str, LLMClient], tracer: Tracer, *, mode: str = "specialists",
    shapes: tuple[str, ...] = SHAPES, concurrency: tuple[int, ...] = (1, 4), repeats: int = 3,
) -> None:
    """Dispatch every (shape, schedule, concurrency) cell `repeats` times; results live in the trace.

    Repeats are the outer loop, so slow drift (server warm-up, noisy neighbours) hits every cell."""
    await run_plan("win-warmup", reshape(plan, "flat"), clients, tracer, mode=mode)  # load every adapter
    for rep in range(repeats):
        for shape in shapes:
            shaped = reshape(plan, shape)
            for parallel in (False, True):
                for c in concurrency:
                    await asyncio.gather(*(
                        run_plan(project_id(shape, parallel, c, rep, i), shaped, clients, tracer,
                                 mode=mode, parallel=parallel)
                        for i in range(c)
                    ))


class Cell(BaseModel):
    shape: str
    parallel: bool
    concurrency: int
    levels: int
    tasks: int
    runs: int
    wall_s: float  # median project wall clock (its final event)
    predicted_s: float  # critical path (parallel) or task sum (serial), from uncontended task times
    ratio: float  # wall / predicted: ~1 when the formula holds
    tasks_ok: float  # latency is only comparable between cells of equal quality


class Window(BaseModel):
    cells: list[Cell]
    s_per_task: float  # median uncontended task seconds
    s_per_level: float | None  # slope of parallel wall vs level count, concurrency 1
    r2_levels: float | None  # share of that wall's variance the level count explains
    serial_spread: float | None  # (max - min) / median serial wall across shapes, concurrency 1
    concurrency_slowdown: float | None  # planned parallel wall at the highest concurrency / at 1


def _fit(xs: list[int], ys: list[float]) -> tuple[float | None, float | None]:
    if len(set(xs)) < 2:
        return None, None
    slope = statistics.linear_regression(xs, ys).slope
    try:
        r2 = statistics.correlation(xs, ys) ** 2
    except statistics.StatisticsError:  # constant wall clock: the level count explains nothing
        r2 = 0.0
    return round(slope, 4), round(r2, 4)


def report(events: list[TraceEvent], plan: ProjectPlan) -> Window:
    """Cells and the level-vs-task summary from a window run's trace (events of other runs are ignored)."""
    walls: dict[str, tuple[tuple[str, bool, int], float]] = {}
    task_s: dict[str, dict[str, float]] = defaultdict(dict)
    oks: dict[str, list[bool]] = defaultdict(list)
    for e in events:
        key = parse_project_id(e.project_id)
        if key is None or e.t_start is None or e.t_end is None:
            continue
        if e.kind == "final":
            walls[e.project_id] = (key, e.t_end - e.t_start)
        elif e.kind == "task":
            task_s[e.project_id][e.task_id] = e.t_end - e.t_start
            oks[e.project_id].append(e.ok)

    base_runs = [task_s[pid] for pid, (key, _) in walls.items() if not key[1] and key[2] == 1]
    if not base_runs:
        raise ValueError("no uncontended run (serial, concurrency 1) to take task seconds from")
    base = {t.id: statistics.median(r[t.id] for r in base_runs) for t in plan.tasks}

    groups: dict[tuple[str, bool, int], list[str]] = defaultdict(list)
    for pid, (key, _) in walls.items():
        groups[key].append(pid)
    cells = []
    for (shape, parallel, c), pids in sorted(groups.items()):
        shaped = reshape(plan, shape)
        predicted = critical_path(shaped, base) if parallel else sum(base.values())
        wall = statistics.median(walls[p][1] for p in pids)
        flags = [f for p in pids for f in oks[p]]
        cells.append(Cell(
            shape=shape, parallel=parallel, concurrency=c, levels=len(shaped.levels()),
            tasks=len(shaped.tasks), runs=len(pids), wall_s=round(wall, 4), predicted_s=round(predicted, 4),
            ratio=round(wall / predicted, 3) if predicted else float("nan"),
            tasks_ok=round(sum(flags) / len(flags), 3) if flags else 0.0,
        ))

    par1 = [c for c in cells if c.parallel and c.concurrency == 1]
    s_per_level, r2 = _fit([c.levels for c in par1], [c.wall_s for c in par1])
    ser1 = [c.wall_s for c in cells if not c.parallel and c.concurrency == 1]
    spread = round((max(ser1) - min(ser1)) / statistics.median(ser1), 4) if len(ser1) > 1 else None
    planned = {c.concurrency: c.wall_s for c in cells if c.parallel and c.shape == "planned"}
    slowdown = (round(planned[max(planned)] / planned[1], 3)
                if 1 in planned and len(planned) > 1 and planned[1] else None)
    return Window(cells=cells, s_per_task=round(statistics.median(base.values()), 4),
                  s_per_level=s_per_level, r2_levels=r2, serial_spread=spread,
                  concurrency_slowdown=slowdown)


def estimate(plan: ProjectPlan, *, shapes: tuple[str, ...] = SHAPES, concurrency: tuple[int, ...] = (1, 4),
             repeats: int = 3, s_per_call: float = 2.0) -> dict:
    """Projected calls, server minutes and $ for run_window, printed before launching (PROTOCOL).

    Copies in flight overlap, so a cell's wall is ~levels calls (parallel) or ~tasks calls (serial)."""
    n = len(plan.tasks)
    calls = n * (1 + repeats * len(shapes) * 2 * sum(concurrency))
    busy_calls = 1 + repeats * len(concurrency) * sum(n + len(reshape(plan, s).levels()) for s in shapes)
    minutes = busy_calls * s_per_call / 60 + IDLE_MINUTES
    return {"calls": calls, "server_minutes": round(minutes, 1),
            "usd": round(minutes / 60 * L4_USD_PER_HOUR, 2), "assumed_s_per_call": s_per_call}
