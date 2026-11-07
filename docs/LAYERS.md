# How this repository is layered

The repo was built in four layers by different hands. Each layer sits on the one below and replaced
or reused parts of it. Read this before changing anything that crosses layers.

```
L4  free-compute-ui (this branch)    $0 training loop · local + Ollama clients · web UI · specialist specs
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
