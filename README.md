# Minverva: two prompts in, a reviewable full-stack codebase out

> Main repository from 2026-11-07. Imported from `NOVA-SLM/nova-hacks` (`free-compute-ui` @ `6bbc9da`), then
> the Minerva pipeline from `Minerva-SLM-Pipeline-Compiled` @ `88c6cbf` ([`PROVENANCE.md`](PROVENANCE.md)).
> Where things stand: [`docs/STATUS.md`](docs/STATUS.md). How to branch, commit and open PRs:
> [`CONTRIBUTING.md`](CONTRIBUTING.md). How the code got here: [`docs/LAYERS.md`](docs/LAYERS.md).

```sh
cd tui && cargo run --release          # press r, describe what you want and how it should look
# or, without the TUI:
uv run minerva build "A tracker for client invoices" --look "Warm, editorial, serif headings"
```

**What you want** goes to a nested manager SLM and trained backend agents. **How it should look** goes only to
the frontend agent, adapted from FrontEndSLM: it writes the UI, is audited in a real browser against the real
backend, and is repaired from the measured failures. An integrator turns that into one project you can run, with a
`REPORT.md` saying what was and wasn't checked.

> Read [`docs/consolidation/STATUS.md`](docs/consolidation/STATUS.md) for what has been shown. Generated apps are
> currently limited to list and create by title ([ISSUES](docs/consolidation/ISSUES.md) #3).

## The terminal UI

`tui/` (Rust, ratatui) starts builds, follows them live from the run directory's `events.jsonl`, and shows every
build in six views: Pipeline (stages and frontend rounds), Tasks, Timeline (time and $ per stage), Deliverable
(`project/` and screenshots), Log and Report. A build on real models shows its estimated cost, the budget cap and
where the data goes, and needs a `y` before anything is spent. See [`tui/README.md`](tui/README.md).

## Try it without spending anything

Needs [uv](https://docs.astral.sh/uv/), Rust, Node 22 and Postgres (`initdb`, `pg_ctl`, `psql` on your PATH).

```sh
uv sync
(cd harness && npm ci --ignore-scripts && npx playwright install chromium)
(cd templates/frontend && npm ci --ignore-scripts)

uv run pytest                                               # fast tests
MINERVA_STACK=1 uv run pytest tests/test_minerva.py         # real Postgres, FastAPI and a browser
uv run python scripts/check_mutants.py                      # proves the audit catches broken apps
uv run minerva build "Track invoices" --engine offline      # the whole path, with fixtures and no models
(cd tui && cargo test)
```

`--engine offline` ignores your brief's content, because a fixed template stands in for the manager. It tests the
plumbing only. `uv run minerva engines` lists the engines, where each sends your data, and what each costs.

## With the real models

`uv run minerva build "<what>" --look "<how>"` (or `r` in the TUI with engine `modal`) runs open-weight models on
your own Modal account: no third-party model API sees the prompts. It costs an estimated $0.50-1.20 per run, with
`--budget-usd` (default 3) as the hard stop. The run writes to `runs/<date>-<slug>/`; pass `--out` with that
directory (or press `e` in the TUI) to resume it without paying again for finished stages.

## How a build works

```
what ──► manager (Qwen3-1.7B + LoRA) ──► ProjectSpec ──► database, auth, network adapters (Qwen3-0.6B + LoRA)
                                                     ──► seam checks + backend preflight (stops before frontend spend)
how  ──► design intent (Qwen3-4B Instruct) ──► Architect (Qwen3-4B Thinking) writes App.tsx against api.ts
                                           ──► audit on the real stack ──► at most 1 repair ──► Critic
     ──► sign-up journey on the final tree ──► project/ + REPORT.md + exit code (0 verified, 10 works with
         defects, 20 fallback UI, 30 failed)
```

The backend agents are the four domain specialists that came before Minerva: one **manager SLM** plans, and one
LoRA adapter per domain writes that domain's files, trained only on its own domain's tasks.

| Specialist | Adapter | Owns |
|---|---|---|
| Database | `spec-database` | Postgres schemas |
| Security/Auth | `spec-auth` | cookie sessions, OAuth hand-off, route guards |
| Network | `spec-network` | FastAPI routers + typed TypeScript clients |
| Frontend-Design | `spec-frontend` | React pages and forms (used by `slm run`; `minerva build` uses the Architect instead) |

A deterministic **integrator** merges their files, writes the application glue, and checks the seams between
domains: every endpoint the frontend calls must exist, every table the API queries must be defined, every
imported module must be in the tree. The older one-command flow is still here: `uv run slm run --project 0`
(oracle specialists, files written), `uv run slm ui` (web workbench), `uv run slm code` (Textual workbench).

## Layout

| Path | What |
|---|---|
| `minerva/pipeline.py` | The build stages, budget, resume, events and report |
| `minerva/bridge/` | From the plan to what the frontend receives: API client, compiled tests, reference UI |
| `minerva/integrator/` | Merges everything into a project that runs |
| `minerva/verify/`, `harness/evaluate.mjs` | The audit on the real stack |
| `templates/frontend/` | The Vite + React + Tailwind template every generated app starts from |
| `vendor/frontendslm/` | The frontend architecture, from FrontEndSLM |
| `slm/domains.py`, `slm/contracts.py` | Task kinds, interface symbols, canonical paths; Task/ProjectPlan/Artifact/Deliverable, `integrate` |
| `slm/manager/` | Manager prompt, nested `ProjectSpec` (`spec.py`), enrichment, plan scoring, SFT rows |
| `slm/pipeline/` | Dispatcher (manager → specialists, parallel per dependency level), routing, finishing, oracle |
| `slm/bench/` | Project templates, gold artifacts, generator, variety, data build, metrics, Elo |
| `slm/train/` | One job per domain, fixed-budget guard, registry logic, free-GPU backprop loop |
| `slm/llm/` | `LLMClient`: fake, vLLM multi-LoRA, local (transformers + peft), Ollama, hosted, CLI |
| `slm/serve/` | Serving smoke tests, latency, adapters |
| `slm/arch/` | Architecture experiments: arms, runs, reports (`python -m slm.arch`) |
| `slm/ui/` | Web workbench (`slm ui`) and Textual workbench (`slm code`) |
| `slm/trace.py` | Append-only JSONL trace of `slm run` (`llm`/`plan`/`route`/`task`/`final`) |
| `modal_apps/` | `pipeline_app.py` (Minerva's real models and sandbox), `slm-data`, `slm-train`, `slm-serve`, `slm-manager`, `slm-ollama`, `slm-teacher`, `slm-tokens`, `specialist_eval_app.py` |
| `models/` | Adapter configs and `SHA256SUMS`; the weights live on the Modal volume `slm-vol` |
| `evaluation/` | Coding-agent evaluation harness with sandboxed, independent grading |
| `tui/` | The terminal UI for Minerva builds, `slm run` traces and `slm.arch` results (Rust, ratatui) |
| `scripts/` | `check_mutants.py`, `check_sandbox.py`: prove the audit can fail |
| `results/` | Raw results: `2026-11-07/` (arch-bench), `consolidation/` (Minerva) |
| `docs/` | `STATUS.md`, `LAYERS.md`, `consolidation/` (status, plan, decisions, issues) |
| `PLAN.md`, `EXPERIMENTS.md`, `README-CHANGES.md` | The nova-hacks plan, pre-registered experiments and refactor notes |
