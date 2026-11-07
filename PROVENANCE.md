# Provenance

Minverva started as an import of `NOVA-SLM/nova-hacks` branch `free-compute-ui` @ `6bbc9da` (Minverva commit `b925d12`).
The Minerva pipeline came in by a second import, on 2026-11-07, from
`aggarwalaarush34-hash/Minerva-SLM-Pipeline-Compiled` branch `feat/contract-pipeline` @ `88c6cbf`
("Consolidate the manager, backend agents, frontend agent and integrator"). That repo had itself been assembled
from the sources in the table below. Both imports are plain copies, not merges of histories.

What the second import changed in Minverva:

- `slm/`, `modal_apps/`, `tests/` are the `feat/arch-bench` versions. `free-compute-ui` is an ancestor of
  `feat/arch-bench`, so every differing file was taken whole, and no Minverva file was lost.
- New: `minerva/`, `harness/`, `templates/`, `vendor/frontendslm/`, `scripts/`, `models/` (no weights),
  `results/`, `docs/consolidation/`.
- `pyproject.toml` keeps the name `slm` (so `uv.lock` and the TUI's root detection are unchanged) and gains the
  `minerva` command, the wheel package list, the vendored paths for pytest and the `stack` marker.
- Root `PLAN.md` and `EXPERIMENTS.md` are the `feat/arch-bench` versions (the source repo kept them in
  `docs/legacy-nova-hacks/`). `README.md`, `LICENSE`, `CONTRIBUTING.md`, `.github/` and `tui/` are Minverva's.

## Before the second import

This repo was assembled on 2026-11-07 from three sources, by plain import rather than a merge of their histories. To see
who wrote what, or why, go back to the source repo at the commit below.

| Path | Source | Commit |
|---|---|---|
| `slm/`, `modal_apps/`, `tests/`, `evaluation/`, `results/`, `models/`, `reports/`, `research_notes/`, `tasks/`, `notebooks/` | `NOVA-SLM/nova-hacks` branch `feat/arch-bench` | `9df574f` |
| The fixes in `slm/llm/vllm.py`, `slm/pipeline/`, `slm/serve/`, `modal_apps/serve_app.py` | `claude-3/r1-dispatch` (local only: the push to `NOVA-SLM` was refused, 403) | `70ea35f` |
| `vendor/frontendslm/` | `RatChakraborty/FrontEndSLM` branch `codex/model-pipeline-snapshot-20261107-v2` | `c7f5094` |
| Root `PLAN.md`, `EXPERIMENTS.md`, `README-CHANGES.md` | The nova-hacks top-level docs, unchanged | `9df574f` |

The first two were merged in a scratch clone. The one conflict was in `tests/test_pipeline.py`, where both sides append
tests; both were kept. The merged suite had 430 passed, 23 skipped before anything else changed.

## Changes to imported code

Everything else under those paths is unmodified.

| File | Change | Why |
|---|---|---|
| `slm/contracts.py` | `integrate(..., host_kinds=)` | Lets tasks be delivered by something other than a specialist. Default behaviour is unchanged |
| `modal_apps/specialist_eval_app.py` | `write_code(..., skip_kinds=, measure_latency=)` | Skips frontend tasks, and the timing re-runs that cost money. Defaults are unchanged |
| `vendor/frontendslm/src/frontendslm/prompts.py` | Adds `FULLSTACK_CONTRACT`, `FULLSTACK_DESIGN_GUIDANCE`, `is_fullstack`, and `api_contract` in the request | Lifts the no-backend ban for `contract_profile == "fullstack"`. The original contract still applies otherwise |
| `vendor/frontendslm/src/frontendslm/repair.py` | `component_repair_messages` uses the same profile | Otherwise repair would reinstate the ban and lose the API contract |
| `pyproject.toml` | Adds the `minerva` command and test paths (Minverva keeps the name `slm`) | |
| `.gitignore`, `models/SHA256SUMS` | Adapter weights left out of git, hashes recorded | See [DECISIONS](docs/consolidation/DECISIONS.md) |

`harness/evaluate.mjs` is a new file derived from `vendor/frontendslm/audit/evaluate.mjs` (audit 2.1). Viewports, axe scans
and the evidence shape are the same.

## Licences

- `vendor/frontendslm/`: MIT, © 2026 RatChakraborty (`vendor/frontendslm/LICENSE`).
- `nova-hacks` has **no licence file**, and has other contributors. The MIT `LICENSE` at this repo's root came from the
  repo's first commit and does not by itself license that code. See [ISSUES](docs/consolidation/ISSUES.md) #1.
- Models: Qwen base models are listed as Apache-2.0 in FrontEndSLM's lock files.
