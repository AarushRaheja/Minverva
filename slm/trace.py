"""Append-only JSONL trace of every model call and every dispatch decision.

One file per run: .slm/traces/<run_id>.jsonl. Every metric in slm/bench/score.py is computed
from traces alone, so the trace is also the demo artifact.

FROZEN event kinds:
  kind="llm"    one per model attempt, written by LLMClient: tokens, latency, ok/error, attempt.
  kind="plan"   the manager's plan for one project: ok=True with `output` = task count, or
                ok=False + `error` when the plan never validated. `adapter` = "manager".
  kind="route"  one per dispatch decision: task -> domain adapter (no model call).
  kind="task"   one per task once it settles: `task_id`, `domain`, `adapter`, `dep_level`,
                `output` = "ok" or a short failure reason.
  kind="final"  exactly one per project: `output` = "pass" when the integrated deliverable
                passed every check, else "fail:<first failing check>"; ok=False + `error`
                when the run produced nothing at all.
"""

from __future__ import annotations

import time
import uuid
from pathlib import Path

from pydantic import BaseModel

TRACE_DIR = Path(".slm/traces")


class TraceEvent(BaseModel):
    run_id: str
    ts: float
    kind: str  # llm | plan | route | task | final
    caller: str
    callee: str
    model: str | None = None
    input_chars: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    latency_ms: float = 0.0
    attempt: int = 1
    ok: bool = True
    error: str | None = None
    # Pipeline context (FROZEN contract: every metric is computed from traces alone)
    mode: str | None = None  # specialists | single | monolith | gold
    project_id: str | None = None
    task_id: str | None = None
    domain: str | None = None
    dep_level: int | None = None
    adapter: str | None = None
    t_start: float | None = None  # wall times (time.time()) so overlapping levels can be overlaid
    t_end: float | None = None
    output: str | None = None


class Tracer:
    def __init__(self, run_id: str | None = None, trace_dir: Path = TRACE_DIR):
        self.run_id = run_id or time.strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:6]
        trace_dir.mkdir(parents=True, exist_ok=True)
        self.path = trace_dir / f"{self.run_id}.jsonl"

    def record(self, **fields) -> TraceEvent:
        event = TraceEvent(run_id=self.run_id, ts=time.time(), **fields)
        with self.path.open("a") as f:
            f.write(event.model_dump_json() + "\n")
        return event

    def events(self) -> list[TraceEvent]:
        return load(self.path)


def load(path: Path) -> list[TraceEvent]:
    return [TraceEvent.model_validate_json(line) for line in path.read_text().splitlines() if line]
