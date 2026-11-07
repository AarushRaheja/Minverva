"""Latency window (task 3, AR2): plan shapes, the critical-path formula, and the trace report."""

from __future__ import annotations

import asyncio

import pytest

from slm.bench.catalog import TRAIN_TEMPLATES, build_plan
from slm.contracts import DOMAINS, specialist_prompt
from slm.pipeline.oracle import OracleSpecialist
from slm.serve.latency import (
    SHAPES, critical_path, estimate, parse_project_id, project_id, report, reshape, run_window,
)
from slm.trace import TraceEvent, Tracer

PLAN = build_plan(TRAIN_TEMPLATES[0])


def test_shapes_change_only_the_levels():
    levels = {s: len(reshape(PLAN, s).levels()) for s in SHAPES}
    assert levels == {"planned": 5, "flat": 1, "chain": len(PLAN.tasks)}
    for shape in SHAPES:
        shaped = reshape(PLAN, shape)
        assert [t.id for t in shaped.tasks] == [t.id for t in PLAN.tasks]
        # the premise of the experiment: every specialist gets the exact same prompt in every shape
        assert all(specialist_prompt(shaped, t) == specialist_prompt(PLAN, PLAN.task(t.id)) for t in shaped.tasks)


def test_unknown_shape_is_rejected():
    with pytest.raises(ValueError, match="unknown shape"):
        reshape(PLAN, "shuffled")


def test_critical_path_sums_the_slowest_task_of_each_level():
    seconds = {t.id: float(i + 1) for i, t in enumerate(PLAN.tasks)}
    want = sum(max(seconds[t] for t in level) for level in PLAN.levels())
    assert critical_path(PLAN, seconds) == want
    assert critical_path(reshape(PLAN, "flat"), seconds) == max(seconds.values())
    assert critical_path(reshape(PLAN, "chain"), seconds) == sum(seconds.values())


def test_project_ids_round_trip_and_other_ids_are_ignored():
    assert parse_project_id(project_id("chain", True, 4, 2, 3)) == ("chain", True, 4)
    assert parse_project_id("win-warmup") is None and parse_project_id("dev-0007") is None
    assert parse_project_id(None) is None


# --- report on a simulated trace (exact numbers, no timing) -----------------------


def _simulate(shape: str, parallel: bool, c: int, rep: int, seconds: dict[str, float],
              slowdown: float = 1.0) -> list[TraceEvent]:
    """The events run_plan would write if every task took exactly seconds[task] * slowdown."""
    plan = reshape(PLAN, shape)
    out = []
    for copy in range(c):
        pid = project_id(shape, parallel, c, rep, copy)
        clock = 0.0
        for level in plan.levels():
            ends = []
            for tid in level:
                start = clock if parallel else (ends[-1] if ends else clock)
                end = start + seconds[tid] * slowdown
                ends.append(end)
                out.append(TraceEvent(run_id="w", ts=0, kind="task", caller="dispatch", callee="a",
                                      project_id=pid, task_id=tid, t_start=start, t_end=end))
            clock = max(ends)
        out.append(TraceEvent(run_id="w", ts=0, kind="final", caller="dispatch", callee="integrator",
                              project_id=pid, output="pass", t_start=0.0, t_end=clock))
    return out


def _simulated_window(slowdown_at_4: float):
    seconds = {t.id: 1.0 for t in PLAN.tasks}
    events = [TraceEvent(run_id="w", ts=0, kind="final", caller="x", callee="y", project_id="win-warmup",
                         t_start=0.0, t_end=99.0)]  # the warm-up must not leak into any cell
    for shape in SHAPES:
        for parallel in (False, True):
            events += _simulate(shape, parallel, 1, 0, seconds)
            events += _simulate(shape, parallel, 4, 0, seconds, slowdown=slowdown_at_4)
    return report(events, PLAN)


def test_report_matches_the_formula_when_tasks_are_uncontended():
    w = _simulated_window(slowdown_at_4=1.3)
    n = len(PLAN.tasks)
    cells = {(c.shape, c.parallel, c.concurrency): c for c in w.cells}
    assert len(cells) == len(SHAPES) * 2 * 2
    for shape, levels in {"planned": 5, "flat": 1, "chain": n}.items():
        par, ser = cells[(shape, True, 1)], cells[(shape, False, 1)]
        assert (par.levels, par.tasks) == (levels, n)
        assert par.wall_s == par.predicted_s == levels and par.ratio == 1.0
        assert ser.wall_s == ser.predicted_s == n and ser.ratio == 1.0
        assert cells[(shape, True, 4)].ratio == 1.3 and cells[(shape, True, 4)].runs == 4
    assert w.s_per_task == 1.0
    assert w.s_per_level == 1.0 and w.r2_levels == 1.0  # one task-time per level: tracks levels
    assert w.serial_spread == 0.0  # serial wall is the task count whatever the shape
    assert w.concurrency_slowdown == 1.3


def test_report_needs_an_uncontended_baseline():
    events = _simulate("planned", True, 4, 0, {t.id: 1.0 for t in PLAN.tasks})
    with pytest.raises(ValueError, match="uncontended"):
        report(events, PLAN)


# --- harness end to end (real dispatch, real clock) ---------------------------------

DELAY = 0.01


class AsyncSlowOracle(OracleSpecialist):
    """Gold artifacts after a fixed async delay: a server with no contention at all."""

    async def acomplete(self, system, user, schema, *, caller="user", callee="model", ctx=None):
        await asyncio.sleep(DELAY)
        return self.complete(system, user, schema, caller=caller, callee=callee, ctx=ctx)


def test_run_window_end_to_end_tracks_levels(tmp_path):
    tracer = Tracer(run_id="window", trace_dir=tmp_path)
    clients = {d: AsyncSlowOracle(tracer=tracer) for d in DOMAINS}
    asyncio.run(run_window(PLAN, clients, tracer, mode="gold", concurrency=(1, 2), repeats=1))
    w = report(tracer.events(), PLAN)
    cells = {(c.shape, c.parallel, c.concurrency): c for c in w.cells}
    assert len(cells) == len(SHAPES) * 2 * 2 and all(c.tasks_ok == 1.0 for c in w.cells)
    par = [cells[(s, True, 1)].wall_s for s in ("flat", "planned", "chain")]
    assert par == sorted(par)  # 1 < 5 < 13 levels
    assert w.r2_levels > 0.9
    assert 0.5 * DELAY < w.s_per_level < 3 * DELAY
    assert w.serial_spread < 0.5
    for c in w.cells:
        assert 0.8 < c.ratio < 3.0, c  # the formula holds up to event-loop overhead


def test_estimate_counts_every_call_and_stays_cheap():
    est = estimate(PLAN)  # defaults: 3 shapes x 2 schedules x concurrency (1, 4) x 3 repeats + warm-up
    assert est["calls"] == len(PLAN.tasks) * (1 + 3 * 3 * 2 * (1 + 4))
    assert est["usd"] < 2  # under PROTOCOL's print-the-cost threshold at the assumed 2 s/call
