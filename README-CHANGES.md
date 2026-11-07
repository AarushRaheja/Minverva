# Architecture refactor: one manager SLM, four domain specialists

This document records the refactor that replaced the arithmetic-DAG research harness with the
manager-and-four-specialists architecture. It is a **before/after record**, not a tutorial — the
project README describes how the system works today.

## What the repository was before

```
word problem ─► manager SLM ─► PlanDAG (8 arithmetic ops) ─► rule router
              ─► hundreds of adapters (A1 … A256, op × digit bucket × format × surface)
              ─► T1/T2/T4/T5 topologies ─► numeric answer
```

- Task space: eight arithmetic ops (`add`, `sub`, `mul`, `div`, `percent`, `ratio`, `convert`,
  `round`), graded by an exact fraction executor against GSM8K-style word problems.
- "Specialization" meant **atomicity levels**: 1, 4, 16, 64 or 256 LoRA adapters on Qwen3-0.6B,
  chosen by a deterministic router from the operands' digit buckets and number formats.
- A parallel-graph runtime (chain, star, parallel DAG, verifier) executed a `PlanDAG` of arithmetic
  nodes, with an oracle-swap error-attribution tool.
- Separate LiveCodeBench harness (`slm/codebench/`) measured single-call code generation.

Nothing in that design expressed *what the specialists are for*. Domains, roles, and the final
product were all missing.

## What it is now

```
project brief
   │
   ▼
manager SLM (Qwen3-1.7B + LoRA) ─► ProjectPlan: tasks tagged database | auth | network | frontend,
   │                                       each with dependency ids derived from interface symbols
   ▼
dispatcher — every ready task at a dependency level fires in parallel
   ├── spec-database   schemas                    src/database/<table>.sql
   ├── spec-auth       sessions, OAuth, guards    src/auth/*.py
   ├── spec-network    routers, typed clients     src/network/*.py · *.ts
   └── spec-frontend   pages, forms, shell        src/frontend/*.tsx
   ▼
integrator — merge artifacts, generate glue, check every seam
   ▼
Deliverable: one file tree + README + explicit pass/fail per check
```

Four fixed specialists, one adapter each, one dependency-ordered dispatch, one deterministic
integration step, one graded product.

## Concept mapping

| Before | After | Why |
|---|---|---|
| `Problem` (word problem, gold DAG, numeric answer) | `Project` (brief, gold `ProjectPlan`, task-level gold artifacts) | The unit of work is a project, not a word problem |
| `PlanNode` / `PlanDAG` (8 ops, literal or node args) | `Task` / `ProjectPlan` (domain, kind, target, deps) | Tasks belong to a specialist, not to an op |
| `AtomKey` + `atom_for` (rule router over operands) | `slm/domains.py` symbols (`table:orders`, `endpoint:GET /api/orders`, `guard:session`, `route:/orders`) | Routing is the manager's job; symbols define the seams |
| Atomicity levels A1/A4/A16/A64/A256 | Four named adapters: `spec-database`, `spec-auth`, `spec-network`, `spec-frontend` | Specialization is by domain, fixed by the architecture |
| `Answer` (`{"value": "42"}`) | `Artifact` (`files[]` + summary) | Specialists produce code, not numbers |
| `execute()` exact arithmetic executor | `integrate()` + `check_task()` | The "exact executor" becomes the integrator and its seam checks |
| Topologies T1 chain, T2 star, T4 DAG, T5 verify | `run_plan(parallel=True/False)` | One schedule matters: parallel per dependency level; serial is the latency control |
| Exact match vs gold answer | Deliverable pass rate (all checks green), task pass rate by domain, plan recall | The end product is a tree of files, graded at the seams |
| Trace kinds `llm`/`route`/`node`/`final` | `llm`/`plan`/`route`/`task`/`final` | Adds the manager's plan as a first-class, gradable event |
| `problem_id`, `node_id`, `dag_level` | `project_id`, `task_id`, `domain`, `dep_level`, `mode` | Same idea, project vocabulary |

## New and rewritten modules

| Path | What it does |
|---|---|
| `slm/domains.py` **(new)** | Domain catalog: task kinds per specialist, canonical file path per kind, `provides`/`requires` symbol rules, and the exact code tokens (`provide_token`/`use_token`) the grader matches |
| `slm/contracts.py` **(rewritten)** | `Task`, `ProjectPlan` (must use all four specialists; deps must point backwards), `Artifact`, `Deliverable`, `check_task`, `integrate`, specialist prompts, `Project`, `TrainExample`, Volume paths, `RegistryEntry` |
| `slm/pipeline/` **(new, replaces `slm/graph/`)** | `dispatch.py` (manager → parallel per level → integrator), `router.py` (task → domain adapter), `oracle.py` (gold artifact per task, driven by a contextvar) |
| `slm/manager/` **(rewritten)** | Manager prompt naming the four specialists and their kinds; plan scoring on validity, dependency satisfaction, domain coverage, task recall/precision; SFT rows; trainer-side logic |
| `slm/bench/catalog.py` **(new)** | Ten project templates (eight train, two held out) and the gold artifact renderer for every kind (SQL schema, session/OAuth/guard, FastAPI router, TS client, React page/form/shell) |
| `slm/bench/projects.py` **(new)** | Deterministic project generator; held-out templates are used only by `split="test"` |
| `slm/bench/build.py` **(rewritten)** | Writes `projects/{split}.jsonl`, `manager/{split}.jsonl`, `domains/{domain}.jsonl`, `manifest.json` |
| `slm/bench/score.py` **(rewritten)** | Deliverable pass rate, per-domain task accuracy, plan validity, latency, calls/tokens from traces; `gate_ok` for the trainer |
| `slm/train/` **(rewritten)** | One job per domain, fixed-budget guard against the manifest, per-kind gate, escalation policy, registry summary |
| `slm/baselines/monolith.py` **(rewritten)** | One-call monolith plus the single-generalist arm, both graded through the same integrator |
| `modal_apps/*.py` **(rewritten)** | `slm-data` (build), `slm-train` (four adapters), `slm-serve` (one multi-LoRA server, project evaluation), `slm-manager` (SFT + plan eval, plan export) |
| `README.md`, `PLAN.md`, `EXPERIMENTS.md`, `tasks/*`, `reports/...` **(rewritten)** | Documentation, pre-registration, and agent workstreams now describe the four-specialist system |

## Removed, and why

| Removed | Reason |
|---|---|
| `slm/graph/` (executors, grid, oracle, router) | Its node = arithmetic op; the dispatcher replaces it entirely |
| `slm/bench/{generator,templates,atoms}.py` | Arithmetic problems, digit buckets, A256 atom sampling |
| `slm/bench/gsm8k.py`, `slm/bench/elo.py`, `slm/bench/plots.py` | GSM8K loader, Bradley–Terry ratings, accuracy-vs-depth plots — all tied to the numeric answer space |
| `slm/codebench/`, `modal_apps/lcb_app.py` | A separate LiveCodeBench harness for single-call code generation; not part of this architecture |
| `slm/train/devdata.py` | Synthetic stand-in data for the atom space |
| Old tests for the above | Replaced by tests for the new contracts, domains, pipeline, data, scoring, manager and baselines |

`uv.lock` changed accordingly (`matplotlib` was only used by the deleted plots).

## Verification performed

- `uv run pytest -q` → **123 passed** (contracts and negative cases, all ten templates integrating
  green, parallel vs serial dispatch, failed-task handling, manager failure path, data build,
  trace-based scoring, monolith baseline, training logic).
- `uv run slm domains` / `slm bench sample --full` / `slm run --project 0` → an 18-file deliverable
  that passes every check, with generated `src/app.py` wiring both routers, the session dependency
  and the route guard.
- `python3 -m py_compile modal_apps/*.py` → all four Modal apps compile.
- No references to `PlanDAG`, `AtomKey`, atomicity levels or topologies remain in `slm/`.

## Not done in this refactor

- **No GPU or Modal run.** The `spec-*` adapters and the manager are untrained here; the pipeline is
  verified with fake clients, gold plans and oracle specialists only. Gates and the
  specialists-vs-monolith comparison are still open.
- **No migration of the existing `/vol` data.** The Volume layout changed (`data/atoms` →
  `data/domains`, `data/manager`, new `data/projects`), so rebuild data with
  `modal run modal_apps/data_app.py` and retrain; old adapters are not reused.

## How to pick this up

1. `uv sync && uv run pytest` — the offline contract tests are the fastest sanity check.
2. `uv run slm bench sample --n 2 --full` — see a brief, its gold plan and its interfaces.
3. `uv run slm run --project 0` — inspect a complete deliverable and the trace it produced.
4. `modal run modal_apps/data_app.py --scale 0.1` → `modal run modal_apps/train_app.py::pilot` →
   `modal deploy modal_apps/serve_app.py` → `modal run modal_apps/serve_app.py::evaluate`.
