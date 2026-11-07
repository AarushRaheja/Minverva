# Agent protocol (read first, every round)

You are one of four Claude agents (claude-1 … claude-4). The orchestrator reviews and merges your
work. Read `PLAN.md`, then `slm/domains.py` and `slm/contracts.py`, then your own `tasks/claude-N.md`.

The architecture is frozen: **one manager SLM splits a project brief into tasks for four domain
specialists (database, auth, network, frontend); the integrator merges their artifacts into one
deliverable.** Do not add a fifth domain, a second manager, or a new topology without a contract
request.

## Git
1. Branch from the latest `origin/main`: `git fetch origin && git switch -c claude-N/<round>-<topic> origin/main`.
2. Touch **only the paths you own** (see the PLAN.md table). Do **not** edit `slm/domains.py`,
   `slm/contracts.py`, `slm/llm/base.py`, `slm/trace.py`, `slm/cli.py`, or another agent's paths.
   If you need a contract change, put a **Contract request** in your hand-back and work around it.
3. Commit small and often. End every commit message with:
   `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`
4. When done: `uv run pytest -q` must pass. Push your branch and open a PR against `main` with
   `gh pr create`. PR body: what/why, how to run, test output, measured numbers, Modal spend, and
   end it with `🤖 Generated with [Claude Code](https://claude.com/claude-code)`.
5. **Never merge, never push to `main`, never force-push.** The orchestrator merges.

## Code
- Python 3.11+, Pydantic for every schema, small boring functions, no orchestration frameworks.
- Every model call goes through `LLMClient.complete/acomplete(system, user, schema, ctx=...)`.
  Pass trace context (`mode`, `project_id`, `task_id`, `domain`, `dep_level`, `adapter`) via `ctx`.
- A task's deliverable is an `Artifact` (files + summary); its contract is `provides`/`requires`
  symbols, checked by `contracts.check_task`. Never invent a second output format.
- CLI: expose your commands as a Typer app in `slm/<your_pkg>/__main__.py`
  (`uv run python -m slm.<pkg> …`). The orchestrator wires it into `slm/cli.py` at merge.
- Dependencies: the local env stays tiny. **Never install torch, transformers, vllm, peft, trl, or
  datasets locally.** They go only in `modal.Image` definitions, imported inside Modal functions,
  so `uv run pytest` stays offline. Add a new local dependency only with a one-line comment.
- Tests run offline with `FakeClient`, the oracle specialists (`slm.pipeline.oracle`), and the gold
  plans in `slm/bench/`. Code that only runs on Modal gets a pure-logic test locally and a logged
  smoke run on Modal (paste the numbers into the PR).

## Modal
- Shared v2 Volume `slm-vol`, mounted at `/vol`; layout in `contracts.PATHS`. Use
  `contracts.BASE_MODEL` (specialists) and `contracts.MANAGER_BASE` (manager). Cache HF under `/vol/hf`.
- Ship the package into images with `.add_local_python_source("slm")`.
- Every Function and server: `min_containers=0` and a short `scaledown_window`. Explicit `timeout`.
  After a smoke test, `modal app stop <app>` anything still running.
- Stay under your round's **spend cap**. Before launching any job estimated at more than $2, print
  the projected cost. **Stop launching new work at 80% of the cap** and report; never exceed it.
  Prefer L4. No H100 without orchestrator approval.
- Use only your own app names: `slm-data` (claude-1), `slm-train` (claude-2), `slm-serve`
  (claude-3), `slm-manager` (claude-4).

## Hand-back (your final message, ≤ 25 lines)
```
PR: <url>   branch: <name>   head: <sha>
Done: <bullets mapped to the task's Definition of Done>
Not done / deviations: <bullets>
Tests: <N passed>   Modal spend this round: $<x>
Measured: <numbers: deliverable pass rate, task pass rate, times, costs>
Contract requests: <none | exact change + why>
Blockers / questions: <none | …>
```
