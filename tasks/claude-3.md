# claude-3 — Serving & dispatcher (round 1)

Read `tasks/PROTOCOL.md` first. You own `slm/serve/`, `slm/pipeline/`, `slm/llm/vllm.py`,
`modal_apps/serve_app.py`, `tests/test_pipeline*.py`, `tests/test_serve*.py`.

## What exists
- `slm/pipeline/dispatch.py`: `run_plan` (dispatch every task per dependency level, parallel or
  serial, then `integrate`), `solve_project` / `solve` (manager plan → dispatch). Failures never
  raise: a failed task is a `kind="task"` event with `ok=False`; the integrator reports what is
  missing.
- `slm/pipeline/router.py`: task → domain adapter, one `kind="route"` event per task.
- `slm/pipeline/oracle.py`: `OracleSpecialist` answers with the gold artifact via the `CALL`
  contextvar (gold plan ⇒ every check green).
- `modal_apps/serve_app.py`: one vLLM multi-LoRA deployment serving the four adapters;
  `make_dummy_adapters`, `smoke`, `evaluate` (whole projects from inside Modal).
- `slm/serve/smoke.py`: warm latency per domain, parallel vs serial wall clock, speedup.

## Round 1 tasks
1. **Smoke on dummies.** `uv run modal run modal_apps/serve_app.py::main` with the untrained
   adapters. Report: first adapter load seconds, warm latency per domain, parallel vs serial wall
   clock and speedup on a gold plan, and whether the four adapters load without eviction
   (`max_loras=8` is deliberate). Fix `for_model()` sharing if the connection pool is not reused.
2. **Gate on quality.** After claude-2 publishes the registry, run
   `::evaluate --split dev --gold-plan` and report deliverable pass rate, per-domain task pass rate,
   first failing check, p50/p95 project latency, calls and tokens per project.
3. **Latency window (AR2).** Dispatch the same gold plan with `parallel=True` and `False` at
   concurrency 1 and 4. Report the critical-path formula's prediction vs the measured wall clock;
   the claim to support or refute is "wall clock tracks the level count, not the task count".
4. **Timeouts and retries.** Confirm a cold start is absorbed by `cold_start_timeout_s` and that a
   503 does not turn into a failed task. Add a test with a mocked transport for a 503-then-200
   sequence.
5. **Trace conformance.** Add `tests/test_serve.py` asserting exactly one `final` per project, one
   `route` + one `task` per task, and that `bench.score` can reconstruct the deliverable pass rate
   from the trace alone.

## Definition of done
- `uv run pytest -q` passes; the new serve/transport tests are offline (httpx mock transport).
- PR body: smoke table, evaluate table, latency window, $ spend.
- Spend cap this round: **$15** (a deployed L4 server is the main cost; stop it with
  `modal app stop slm-serve` when done).
