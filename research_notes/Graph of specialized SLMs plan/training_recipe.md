# Training Recipe: 100-500 Hyperspecialized SLM Specialists in a 10-Day Hackathon (Modal cloud GPUs)

Context: as of 2026-10-27. Training runs on **Modal** cloud GPUs (CUDA: PEFT / TRL / Unsloth). The Apple M4 16GB Mac (only ~2.7GB free disk, confirmed with `df`: 188Gi used of 228Gi) is for local dev and debugging only.

Recommended default recipe (summary):
- **Base:** Qwen3-0.6B (non-thinking mode) as the shared base for most specialists. Use Qwen3-1.7B or Llama-3.2-1B-Instruct for harder specialists. Gemma-3-270M is the "tiny" option for trivial classification and routing.
- **Adapters:** one LoRA per atomic task, all-linear targets, r=8-16, alpha=r to 2r, lr about 2e-4, 1-3 epochs, effective batch 8-16, loss on completions only.
- **Data:** 500-2,000 examples per task. Use programmatic generators wherever the task has a checkable answer (math steps, SQL fragments, format conversion). Use teacher distillation (batched Haiku or similar) for fuzzy extraction tasks.
- **Compute:** pack about 5-25 adapters per Modal container on L4/A10, so the base model loads once per container. 500 adapters cost roughly $20-60 of GPU time (estimate; see the cost section).
- **Storage:** about 10-20 MB per adapter (bf16, Qwen3-0.6B, r=8-16). 500 adapters come to about 5-10 GB, which **will not fit on the Mac's 2.7GB free**. Keep them on a Modal Volume or HF Hub.

---

## Q1. LoRA adapters on one shared base vs. fully separate tiny models

### Takeaway
For narrow tasks, LoRA on a shared 0.5-1.7B base is the better choice per unit of compute and storage. LoRA matches full fine-tuning when it is applied to all layers (incl. MLP) and is not capacity-limited. One adapter is about 1-4% of the size of a full fine-tuned 135M-270M model. One server can host many adapters over one base (LoRAX ran 25 adapters on one A100). Separate full fine-tunes of tiny models make sense only for edge cases, such as a specialist that has to ship standalone.

### Cited Findings
- LoRA matches full fine-tuning when (1) it is applied to all layers, especially MLP/MoE, and (2) the adapter isn't capacity-constrained. Attention-only LoRA underperforms MLP-only LoRA even at matched parameter count. — [Thinking Machines, "LoRA Without Regret" (Sep 2025)](https://thinkingmachines.ai/blog/lora/)
- The optimal LoRA LR is about 10x the full fine-tuning LR, and about 15x for very short runs (<~100 steps). With 1/r scaling, the optimal LR is roughly independent of rank. LoRA tolerates large batches worse than full fine-tuning; smaller batches are better. — [Thinking Machines](https://thinkingmachines.ai/blog/lora/)
- Datasets carry about 1 bit per token of loss. Even rank-1 LoRA on an 8B model (about 3M params) far exceeds the information needed for RL tasks. Narrow tasks need little capacity. — [Thinking Machines](https://thinkingmachines.ai/blog/lora/)
- LoRA Land: 310 adapters (10 bases x 31 tasks). 4-bit LoRA fine-tunes beat their base models by 34 points and GPT-4 by 10 points on average. 224 of 310 beat GPT-4. — [LoRA Land, arXiv 2405.00732 (2024)](https://arxiv.org/html/2405.00732v1)
- LoRAX serves 25 Mistral-7B adapters on one A100-80GB. TTFT stays under 200 ms at 100 concurrent users with adapter switching. — [LoRA Land](https://arxiv.org/html/2405.00732v1)
- Gemma 3 270M has 170M embedding params and only 100M transformer params, with a 256k vocab. Google positions it explicitly for task-specific fine-tuning (entity extraction, query routing, sentiment, compliance checks). — [Google Developers Blog](https://developers.googleblog.com/en/introducing-gemma-3-270m/)
- MLX-LM also supports `--fine-tune-type lora | dora | full`. — [mlx-lm LORA.md](https://github.com/ml-explore/mlx-lm/blob/main/mlx_lm/LORA.md)
- QLoRA (4-bit) uses about 4x less VRAM and is marginally less accurate. 16-bit LoRA is slightly more accurate and faster. — [Unsloth LoRA hyperparameters guide](https://unsloth.ai/docs/get-started/fine-tuning-llms-guide/lora-hyperparameters-guide)

### Inferences
- A full fine-tune of SmolLM2-135M is about 270 MB in bf16 per specialist, and Gemma-3-270M is about 540 MB. A Qwen3-0.6B r=16 adapter is about 20 MB (see Q4). Across 500 specialists, separate models cost 135-270 GB against about 10 GB of adapters.
- With bases at or below 1.7B, plain bf16 LoRA fits easily on T4/L4/A10, so **QLoRA is unnecessary**. 16-bit LoRA is faster and slightly more accurate. Reserve QLoRA for 3B-8B bases on a T4.
- DoRA is supported by PEFT and MLX, but I found no evidence that it is worth its extra training cost for narrow tasks. Use plain LoRA by default.
- From-scratch 10M-100M models are only realistic for very simple, closed-vocabulary tasks such as a classifier or tagger. They lose the pretrained language prior, so I would not use them for extraction or SQL.

### Gaps
- I found no head-to-head study of "LoRA on shared 0.6B" vs. "full FT of SmolLM2-135M" on identical narrow tasks, normalized for compute.
- I found no data on DoRA vs. LoRA specifically for sub-2B models on narrow tasks.

---

## Q2. Which base model is strongest for narrow structured tasks after fine-tuning

### Takeaway
The best published 2025 comparison (distil labs, Dec 2025) found Qwen3 the strongest family after fine-tuning. In the sub-2B range, Qwen3-1.7B ranked first and Qwen3-0.6B next. Llama-3.2-1B-Instruct was the "most tunable" (largest gain from fine-tuning). Gemma-3 and SmolLM2 trailed. Default pick: **Qwen3-0.6B**, with Qwen3-1.7B for harder specialists.

### Cited Findings
- distil labs benchmarked 12 models across 8 tasks after LoRA fine-tuning. Setup: 10,000 synthetic examples per task from a GPT-OSS-120B teacher, 4 epochs, lr 5e-5, LoRA r=64, identical hyperparameters for every model. — [distil labs blog (Dec 10, 2025)](https://www.distillabs.ai/blog/we-benchmarked-12-small-language-models-across-8-tasks-to-find-the-best-base-model-for-fine-tuning)
  - Post-fine-tune average rank: Qwen3-4B-Instruct-2507 (2.25), Qwen3-8B (2.75), Llama-3.1-8B (4.00), **Qwen3-1.7B (4.44)**, Llama-3.2-3B (4.56), **Qwen3-0.6B (5.11)**. Gemma-3-1B, Gemma-3-270M, SmolLM2-1.7B and SmolLM2-135M trailed (exact ranks not given).
  - "Most tunable" (largest gain): **Llama-3.2-1B-Instruct (3.44)**, Llama-3.2-3B (4.67), Qwen3-0.6B (4.78). Smaller models gain the most from fine-tuning.
  - Fine-tuned Qwen3-4B matched or beat the 120B teacher on 7 of 8 tasks (e.g., SQuAD 2.0: 0.71 vs. 0.52 for the teacher).
- Qwen3-0.6B config: hidden 1024, 28 layers, MLP 3072, 16 Q heads / 8 KV heads, head_dim 128, vocab 151,936, tied embeddings. — [HF config](https://huggingface.co/Qwen/Qwen3-0.6B/raw/main/config.json)
- In the SmolLM2 paper, the SmolLM2-1.7B base beats Qwen2.5-1.5B on HellaSwag, ARC and MMLU-Pro, but trails it on math and coding. — [SmolLM2 paper, arXiv 2502.02737](https://arxiv.org/pdf/2502.02737) (via search summary; this compares base models, not fine-tunes)
- In LoRA Land (2024, 7B-era bases), Zephyr-7b-beta / Mistral-7B were the best fine-tuning bases. Gemma-2b and Phi-2 were included and were weaker. — [LoRA Land](https://arxiv.org/html/2405.00732v1) (older result)
- Gemma-3-270M is designed for fine-tuning, with INT4 QAT checkpoints. — [Google Developers Blog](https://developers.googleblog.com/en/introducing-gemma-3-270m/)

### Inferences
- For math steps and SQL fragments, prefer Qwen. Qwen is math- and code-heavy in pretraining, and SmolLM2 trails Qwen2.5 there in its own paper. Turn off Qwen3 thinking mode (as distil labs did) so outputs stay short.
- Use Gemma-3-270M or SmolLM2-360M only for trivial classify/route/format specialists where latency matters more than accuracy.
- Mixing bases breaks the "one shared base" storage and serving advantage. Pick one base (Qwen3-0.6B) for at least 90% of specialists, and maybe a second (Qwen3-1.7B) for a hard tier.

### Gaps
- I found no published fine-tune comparison that includes Qwen3.5 small models or Gemma-3n at sub-2B sizes. Phi-4-mini (3.8B) is outside the size range and was not benchmarked here.
- The exact post-fine-tune ranks of Gemma and SmolLM2 in the distil labs post were not given.

---

## Q3. Data size, steps, rank, hyperparameters, and training time per adapter (Modal CUDA)

### Takeaway
For a narrow atomic task, use about 500-2,000 examples, 1-3 epochs, LoRA r=8-16 on all linear layers, alpha=r to 2r, lr about 2e-4 (cosine, 5-10% warmup), effective batch 8-16, and completion-only loss. This works out to roughly 100-400 optimizer steps. On a 0.6B base with short sequences, an adapter trains in a few minutes on an L4/A10 (my estimate, not a measured benchmark).

### Cited Findings
- Unsloth guidance: r of 16 or 32 (from 8-128). alpha = r or 2r. lr 2e-4 for LoRA/QLoRA. 1-3 epochs (>3 means diminishing returns and overfit risk). Batch 2 x grad-accum 8 = effective 16. Target all of q/k/v/o/gate/up/down. Dropout 0-0.1. Weight decay 0.01-0.1. Warmup 5-10%. Training loss below about 0.2 suggests overfitting. Train-on-responses-only gives about +1 pt. No minimum dataset size is given. — [Unsloth hyperparameters guide](https://unsloth.ai/docs/get-started/fine-tuning-llms-guide/lora-hyperparameters-guide)
- LoRA Land (2024): r=8, lr 2e-3, cosine, 3% warmup, 40K steps, batch 1 x grad-accum 16. Hardware: 4-bit QLoRA, single A10 24GB, gradient checkpointing. — [LoRA Land](https://arxiv.org/html/2405.00732v1) (this is much longer training than a hackathon needs)
- distil labs: 10K examples, 4 epochs, lr 5e-5, r=64. — [distil labs](https://www.distillabs.ai/blog/we-benchmarked-12-small-language-models-across-8-tasks-to-find-the-best-base-model-for-fine-tuning)
- Prefer smaller batches with LoRA. The optimal LoRA LR is about 10x the full fine-tuning LR. — [Thinking Machines](https://thinkingmachines.ai/blog/lora/)
- Distillation lowers data needs: distilling step-by-step reached better performance with fewer examples than standard fine-tuning. — [arXiv 2305.02301](https://arxiv.org/abs/2305.02301)
- Community anchors (anecdotal, no accuracy reported): a Qwen2.5-0.5B SQL LoRA (r=8, alpha=16) trained on only 250 examples — [HF card](https://huggingface.co/aijadugar/qwen2.5-0.5b-sql-lora). A Qwen2-0.5B DuckDB SQL model trained on 10K rows — [HF card](https://huggingface.co/Omaratef3221/Qwen2-0.5B-Instruct-SQL-query-generator). A controlled T5-small (60M) WikiSQL LoRA rank/module sweep used 5,000 examples — [arXiv 2607.25583](https://arxiv.org/pdf/2607.25583).
- Unsloth claims about 2x speed and about 70% less VRAM for Qwen3 fine-tuning. The measured T4 figure is for TinyLlama-1.1B: 2.06x speed and -73.8% memory vs. HF baseline (older software stack). — [Qwen docs: Unsloth](https://qwen.readthedocs.io/en/latest/training/unsloth.html); [HF blog: Unsloth + TRL](https://huggingface.co/blog/unsloth-trl)
- MLX-LM (Mac) benchmark: about 250 tok/s for Mistral-7B LoRA on an M1 Max 32GB (batch 1, 4 layers). — [mlx-lm LORA.md](https://github.com/ml-explore/mlx-lm/blob/main/mlx_lm/LORA.md)

### Inferences (time estimates; my calculations, not measured)
- **Per-adapter workload:** 1,000 examples x ~300 tokens x 3 epochs is about 0.9M training tokens. Training FLOPs come to about 6 x 0.6e9 x 0.9e6, or roughly 3e15 (LoRA skips weight grads for frozen weights, so the real figure is somewhat less).
- At a realistic 10-30% utilization for a tiny model with short sequences, training time is about **1-3 min on A10/L4**, about **3-6 min on a T4**, and under 1 min on an A100/H100. On an A100/H100, per-step overhead dominates and the GPU sits underused.
- **Fixed overhead per container:** cold start, image pull and loading the base from a Modal Volume. Rough estimate: about 30-90 s. This is why **packing several adapters per container** matters: load the base once, then loop over tasks.
- **Default:** r=16 (r=8 for trivially simple tasks), alpha=32, lr 2e-4, 2 epochs, effective batch 8-16, max_seq_len 512, bf16 LoRA (no QLoRA) on L4/A10. Use fp16 on T4, which lacks bf16. Early-stop on a 100-example held-out set. Gate each adapter with an exact-match eval and retrain the failures with more or cleaner data.
- **Data size ladder:** start at 500 examples. If eval accuracy is below target, go to 2,000. Beyond about 5K examples there are diminishing returns for an atomic task (inference from distil labs using 10K for whole benchmarks, which are broader than atomic tasks).

### Gaps
- I found no measured per-adapter wall-clock benchmark for Qwen3-0.6B LoRA on T4/L4/A10/A100. Run a single pilot adapter on Day 1 and replace these estimates.
- I found no learning-curve study of examples needed vs. accuracy for sub-1B LoRA on atomic tasks.

---

## Q4. Adapter file size and total storage for 100/250/500 specialists

### Takeaway
LoRA params = r x sum(d_in + d_out) over the targeted linear layers. For all-linear Qwen3-0.6B, that is about 0.63M params per unit of rank: r=8 gives about 10 MB and r=16 about 20 MB in bf16 (double that if saved as fp32). 500 adapters come to about 5-10 GB. **That does not fit on the Mac's ~2.7 GB free disk.** Keep them on a Modal Volume or HF Hub, and pull locally only the handful being tested.

### Cited Findings (architecture inputs)
- Qwen3-0.6B: hidden 1024, 28 layers, MLP 3072, Q dim 16x128=2048, KV dim 8x128=1024. — [config](https://huggingface.co/Qwen/Qwen3-0.6B/raw/main/config.json)
- Qwen2.5-0.5B-Instruct: hidden 896, 24 layers, MLP 4864, 14 Q heads, 2 KV heads (head dim 64 gives KV dim 128). — [config](https://huggingface.co/Qwen/Qwen2.5-0.5B-Instruct/raw/main/config.json)
- Qwen2.5-1.5B-Instruct: hidden 1536, 28 layers, MLP 8960, 12 Q heads, 2 KV heads (KV dim 256), bf16. — [config](https://huggingface.co/Qwen/Qwen2.5-1.5B-Instruct/raw/main/config.json)
- A secondary blog says a Gemma 3 270M LoRA adds only about 3 MB. — [dasroot.net (2026, secondary; treat with caution)](https://dasroot.net/posts/2026/05/gemma-3-270m-lora-vs-larger-models-local-agentic-tasks/)

### Inferences (computed from the configs above; all-linear q/k/v/o/gate/up/down; bf16 = 2 bytes/param)

| Base | Params per rank | r=8 size | r=16 size | 100 x r16 | 250 x r16 | 500 x r16 |
|---|---|---|---|---|---|---|
| Qwen2.5-0.5B | 0.55M | ~8.8 MB | ~17.6 MB | ~1.8 GB | ~4.4 GB | ~8.8 GB |
| Qwen3-0.6B | 0.63M | ~10.1 MB | ~20.2 MB | ~2.0 GB | ~5.0 GB | ~10.1 GB |
| Qwen2.5-1.5B | 1.15M | ~18.5 MB | ~36.9 MB | ~3.7 GB | ~9.2 GB | ~18.5 GB |

- At r=8, halve the totals. For Qwen3-0.6B, 500 x r8 is about 5 GB.
- PEFT often keeps adapter weights in fp32, which doubles everything (Qwen3-0.6B r16 is about 40 MB). Cast to bf16 before saving.
- Attention-only r=8 on Qwen3-0.6B is about 2.3M params, or about 4.6 MB, so 500 adapters take about 2.3 GB. This is the only configuration that would barely fit on the Mac, but attention-only is weaker per Thinking Machines.
- Separate full models for comparison: SmolLM2-135M is about 270 MB each, so 500 is about 135 GB. Gemma-3-270M is about 540 MB each, so 500 is about 270 GB.
- **Mac constraints:** the Qwen3-0.6B base alone is about 1.2-1.5 GB in bf16, plus the Python env and torch/MLX packages. The 2.7 GB free disk can hold the base, a few adapters and maybe a 4-bit model, nothing more. Free up disk (HF cache, Xcode DerivedData) before any local work.

### Gaps
- I did not verify the exact file size of an actual saved safetensors adapter. The figures exclude small metadata overhead.

---

## Q5. Synthetic data: programmatic generators vs. teacher distillation; cost; evidence that small specialists beat big models

### Takeaway
Task-specific distillation lets small models beat much larger general models on narrow tasks. Examples: a 770M T5 beat 540B PaLM, LoRA Land adapters beat GPT-4 224 of 310 times, and a fine-tuned Qwen3-4B beat its 120B teacher on 6 of 8 tasks. Programmatic generators are free and come with verified labels, so use them for math, SQL and format tasks. Use a cheap hosted teacher with the Batch API for fuzzy tasks. Teacher cost for 500 tasks x 1,000 examples is roughly tens of dollars at current Haiku pricing (estimate).

### Cited Findings
- Distilling step-by-step: a 770M T5 outperforms 540B PaLM few-shot using 80% of the data on one benchmark, while standard fine-tuning of the same T5 did not match PaLM even with 100% of the data. It needs fewer examples than fine-tuning or standard distillation. Results span 4 benchmarks. — [arXiv 2305.02301 (2023)](https://arxiv.org/abs/2305.02301)
- LoRA Land: the biggest gains are on narrow tasks (WikiSQL, Reuters, DROP, legal, GLUE MNLI, with lifts of about +0.44 to +0.68 over the base). Fine-tuned models still trail GPT-4 on broad knowledge (MMLU -0.185) and on coding (Magicoder -0.396). — [LoRA Land](https://arxiv.org/html/2405.00732v1)
- Using 10K teacher-generated examples per task, a fine-tuned Qwen3-4B matched or beat the GPT-OSS-120B teacher on 7 of 8 tasks. — [distil labs](https://www.distillabs.ai/blog/we-benchmarked-12-small-language-models-across-8-tasks-to-find-the-best-base-model-for-fine-tuning)
- distil labs markets a workflow that needs only a task prompt plus about 50 labeled seed examples to generate training data. — [search summary of distil labs materials](https://www.wearedevelopers.com/videos/1654-distil-labs-small-model-training-made-simple.md?t=113) (vendor claim)
- Current Claude pricing (as shown on the pricing page): Haiku 5.5 at $0.10 input / $0.50 output per M tokens (prompts ≤100K); Sonnet 5.5 at $2 / $10. Batch processing saves 50%. — [claude.com/pricing](https://claude.com/pricing) (verify before budgeting; these are the figures the page returned on 2026-10-27)

### Inferences
- **Teacher cost estimate:** 500 tasks x 1,000 examples x ~300 output tokens is 150M output tokens, about $75 at list price or about $37 with Batch. Generate 10-20 examples per call with a cached system prompt so input stays small. 100 tasks would cost about $8-15. A local 7-8B teacher on the Mac is impractical: there is no disk for the weights (about 4-5 GB at 4-bit) and it is slow.
- **Programmatic first:** for arithmetic steps, unit conversions, SQL clause fragments, date and regex normalization, and JSON reshaping, write Python generators. They produce unlimited, exactly correct labels for $0 and give you a free exact-match eval.
- **Hybrid:** use the teacher to write diverse inputs (realistic messy text), compute labels programmatically where possible, and filter teacher labels with validators (schema check, SQL parse with sqlglot, numeric re-check). The distilling-step-by-step result suggests including short rationales for multi-step tasks, but keep the outputs terse for latency.
- Atomic specialists are the regime where small models win (LoRA Land narrow tasks). Avoid specialists that need broad world knowledge, where fine-tuned small models still lose to big general models.

### Gaps
- I have no measured throughput (examples/hour) for Batch API generation at this scale. Batch jobs can take hours, so submit all task batches on Day 1-2.

---

## Q6. Batch-training many adapters efficiently on Modal: fan-out vs. packing, time and dollar cost

### Takeaway
Write one parameterized `train_adapter(task_id)` with PEFT + TRL (or Unsloth). Use a Modal function that loads the base once per container and loops over a chunk of tasks (packing). Fan the chunks out with `.map()`. The Modal Starter plan caps you at **10 concurrent GPUs** and gives $30/month in free credits. 500 small adapters fit within about $20-60 of L4/A10 time and finish in a few hours of wall clock. Multi-LoRA systems such as mLoRA target multi-GPU, large-model setups and are overkill here.

### Cited Findings
- Modal GPU list prices: T4 $0.000164/s (~$0.59/h), L4 $0.000222/s (~$0.80/h), A10 $0.000306/s (~$1.10/h), L40S ~$1.95/h, A100-40GB ~$2.10/h, A100-80GB ~$2.50/h, H100 ~$3.95/h. — [modal.com/pricing](https://modal.com/pricing)
- Modal Starter plan: $30/month free compute, limits of 100 containers and **10 GPU concurrency**. Academic credits up to $10k for grad students and researchers (application required). — [modal.com/pricing](https://modal.com/pricing)
- mLoRA: LoRA-aware pipeline parallelism across GPUs, with about 30% lower average task completion time than FSDP. Example: 2 x Llama-2-13B on 4 x A6000. Deployed at AntGroup. — [arXiv 2312.02515](https://arxiv.org/abs/2312.02515)
- Unsloth gives about 2x speed and about 70% less VRAM (vendor claim; measured 2.06x on TinyLlama-1.1B on a T4). — [HF blog](https://huggingface.co/blog/unsloth-trl); [Qwen docs](https://qwen.readthedocs.io/en/latest/training/unsloth.html)
- Batching many adapters at serving time is proven: LoRAX ran 25 adapters on one A100. — [LoRA Land](https://arxiv.org/html/2405.00732v1)

### Inferences (cost and time model; estimates built from the Modal prices above and the Q3 per-adapter estimate)
Assumptions: Qwen3-0.6B, 1,000 examples x ~300 tokens, 2-3 epochs. Training takes about 2.5 min/adapter on L4 and about 1.5 min on A10. One-off overhead is about 1.5 min per container for cold start and base load.

**(a) Pure fan-out (1 adapter per container), L4:** about 4 min billed per adapter, or about $0.053 each.

| Adapters | GPU cost | Wall clock at 10 concurrent GPUs |
|---|---|---|
| 100 | ~$5 | ~40 min |
| 250 | ~$13 | ~1.7 h |
| 500 | ~$27 | ~3.3 h |

**(b) Packed (e.g., 10 adapters per container, base loaded once), L4:** about 2.65 min billed per adapter, or about $0.035 each.

| Adapters | GPU cost | Wall clock at 10 concurrent GPUs |
|---|---|---|
| 100 | ~$3.5 | ~27 min |
| 250 | ~$9 | ~1.1 h |
| 500 | ~$18 | ~2.2 h |

- On A10, cost is similar or slightly lower and runs are faster: about $0.03-0.05 per adapter.
- On a T4 (~$0.59/h, about 2x slower, fp16 only), cost is roughly the same and wall clock is longer.
- An A100/H100 is only worth it if you run several training processes per GPU concurrently, for example 4-8 adapter jobs sharing one A100-80GB, because a 0.6B LoRA leaves a big GPU mostly idle.
- **Budget reality:** even with 2-3x headroom for retries, hyperparameter pilots and the 1.7B tier, all training stays under about $100. The $30 free credit alone covers about 500 packed L4 adapters. Data generation (Q5) is a comparable cost.
- **Wall-clock bound:** the 10-GPU Starter concurrency is the binding constraint, not money. Upgrading the plan or packing more adapters per container raises throughput.
- **Practical script layout:** store `tasks/{id}/train.jsonl` and `eval.jsonl` on a Modal Volume. `@app.function(gpu="L4", volumes=..., timeout=3600)` takes `def train_chunk(task_ids)`, which loads the base and tokenizer once. For each task it wraps the base with `get_peft_model` (or Unsloth `FastLanguageModel.get_peft_model`), trains with TRL `SFTTrainer` (completion-only loss), evals exact-match, saves the adapter in bf16 to the Volume, then unloads the adapter (`model.unload()` / delete the peft wrapper) before the next task. Launch everything with `train_chunk.map(chunks)` and write per-task metrics to JSON for a leaderboard.
- Put a retry loop on low-scoring tasks: regenerate data, raise r or examples, and retrain only the failures.

### Gaps
- Modal also bills CPU and memory per second on top of GPU time. I did not fetch those rates, so the totals above are GPU-only.
- Cold-start and model-load times on Modal for a 1.5 GB base are my assumption, not measured.
- I found no maintained ASPEN/mLoRA support for Qwen3 small models. I did not evaluate its practicality for this use.

---

## Note: MLX-LM on the Mac (local dev and debug only)
- `pip install "mlx-lm[train]"`, then `mlx_lm.lora --model <hf_id> --train --data <dir with train/valid.jsonl> --iters 200 --batch-size 2 --num-layers 8 --grad-checkpoint`. Formats are chat/completions/text JSONL. Adapters save to `adapters/adapters.safetensors`, and `mlx_lm.fuse` merges them. — [mlx-lm LORA.md](https://github.com/ml-explore/mlx-lm/blob/main/mlx_lm/LORA.md)
- 16GB memory tips: batch size 1-2 with grad accumulation, fewer layers (4-8), `--grad-checkpoint`, QLoRA via a quantized model. — [mlx-lm LORA.md](https://github.com/ml-explore/mlx-lm/blob/main/mlx_lm/LORA.md); [insiderllm guide](https://insiderllm.com/guides/fine-tuning-mac-lora-mlx/)
- Use it to sanity-check the data format and the prompt template on one task with a 4-bit Qwen3-0.6B. With ~2.7 GB free disk, there is room for only one small base plus a few adapters. Note that MLX adapters are not directly PEFT-compatible: name mappings differ, so convert or retrain on Modal for production.
- I found no measured MLX tok/s benchmark for 0.5-1.5B models on an M4 16GB.
