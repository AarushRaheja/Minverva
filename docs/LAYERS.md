# How this repository is layered

The repo was built in six layers by different hands. Each layer sits on the one below and replaced
or reused parts of it. Read this before changing anything that crosses layers.

```
L6  Minerva in Minverva (Nov 7)     `minerva build` imported; the tui drives it (events.jsonl, run dirs)
L5  arch-bench + consolidation      nested manager spec, trained backend adapters, FrontEndSLM frontend agent,
                                     real-stack audit, integrator (Minerva-SLM-Pipeline-Compiled @ 88c6cbf)
L4  free-compute-ui    $0 training loop · local + Ollama clients · web UI · specialist specs
                                     · primary-agent architecture experiments (slm/arch)
L3  fork refactor (PR #18, Nov 1)    manager SLM + 4 domain specialists build a web project
                                     (RatChakraborty's fork; the commit is authored by Codebuff, an AI agent)
L2  agent rounds (Oct 27–28)         4 Claude workstreams (claude-1..4) on branches, merged by the orchestrator:
                                     arithmetic DAG of 1–256 LoRA "atoms", vLLM multi-LoRA server, LiveCodeBench
L1  scaffold (Oct 27)                README, LLMClient + FakeClient, schemas, trace
```

## L1: scaffold (Aarush Raheja, Raunak Mondal)
`slm/llm/base.py` (one `LLMClient.complete(system, user, schema)` with validation, one retry and
tracing), `slm/llm/fake.py`, `slm/trace.py`. **Still load-bearing in every later layer**: every model
call in L3 and L4 goes through this interface, and every metric is computed from its traces.

## L2: arithmetic graph of specialists (34 commits, PRs #1–#14)
The original question was whether a graph of up to 256 hyper-specialised LoRA adapters on Qwen3-0.6B
beats one model on arithmetic word problems. Four Claude agents owned four workstreams
(`tasks/claude-N.md`, `tasks/PROTOCOL.md`) and spent about $30 of Modal credit:
341 adapters trained (multi-digit multiplication, percent/ratio and fractions failed at 0.6B), a
vLLM multi-LoRA server (8 adapters concurrent, 0.34 s warm), and a LiveCodeBench side study (best-of-5
beat the prompt-only code graph, a negative result that was kept).

**What survives from L2:** the agent protocol and workstream ownership, the vLLM client
(`slm/llm/vllm.py`, retries and connection pool), the Modal app shapes, the stats helpers
(`slm/bench/stats.py`), and the manager-training lessons (never truncate completions, retry with the
validation error, export plans).
**What L3 deleted:** `slm/graph/`, the atom generator, GSM8K, Elo, plots and `slm/codebench/`. The open
PRs #15–#17 and every `claude-*/r*` branch belong to L2 and no longer apply to `main`. Close them.

## L3: manager + four domain specialists (one commit, 84 files, +3.3k / −7.8k lines)
The task changed from arithmetic to *building a small web project*: a manager plans a `ProjectPlan`
whose tasks belong to `database`, `auth`, `network` or `frontend`. A dispatcher runs each dependency
level in parallel, and a deterministic integrator merges the files and checks every seam. Interfaces
are **symbols with exact code tokens** (`slm/domains.py`), which makes grading exact.
Frozen contracts: `slm/domains.py`, `slm/contracts.py`, `slm/trace.py` (kinds `llm/plan/route/task/final`).
Data: `slm/bench/catalog.py` (10 templates, gold plan + gold artifact per task). Nothing in L3 was
run on a GPU.

Known limits of L3, found while building L4:
- Gold artifacts are fixed templates with the entity name swapped in, so a specialist trained on them
  learns to fill in templates. Training gates will look excellent and prove little.
- `string.Template` left `import {{ createX }}` in every gold form (invalid TSX). Fixed in L4, data v2.
- `VLLMLoRAClient` defaults to `max_tokens=128`, which is far too small for an artifact. Callers must pass ~1024.

## L4: this branch
| Piece | Path |
|---|---|
| Specialist definitions, one place; system prompts rendered from them | `slm/specialists.py` |
| Backprop training loop for any GPU (Kaggle/Colab/MPS), Volume layout | `slm/train/backprop.py`, `notebooks/train_free.ipynb` |
| In-process adapter client; Ollama client for local models | `slm/llm/local.py`, `slm/llm/ollama.py` |
| Web UI (demo / vLLM / local backends) | `slm/ui/`, `uv run slm ui` |
| Primary-agent architecture experiments | `slm/arch/`, `docs/ARCHITECTURE_RESULTS.md` |

L4 doesn't change the integrator or the symbol contract, so L3's tests still hold. It adds new code
next to L3's and changes only the specialist system prompts and one gold template.

## L5: arch-bench and the Minerva consolidation (Nov 3–7)
`feat/arch-bench` (12 commits after `free-compute-ui`) moved the manager to a nested `ProjectSpec`
(`slm/manager/spec.py`), trained the manager and the database, auth and network adapters (weights on the
Modal volume `slm-vol`, hashes in `models/SHA256SUMS`), and fixed the gold artifacts. 70ea35f raised
`VLLMLoRAClient`'s default `max_tokens` from 128 to 768. The consolidation added `minerva/`: one command,
`minerva build "<what>" --look "<how>"`, that plans and writes the backend with those adapters, has
FrontEndSLM's Architect (`vendor/frontendslm/`) write the UI, audits the assembled app on real Postgres,
FastAPI and a browser (`harness/`), and ships `project/` plus `REPORT.md`. `spec-frontend` is unused by it.
Current state: `docs/consolidation/STATUS.md`.

## L6: Minerva in Minverva
The pipeline was imported as a whole (PROVENANCE.md). `minerva build` writes an append-only
`events.jsonl` in its run directory and prints `run: <dir>` first, so the ratatui `tui/` can start
builds, follow them live and show their stages, rounds, audit, report and project. The old `slm run`
flow and the Arms view still work.
