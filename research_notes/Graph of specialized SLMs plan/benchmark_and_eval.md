# Benchmark and Evaluation Design: Graph of 100-500 Hyperspecialized SLMs vs. a Single LLM

Scope: pick one primary benchmark (plus at most one secondary), define atomicity levels, topologies, metrics, and fair baselines, with all scoring automatic. Notes current as of 2026-10-27. About 16 tool calls were used, so some licensing and performance facts are listed as gaps rather than verified.

**Bottom-line recommendation (inference, built from the findings below):**
- **Primary benchmark:** a programmatically generated compositional arithmetic word-problem benchmark built on computation graphs (DAGs), in the style of GSM-Infinite. We control depth, width, operator mix, and operand size, and we know the gold DAG for every item. That gold DAG is what makes the atomicity sweeps, the topology comparison, per-node accuracy, error attribution, and parallelism measurement possible.
- **Secondary (real-world anchor):** the GSM8K test set (1,319 problems, MIT license). GSM-Symbolic can be used for evaluation only, as a robustness check, because its license is CC-BY-NC-ND.
- **Alternative secondary, if a "real-world" flavor matters more than math:** CORD receipt field extraction (CC BY 4.0), with specialists per field × document pattern.

---

## 1. Candidate tasks: data, licensing, decomposability, unlimited data, SLM performance

### Takeaway
Arithmetic or math word problems built from computation graphs are the best fit. They decompose naturally into operator-level skills, can be generated without limit with exact-match scoring, are under permissive licenses (GSM8K is MIT), and give 0.5B-1.5B models a known, meaningful baseline (Qwen2.5-0.5B/1.5B-Instruct score 49.6/73.2 on GSM8K, against 91.6 for 7B). Text-to-SQL and extraction are viable but harder to decompose cleanly. Several have restrictive or conflicting licenses.

### Cited Findings
**Math / arithmetic**
- GSM8K is distributed under the MIT licence. GSM-Symbolic is under CC-BY-NC-ND 4.0 — [Re-evaluation of GSM-Symbolic, arXiv 2605.28700](https://arxiv.org/pdf/2605.28700); the GSM-Symbolic HF repo includes a LICENSE-CC-BY-NC-ND-4.0 file — [HF apple/GSM-Symbolic](https://www.huggingface.co/datasets/apple/GSM-Symbolic/tree/main)
- GSM-Symbolic has main, P1, and P2 variants (folders in the HF repo) — [HF apple/GSM-Symbolic](https://www.huggingface.co/datasets/apple/GSM-Symbolic/tree/main)
- A 2026 paper critically re-evaluates the statistics behind GSM-Symbolic's conclusions ("The Importance of Being Statistically Earnest") — [arXiv 2605.28700](https://arxiv.org/pdf/2605.28700)
- GSM-Infinite (CMU + Meta, ICML 2025) generates problems from computational graphs. Adding unnecessary nodes and edges creates noise, so problems can be made arbitrarily difficult and long. It has Symbolic, Medium (add/sub), and Hard (mul/div) tiers. Performance shows a "consistent sigmoid decline" as complexity rises, and scaling inference compute exponentially gives only linear gains. Code is on GitHub (Infini-AI-Lab) — [GSM-Infinite arXiv 2502.05252](https://arxiv.org/pdf/2502.05252); [PMLR](https://proceedings.mlr.press/v267/zhou25m.html)
- Another paper used GSM-Infinite with 1,600 held-out examples and called it structured enough for controlled analysis yet realistic — [search summary of arXiv 2605.26099](https://arxiv.org/pdf/2605.26099) (secondary snippet)
- "Faith and Fate" (NeurIPS 2023) frames multi-digit multiplication, logic grid puzzles, and a DP problem as computation graphs. It argues that transformers reduce multi-step reasoning to "linearized subgraph matching", and that autoregressive performance can decay rapidly as task complexity increases — [NeurIPS 2023](https://proceedings.neurips.cc/paper_files/paper/2023/hash/deb3c28192f979302c157cb653c15e90-Abstract.html); [arXiv 2305.18654](https://arxiv.com/abs/2305.18654)
- "Teaching Arithmetic to Small Transformers" (ICLR 2024) finds that simple formatting changes, and chain-of-thought data with intermediate step results, significantly improve accuracy, sample complexity, and convergence for small models on arithmetic. Length generalization remains a challenge — [ICLR 2024](https://proceedings.iclr.cc/paper_files/paper/2024/hash/6bf82fdcbd92b6a7793b3894422d2437-Abstract-Conference.html); [code](https://github.com/lee-ny/teaching_arithmetic)

**Small-model baselines (math/code)**
- Official Qwen2.5 Instruct scores: 0.5B gets GSM8K 49.6, MATH 34.4, HumanEval 35.4, MBPP 49.6. 1.5B gets GSM8K 73.2, MATH 55.2, HumanEval 61.6, MBPP 63.2. 7B gets GSM8K 91.6, MATH 75.5, HumanEval 84.8, MBPP 79.2 — [Qwen2.5 blog](https://qwenlm.github.io/blog/qwen2.5-llm/)
- Third-party: the verl baseline table lists 36.4 GSM8K for the Qwen2.5-0.5B-Instruct HF checkpoint (56.7 after PPO). This conflicts with the official 49.6, likely because of a different prompt or answer extraction — [verl baselines](https://nano-verl.readthedocs.io/en/latest/algo/baseline.html); contradicted by [Qwen2.5 blog](https://qwenlm.github.io/blog/qwen2.5-llm/)
- Community fine-tunes of Qwen2.5-0.5B base on GSM8K report 34.7% (SFT, 3 epochs on 7,473 train samples) and 41.6% (SFT+GRPO), from model cards that are not independently verified — [pngwn SFT](https://featherless.ai/models/pngwn/qwen2.5-0.5b-gsm8k-sft); [towardtype1](https://featherless.ai/models/towardtype1/qwen2.5-0.5b-gsm8k)

**Synthetic compositional / BBH / CLUTRR**
- BIG-Bench Hard: 23 tasks, MIT license (per the GitHub page) — [suzgunmirac/BIG-Bench-Hard](https://github.com/suzgunmirac/BIG-Bench-Hard)
- BBH tasks such as Date Understanding, Dyck Languages, and Multi-Step Arithmetic (Two) have 250 items each. Multistep arithmetic covers +, -, ×, ÷ — [aiwiki BBH](https://www.aiwiki.ai/wiki/big-bench-hard)
- The CLUTRR generator (kinship relational reasoning) is CC-BY-NC 4.0, so non-commercial only — [facebookresearch/clutrr](https://github.com/facebookresearch/clutrr); [HF loader](https://huggingface.co/datasets/CLUTRR/v1/blob/main/v1.py)

**Text-to-SQL**
- Spider is CC BY-SA 4.0 per the HF card, although older HF metadata said cc-by-4.0 — [HF xlangai/spider](https://huggingface.co/datasets/xlangai/spider/blob/fbb01a4f128231b111c4a047b6d0f6bf36d1f5a6/README.md)
- Secondary papers disagree on BIRD's license: CC BY-NC 4.0, CC BY-NC-SA 4.0, and CC BY-SA 4.0 all appear — [BIRD-History arXiv 2608.29345](https://arxiv.org/pdf/2608.29345); [arXiv 2605.27791](https://arxiv.org/pdf/2605.27791)
- BIRD has about 12.7k question-SQL pairs over 95 databases. GPT-4 reached 54.89% execution accuracy against 92.96% for humans — [BIRD paper arXiv 2305.03111](https://arxiv.org/pdf/2305.03111)
- A 0.5B RL-tuned model reports 75.0% Spider-dev execution accuracy with 30-candidate voting (model card, not peer reviewed) — [FINER-SQL-0.5B](https://featherless.ai/models/thanhdath/FINER-SQL-0.5B-Spider)

**Structured extraction**
- CORD (receipts, NAVER Clova) is CC BY 4.0, and v2 is on HF. Derivatives such as cord-instruct carry different licenses (CC BY-NC) — [clovaai/cord](https://github.com/clovaai/cord); [Voxel51 card](https://docs.voxel51.com/dataset_zoo/datasets_hf/consolidated_receipt_dataset.html)

**Decomposed prompting precedent**
- DecomP (Khot et al., ICLR 2023) splits complex tasks into sub-tasks handled by a library of dedicated sub-task handlers. Each handler can be optimized, decomposed further, or replaced by a trained model or a symbolic function. It beat prior few-shot prompting with GPT-3 on symbolic reasoning and multi-hop QA. Code and data: github.com/allenai/DecomP — [arXiv 2210.02406](https://arxiv.org/pdf/2210.02406)

### Inferences
Comparison of the candidates:

| Candidate | License | Decomposability into 100-500 atoms | Unlimited programmatic data | Scoring | Verdict |
|---|---|---|---|---|---|
| Synthetic DAG arithmetic word problems (own generator, GSM-Infinite-style) | Ours | Excellent (op × operand bucket × format) | Yes | Exact match | **Primary** |
| GSM8K | MIT | Good, but decomposition is done by the manager in natural language | No, only 7.5k train (augment with synthetic) | Exact match on final number | **Secondary (real anchor)** |
| GSM-Symbolic | CC-BY-NC-ND | Same as GSM8K | Templates only; no derivatives allowed | Exact match | Eval-only robustness check; do not redistribute modified copies |
| MATH | (not verified) | Medium: heterogeneous topics, hard to atomize | No | Exact match with normalization | Skip |
| BBH multistep_arithmetic / dyck / word_sorting / date | MIT | Good per task, but only 250 items/task, so CIs are wide | Easy to regenerate in the same format | Exact match | Optional extra probe set |
| CLUTRR | CC-BY-NC | Good (relation composition) | Yes (generator) | Exact match | Fine for a non-commercial hackathon, but there are only about 20 relation types, so too few atoms |
| SCAN/COGS | (not verified) | Medium | SCAN is synthetic | Exact match | Tests compositional generalization, not speed; skip |
| Spider / BIRD by clause | Spider CC BY-SA; BIRD unclear | Medium: clauses interact (JOIN depends on schema) | Partially (SQL templates) | Execution accuracy | Possible, but clause-level specialists need schema linking, and the story is muddier |
| CORD / SROIE extraction | CORD CC BY 4.0; SROIE not verified | Good (field × doc type), but CORD has about 30 field classes | Limited (synthetic receipts possible) | Field-level exact match / F1 | Best "real-world" secondary alternative |
| HumanEval / MBPP code units | (not verified) | Weak: functions are not naturally sub-unit decomposable | No | pass@k execution | Skip |

- The synthetic DAG benchmark is the only candidate with all of these: a gold decomposition (enabling oracle-plan ablations), an unlimited train/test split, a controllable critical-path depth (needed for the parallelism story), and a controllable atom count.
- Expect a 0.5B-1.5B specialist fine-tuned on a single narrow op (for example, 4-digit × 2-digit multiply) to reach near-ceiling exact match, given the small-transformer arithmetic results. This is an inference to verify in a pilot, not a cited number.

### Gaps
- Licenses for GSM-Infinite code/data, MATH, SROIE, SCAN/COGS, HumanEval/MBPP, and BIRD (conflicting) were not verified from primary sources.
- I found no peer-reviewed numbers for 0.5B-1.5B models fine-tuned on single narrow arithmetic ops. Plan a pilot.
- I found no fine-tuned 0.5B-1.5B numbers on CORD field extraction.

---

## 2. Clearest non-strawman story; is a synthetic benchmark defensible?

### Takeaway
Yes, a synthetic compositional benchmark is defensible if three things hold: (a) it follows an established published design (GSM-Infinite, Faith and Fate), (b) it is paired with a real benchmark (GSM8K), and (c) the baselines include strong monoliths, a monolith with a calculator/code tool, and the "generalist adapter" control. The honest story is "accuracy degrades with compositional depth for monoliths; a graph of exact atomic specialists degrades more slowly and runs independent nodes in parallel." It is not "SLM graph beats a 7B on everything."

### Cited Findings
- Monolith accuracy declines sigmoidally with reasoning complexity on computation-graph problems, and exponential inference compute buys only linear gains — [GSM-Infinite](https://arxiv.org/pdf/2502.05252)
- Transformers solve compositional tasks through linearized subgraph matching, and performance can decay rapidly with complexity — [Faith and Fate](https://arxiv.com/abs/2305.18654)
- DecomP shows that modular sub-task handlers beat monolithic few-shot prompting, and that a sub-task handler can also be "a symbolic function" — [DecomP](https://arxiv.org/pdf/2210.02406)
- NVIDIA position paper: SLMs (under about 10B) are "sufficiently powerful, inherently more suitable, and necessarily more economical" for many agentic invocations, and heterogeneous multi-model agents are "the natural choice" — [arXiv 2506.02153](https://arxiv.org/pdf/2506.02153)
- On GSM8K the 7B monolith scores 91.6 against 73.2 for 1.5B and 49.6 for 0.5B, so the real-benchmark headroom for a 0.5B-based graph is large and nontrivial — [Qwen2.5 blog](https://qwenlm.github.io/blog/qwen2.5-llm/)

### Inferences
- **Strawman risks judges will raise:** (1) "A calculator does arithmetic perfectly, so why use specialists?" Include a monolith + Python/calculator (PAL-style) baseline and report it honestly. The graph's claimed advantage is then latency, cost, and a learned NL-to-op mapping, not arithmetic correctness alone. (2) "You fine-tuned the graph but not the monolith." The generalist-adapter control (Section 5) answers this. (3) "Synthetic data favors your design." The GSM8K anchor answers this.
- **Most likely outcome to plan for:** on deep synthetic DAGs (depth ≥ 6, many ops), the graph beats untuned 7B-8B models and is competitive with Haiku-class models. On GSM8K, the bottleneck becomes the manager's NL decomposition. A 0.5B manager probably will not beat 7B (91.6). Use a 1.5B manager and present GSM8K as "closes X% of the gap at Y× lower latency/cost." Report it either way; do not cherry-pick.
- **Headline plot:** accuracy vs. DAG depth (x-axis) for each system, plus latency vs. DAG width. The graph's curve should be flatter in accuracy, and its latency should scale with critical-path length rather than total node count.

### Gaps
- No published head-to-head of a 100+ fine-tuned-specialist graph vs. a monolith on GSM-style tasks was found. This is the novelty, but it also means there is no prior effect size to power-plan against.

---

## 3. Defining atomicity levels (4 / 16 / 64 / 256 specialists)

### Takeaway
Define atomicity as a factorial split of the operation space: op family × operand-size bucket × number format (× optional surface/phrasing type). Each level is a strict refinement of the previous one, so every coarse specialist's training data equals the union of its children's. The total training budget stays fixed across levels.

### Cited Findings
- GSM-Infinite already parametrizes problems by operation class (add/sub at Medium, mul/div at Hard) and by number of variables — [GSM-Infinite](https://arxiv.org/pdf/2502.05252)
- Small-model arithmetic accuracy is very sensitive to format and operand length (length generalization is hard), which justifies operand-size buckets as a meaningful specialization axis — [Teaching Arithmetic to Small Transformers](https://proceedings.iclr.cc/paper_files/paper/2024/hash/6bf82fdcbd92b6a7793b3894422d2437-Abstract-Conference.html)
- CORD's field classes are the natural axis for extraction specialists — [clovaai/cord](https://github.com/clovaai/cord)

### Inferences
Proposed nested scheme for the primary benchmark (the manager and router are extra and not counted):

| Level | # specialists | Partition |
|---|---|---|
| A1 | 1 | single generalist adapter (= the control baseline) |
| A4 | 4 | op family: {add/sub, mul, div/ratio/percent, unit-conversion/compare/round} |
| A16 | 16 | 8 ops {add, sub, mul, div, percent, ratio, unit-convert, compare/min/max} × 2 operand sizes {≤3 digits, >3 digits} |
| A64 | 64 | 8 ops × 4 operand buckets {1-2, 3-4, 5-6, 7+ digits} × 2 formats {integer, decimal} |
| A256 | 256 | 8 ops × 4 operand buckets × 4 formats {integer, decimal, fraction, percent/currency} × 2 surface types {bare expression, NL clause "x apples cost $y each"} |

- A256 lands inside the 100-500 target. To hit about 500, add a third surface type or 8 operand buckets.
- **Fixed-budget rule:** total fine-tuning examples (say 256k) and total adapter parameters (LoRA rank × count) are held constant or reported across levels. Otherwise atomicity is confounded with compute. Report both "fixed total data" and "fixed per-specialist data" curves if time permits.
- **Routing cost grows with atomicity:** at A256 the router must classify into 256 classes. Measure router accuracy separately. Use a deterministic router based on parsed op, digit count, and format where possible, so that "learned router" vs. "rule router" becomes an ablation.
- Alternative secondary atomicity (CORD): field (about 30 classes) × receipt layout cluster (4-8), giving roughly 120-240 specialists.
- SQL alternative: clause {SELECT, WHERE, GROUP BY, HAVING, ORDER BY, JOIN, nested, set-op} × pattern subtype × DB domain. Plausible, but clauses are not independent.

### Gaps
- No literature directly identifies the optimal atomicity for fine-tuned specialists. This is an empirical question for the experiment.

---

## 4. Topologies and metrics (including fair latency measurement)

### Takeaway
Compare four topologies on identical specialists: (T1) sequential chain, (T2) star (manager → specialists → manager aggregates), (T3) two-level hierarchical tree (manager → family routers → specialists), and (T4) DAG dataflow executor (independent nodes run in parallel per topological level). Measure latency on one shared serving stack (multi-LoRA serving on one GPU), at batch size 1 and under load, and report critical-path length alongside total calls.

### Cited Findings
- S-LoRA serves thousands of LoRA adapters on one GPU, keeping adapters in host memory and paging them in. It reports up to 4× throughput over HF PEFT and vLLM's naive LoRA. Adapter weight add/subtract swapping "significantly reduces overall serving throughput and increases total latency" — [S-LoRA arXiv 2311.03285](https://arxiv.org/pdf/2311.03285)
- Inference compute scaling yields only linear gains on deep computation graphs, so latency/compute budgets matter for monoliths too — [GSM-Infinite](https://arxiv.org/pdf/2502.05252)

### Inferences
**Topologies (all with the same manager and specialists; only the wiring changes):**
- T1 Chain: the manager emits ordered steps, executed one at a time. This is the no-parallelism ablation.
- T2 Star: the manager emits a plan with dependencies, but every result returns to the manager before the next dispatch.
- T3 Hierarchical: manager → op-family routers (4) → leaf specialists. This tests whether routing depth hurts.
- T4 DAG dataflow: the manager emits a JSON DAG once. An executor launches all ready nodes concurrently, and a final aggregator formats the answer. This is the "faster" claim.
- Optional T5: a verifier node (a specialist re-checks each node's output) as an accuracy/latency trade-off.

**Metrics (all automatic):**
- End-to-end exact-match accuracy, with a 95% CI.
- Per-node accuracy: compare each specialist's output to the gold DAG node value.
- Plan accuracy: the manager's DAG is isomorphic to the gold DAG (nodes, ops, edges, operands).
- Router accuracy: chosen specialist = gold (op, bucket, format) class.
- **Error attribution via oracle swaps** (made possible by the synthetic gold DAG):
  - gold plan + learned specialists → isolates specialist error
  - learned plan + exact Python executor → isolates manager error
  - gold plan + gold routing + learned specialists → isolates router error
  - Attribute each failure to the first erroneous component in topological order.
- Latency: wall-clock p50/p95 per problem; time to first token for the monolith; critical-path length (longest chain of sequential model calls) vs. total model calls (a parallelism ratio of total/critical); tokens generated on the critical path vs. total tokens.
- Cost: GPU-seconds per problem on owned hardware; $ per 1k problems for hosted baselines (Claude Haiku 4.5 is about $1/M input and $5/M output per aggregators — [anotherwrapper](https://anotherwrapper.com/llm-pricing/claude-haiku-4-5-20251001); confirm on Anthropic's pricing page).
- Accuracy-vs-depth and latency-vs-width curves (the headline plots).

**Fair latency protocol:**
1. Same GPU, same serving engine (vLLM or SGLang with multi-LoRA, or S-LoRA), same precision, and warm caches for all local models. Preload all adapters for the graph and report the adapter-swap overhead separately.
2. Report two regimes: (a) single-request latency at batch size 1, where the graph's parallel nodes are batched together within one request; and (b) throughput at a fixed request rate on the same hardware, since the parallel graph uses more concurrent slots.
3. Count the monolith's chain-of-thought tokens. A monolith with long CoT is the fair accuracy baseline, and its latency should include those tokens.
4. Hosted models (Haiku) include network latency. Report them in a separate column and do not claim "faster than Haiku" unless the margin exceeds measured network RTT plus variance.
5. Report median of ≥3 runs, with timers placed around the full pipeline (manager + router + specialists + aggregation), not just model calls.

### Gaps
- No published standard for measuring latency of multi-agent SLM graphs against monoliths was found. The protocol above is a recommendation, not an established norm.
- Real-world S-LoRA latency at 256 adapters with 0.5B bases was not verified. Pilot it.

---

## 5. Fair baselines and statistical rigor

### Takeaway
Use these baselines: the untuned base model (0-shot, 8-shot, 8-shot CoT); a single generalist LoRA trained on the union of all specialist data (the key control); a 7-8B open model with CoT (and optionally a tool); a monolith + calculator/code tool; and Claude Haiku-class. Use paired comparisons with bootstrap or clustered CIs, ≥2,000 synthetic test items per depth bin plus the full 1,319 GSM8K test set, and 3 training seeds.

### Cited Findings
- Miller (Anthropic) argues that evals are experiments. Treat questions as draws from a super-population, compute CLT standard errors, use clustered SEs when questions share a source, use paired differences between models to reduce variance, and plan sample size with power analysis — [arXiv 2411.00640](https://arxiv.org/pdf/2411.00640)
- The `errorbars` package example: on a 500-question benchmark at a 50% baseline, reliably detecting a difference at 80% power needs roughly a 9-point gap — [PyPI errorbars](https://pypi.org/project/errorbars/) (third-party package description)
- GSM-Symbolic's own conclusions have been challenged on statistical grounds, which is a warning to report variance properly — [arXiv 2605.28700](https://arxiv.org/pdf/2605.28700)
- Reference scores for choosing baseline sizes: Qwen2.5-7B-Instruct gets GSM8K 91.6 and MATH 75.5 — [Qwen2.5 blog](https://qwenlm.github.io/blog/qwen2.5-llm/)

### Inferences
**Baseline set (same base family for the SLM rows, for example Qwen2.5-0.5B/1.5B):**
1. Base SLM untuned: 0-shot, 8-shot, 8-shot CoT.
2. **Generalist adapter (A1):** one LoRA with the same total rank budget and the same total training data as the graph, trained on the union of all specialist tasks plus manager-style full solutions. If the graph does not beat this, the gain comes from fine-tuning, not specialization. This is the critical control.
3. Generalist adapter + the same graph scaffold (the manager calls the same single adapter for every node). This separates "decomposition/scaffold" from "specialization."
4. 7-8B open model (for example Qwen2.5-7B-Instruct or Llama-3.1-8B): CoT, plus a PAL/calculator variant.
5. Monolith + Python tool (honest upper bound on arithmetic correctness).
6. Hosted Claude Haiku-class: CoT, reported with cost and latency in a separate column.
7. Graph with oracle components (an upper bound for attribution, not a competitor).

**Statistical protocol:**
- Synthetic: ≥2,000 test items per depth bin (for example depths 2, 4, 6, 8, 12), fresh seeds, and no template overlap with training. Hold out some operand ranges or phrasing templates to test generalization rather than memorization.
- GSM8K: the full 1,319 test set. Optionally add GSM-Symbolic main/P1/P2 as eval-only robustness checks, respecting the ND license.
- Paired tests (McNemar or paired bootstrap) for every graph-vs-baseline comparison on identical items. Report 95% CIs. Use clustered SEs by template when items share templates (per Miller).
- 3 training seeds for specialists and the generalist adapter. Report mean ± std across seeds and CIs within seeds.
- Greedy decoding (temperature 0) for the main numbers. For any sampled results, report temperature and number of samples.
- Pre-register (in the repo) the depth bins, metrics, and primary comparison (graph T4 at A256 vs. generalist adapter A1 and vs. 7B CoT) before running.

### Gaps
- No prior effect-size estimates exist for this specific comparison. Run a 200-item pilot to size the test sets.
- Haiku-class latency and pricing in late 2026 should be confirmed from Anthropic's official pricing page. Aggregator figures were used here.
