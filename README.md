# Minverva: a manager SLM and four domain specialists

> Main repository from 2026-11-07, imported from `NOVA-SLM/nova-hacks` (`free-compute-ui` @ `6bbc9da`).
> Where things stand: [`docs/STATUS.md`](docs/STATUS.md). How to branch, commit and open PRs:
> [`CONTRIBUTING.md`](CONTRIBUTING.md). How the code got here: [`docs/LAYERS.md`](docs/LAYERS.md).

One **manager SLM** reads a project brief, splits it into tasks, and hands each task to the
specialist that owns it:

| Specialist | Adapter | Owns |
|---|---|---|
| Database | `spec-database` | Postgres schemas |
| Security/Auth | `spec-auth` | cookie sessions, OAuth hand-off, route guards |
| Network | `spec-network` | FastAPI routers + typed TypeScript clients |
| Frontend-Design | `spec-frontend` | React pages, forms, app shell |

Every specialist is a LoRA adapter on one Qwen3-0.6B base, trained only on its own domain's tasks
(auth data never teaches the database adapter, and so on). A deterministic **integrator** merges
their files, writes the application glue (`src/app.py`, `src/main.py`, `requirements.txt`), and
checks the seams between domains — every endpoint the frontend calls must exist, every table the
API queries must be defined, every imported module must be in the tree. What the end user gets is
one `Deliverable`: a file tree that either passes every check or names the check it failed.

```
project brief
     │
     ▼
manager SLM (Qwen3-1.7B + LoRA) ──► ProjectPlan: tasks tagged database | auth | network | frontend,
     │                                        with dependencies and interface symbols
     ▼
dispatcher: per dependency level, in parallel
     ├── database  spec-database   ──► Artifact (src/database/*.sql)
     ├── auth      spec-auth       ──► Artifact (src/auth/*.py)
     ├── network   spec-network    ──► Artifact (src/network/*.py, *.ts)
     └── frontend  spec-frontend   ──► Artifact (src/frontend/*.tsx)
     │
     ▼
integrator ──► Deliverable (one tree + glue + seam checks) ──► end user
```

- **Contracts:** [`slm/contracts.py`](slm/contracts.py) (Task, ProjectPlan, Artifact, Deliverable,
  `integrate`, specialist prompts), domain catalog in [`slm/domains.py`](slm/domains.py)
  (task kinds, interface symbols, canonical paths, contract tokens).
- **What changed in the refactor:** [`README-CHANGES.md`](README-CHANGES.md) (before/after, concept
  mapping, removed modules, what is still unmeasured)
- **Plan, experiments, pre-registration:** [`PLAN.md`](PLAN.md), [`EXPERIMENTS.md`](EXPERIMENTS.md)
- **Design + prior work:** [`reports/`](reports/), notes in [`research_notes/`](research_notes/)
- **Agent task files:** [`tasks/`](tasks/) (start with `PROTOCOL.md`)

## Run from a fresh clone

Requires [uv](https://docs.astral.sh/uv/). GPU work runs on [Modal](https://modal.com); nothing
heavy is installed locally.

```sh
uv sync
uv run pytest                          # offline: fake clients, gold plans, oracle specialists
uv run slm domains                     # the four specialists and their adapter names
uv run slm run --project 0             # one project end to end, oracle specialists, files written
uv run slm bench sample --n 2 --full   # a generated brief plus its reference decomposition
```

## Layout

| Path | What |
|---|---|
| `slm/domains.py` | Per-domain task kinds, interface symbols, canonical file paths, provide/use tokens |
| `slm/contracts.py` | Task/ProjectPlan/Artifact/Deliverable, `check_task`, `integrate`, specialist prompts |
| `slm/pipeline/` | Dispatcher (manager → specialists, parallel per dependency level), routing, oracle |
| `slm/manager/` | Manager prompt, plan scoring, SFT rows, trainer-side logic |
| `slm/bench/` | Project templates, gold artifacts, generator, data build, metrics from traces |
| `slm/train/` | One job per domain, fixed-budget guard, registry logic |
| `slm/baselines/` | Monolith (one model, one pass) and single-generalist arms |
| `slm/llm/` | `LLMClient.complete/acomplete`, fake, vLLM multi-LoRA, hosted |
| `slm/trace.py` | Append-only JSONL trace (`llm`/`plan`/`route`/`task`/`final`); every metric is from traces |
| `modal_apps/` | `slm-data`, `slm-train`, `slm-serve` (one server, four adapters), `slm-manager`, `slm-ollama` |
| `slm/arch/` | Architecture experiments: arms, runs, reports (`python -m slm.arch`) |
| `slm/ui/` | Web workbench (`slm ui`) and Textual workbench (`slm code`) |
| `evaluation/` | Coding-agent evaluation harness with sandboxed, independent grading |
| `tui/` | Terminal monitor for traces and `slm.arch` results (Rust, ratatui) |
| `docs/` | `STATUS.md`, `LAYERS.md`, and `results/` write-ups |

## Status

Detailed, current picture: [`docs/STATUS.md`](docs/STATUS.md).

- [x] Architecture frozen: four domains, task catalog, integrator checks, traces
- [x] Gold pipeline: gold plan + gold artifacts integrate with every check green (`uv run pytest`)
- [ ] Data: project briefs, manager rows, per-domain training files on the Volume
- [ ] Adapters: `spec-database`, `spec-auth`, `spec-network`, `spec-frontend` with gates
- [ ] Manager: SFT on `ProjectPlan`, plan recall/precision on held-out briefs
- [ ] Results: specialists vs single generalist vs monolith on deliverable pass rate and latency
