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

## Results (measured 2026-11-07)

Same project briefs for every model; apps are started and used in a sandbox (real Postgres, real API calls,
rendered pages), not judged by reading the code.

| What | Minerva | Comparison |
|---|---|---|
| Cost per working app | **4.5¢** (GPU time) | Claude Opus 15.6¢ list → **3.5× cheaper**; Opus team of agents $1.12–7.04 → **25×+ cheaper** |
| Output tokens per build | **2,937** | Opus 7,183 (**2.4× fewer**), Haiku 10,600 (3.6×), Opus team 41,963 (**14×**) |
| Generation time per working app, batched on one GPU | **21.5 s** | Opus 56 s (**2.6× faster**), Haiku 46 s; batching alone gives a 9.6× speedup |
| Peak memory | **5.2 GB** RAM on a 16 GB laptop, offline; 3.2 GB GPU batched | Opus and Haiku run only on the provider's servers |
| Specialist size | **19 MB** LoRA per specialist on one shared base | n/a |
| Retraining | all four specialists in **21 min** on one GPU for **$0.30** | Opus cannot be retrained by you |

**Architecture beats the loop (same weights).** With the same `qwen3.5:4b` model, the manager + specialists
layout (`mgr-G4-promptfix`) scores **0.70** average run score vs **0.24** for a conventional tool-calling agent
loop, **2.9×** higher, on every project (invoice_tracker 0.83 vs 0.33, issue_board 0.63 vs 0.24,
stock_room 0.63 vs 0.14; 3 repeats each).

**Verify and repair lifts small models.** On LiveCodeBench (n = 454), checking and repairing its own
answer takes a 1.7B model from **14.3% to 24.0%**, ahead of best-of-5 sampling (18.1%, paired p ≈ 0.000007)
and of a 4B model answering once (22.9%).

**Restaurant ops dashboard (inventory, supply, billing) vs Claude.** Minerva built the full stack (React
front end, FastAPI, SQL, sign-up) in **49 files** for **$0.86**; Claude built a front end only (10 files)
for $2.91. That is **3.4× cheaper**, **2.2× fewer output tokens** (30,992 vs 67,813) and 36% fewer lines.

Raw rows and per-project scores: `slm/arch/` reports and [`docs/STATUS.md`](docs/STATUS.md).

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
