# Secondary experiments

Pre-registered on 2026-11-01, before any of these were run. The primary comparison in `PLAN.md`
(`specialists` vs `single` vs `monolith`) is unchanged. These explain *why* it comes out the way it
does.

**Selection rules**
- Specialist and manager knobs are chosen on `dev` only. `test` is scored once per final
  configuration.
- A new recipe replaces the old one only if it wins on held-out briefs by more than the 95% CI.
- Every experiment reports cost ($, GPU-hours) next to deliverable pass rate and latency.

## Hyperparameter tuning

| ID | What | Design | Owner | Est. $ |
|---|---|---|---|---|
| HP1 | Specialist LoRA recipe | 12 probe tasks per domain, one-factor-at-a-time around the default (r16, α=2r, lr 2e-4, 2 ep): rank {8,16,32}, lr {1e-4,2e-4,5e-4}, epochs {1,2,3}, target modules {attn, all}. Gate = `gate_task_ok` on the domain's eval split. | claude-2 | 4–6 |
| HP2 | Per-domain data efficiency | The same probe tasks at {50,100,200,400,800,1600} examples: gate vs examples per domain (where is the bottleneck — schemas or pages?). | claude-2 | 2–3 |
| HP3 | Manager recipe | rank {16,64} × lr {1e-4,3e-4} × epochs {1,2} on `train`, 4 runs. Report plan recall/precision/validity on `dev`. | claude-4 | 5–7 |

## Architecture variants

| ID | Question | Design | Owner | Est. $ |
|---|---|---|---|---|
| AR1 | Bigger specialist base? | `spec-*` on Qwen3-1.7B vs 0.6B at the same data: gate, deliverable pass rate, p50 latency. A second vLLM deployment. | claude-2 trains, claude-3 serves | 5–7 |
| AR2 | Is the manager's *order* load-bearing? | Dispatch the gold plan in dependency order vs shuffled order vs one flat level. Same artifacts, different plan quality feed: isolates decomposition value. | claude-3 | 1–2 |
| AR3 | Does specialization need four adapters, or is one enough? | One `spec-general` adapter on the union of all domain data vs the four. Deliverable pass rate per domain. | claude-2 | 2–3 |
| AR4 | Does merging work? | Merge the four adapters into one (linear and TIES) and run the `single` arm with the merged adapter. Replicates the "merged specialists < routed specialists" finding. | claude-2 | ≤1 |
| AR5 | Closed-loop repair | When a task or a seam check fails, re-plan only the affected subgraph once (manager sees the failing check). Error compounding vs extra latency. | claude-3 | 1–2 |
| AR6 | Manager size | 0.6B vs 1.7B vs 4B manager, same recipe: plan validity and task recall vs plan latency. | claude-4 | 3–5 |
| AR7 | Do interface symbols help the specialists? | Specialist prompts with the full symbol list vs a bare one-line task. Task pass rate and integration failures. | claude-1, claude-2 | ≤1 |
| AR8 | Verifier per domain | A second call per task with the task's own contract as the rubric, keep the artifact that passes more checks. Task pass rate vs 2× calls. | claude-3 | 2–3 |
| AR9 | Does a nested spec cost plan quality? | Pre-registered 2026-11-06. Same base and recipe, trained on `train` vs `spec-train` rows. Task recall/precision, validity and plan latency on `dev`, plus symbol coverage, test scoping and known references for the nested arm. The nested format replaces the flat one only if it stays within the 95% CI on task recall and validity; its extra latency is reported either way. | claude-4 | est. after pilot |
| AR10 | Are the manager's generated tests any good? | Pre-registered 2026-11-06, before scoring. The tests are prose, so each is compiled to an executable check using only values in its own text; a test that cannot be compiled does not count. A test counts only if it passes on the gold artifacts and fails on at least one broken version of them. Report compile rate, pass rate, broken versions caught per test, and tests per task, on `dev` with the gold spec's tests as a control. WebGen-Bench's 101 test briefs are a held-out check of real wording only and are never trained on. | orchestrator | under 2 |

**Order:** cheap and decisive first (AR2, AR3, AR4, AR7), then HP1–HP3, then AR1 and AR6, then
AR5 and AR8. All training finishes before the final grid.
