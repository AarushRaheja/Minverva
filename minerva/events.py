"""Append-only progress events for one run directory, so a UI can follow `build()` while it runs.

Each line of `events.jsonl` is one JSON object with `ts` (Unix seconds) and `event`:

    run_start   engine, brief, look, resumed, budget_usd, max_repairs, spent_usd, pid
    stage_start stage, round?, estimate_usd?
    stage_end   stage, round?, ok, cached, seconds, usd?, detail?
    run_end     status, stage?, detail, usd, exit_code      (status also "stopped" or "error" when interrupted)

Stages: plan, backend, seams, preflight, intent, architect, audit, critic (per frontend round), verify, project.
A resumed run appends to the same file; a reader keeps the events after the last `run_start`.
Nothing here is read back by the pipeline: the stage files in the run directory stay the source of truth.
"""

from __future__ import annotations

import json
import time
from contextlib import contextmanager
from pathlib import Path

EVENTS_FILE = "events.jsonl"


class Events:
    def __init__(self, run_dir: Path | None):
        self.path = run_dir / EVENTS_FILE if run_dir is not None else None

    def emit(self, event: str, **fields) -> None:
        if self.path is None:
            return
        row = {"ts": round(time.time(), 3), "event": event, **{k: v for k, v in fields.items() if v is not None}}
        with self.path.open("a") as handle:
            handle.write(json.dumps(row, default=str) + "\n")

    def cached(self, stage: str, *, round_: int | None = None, ok: bool = True, detail: str | None = None) -> None:
        """A stage whose saved result was reused: nothing ran and nothing was paid."""
        self.emit("stage_end", stage=stage, round=round_, ok=ok, cached=True, seconds=0.0, detail=detail)

    @contextmanager
    def step(self, stage: str, *, round_: int | None = None, estimate: float | None = None):
        """Emit stage_start now and stage_end when the block exits.

        The block may set `outcome["ok"]`, `["usd"]`, `["seconds"]` and `["detail"]`. An exception ends the stage as
        not ok and propagates.
        """
        started = time.monotonic()
        self.emit("stage_start", stage=stage, round=round_, estimate_usd=estimate)
        outcome: dict = {"ok": True}
        try:
            yield outcome
        except BaseException as error:
            detail = "stopped" if isinstance(error, KeyboardInterrupt) else f"{type(error).__name__}: {error}"[:300]
            self.emit("stage_end", stage=stage, round=round_, ok=False, cached=False,
                      seconds=round(time.monotonic() - started, 3), detail=detail)
            raise
        seconds = outcome.get("seconds")
        self.emit("stage_end", stage=stage, round=round_, ok=bool(outcome["ok"]), cached=False,
                  seconds=round(seconds if isinstance(seconds, (int, float)) else time.monotonic() - started, 3),
                  usd=outcome.get("usd"), detail=(outcome.get("detail") or None) and str(outcome["detail"])[:500])


NO_EVENTS = Events(None)
