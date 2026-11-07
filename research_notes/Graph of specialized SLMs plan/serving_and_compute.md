# Serving Hundreds of LoRA Specialists at Low Latency, and Compute for a 10-Day Student Project (Modal-primary)

Researched 2026-10-27. Numbers that come from 2023 papers, or that sources date as stale, are marked **[OLD]**. Numbers that come from third-party blogs and not from primary docs are marked **[3P]**.

## Q1. Multi-adapter serving systems: how many adapters can be resident, what switching costs, and can different adapters share one batch?

### Takeaway
Use vLLM or SGLang for cloud or GPU serving. Both keep several adapters on the GPU, keep many more in CPU RAM, load adapters at runtime, and batch requests for different adapters into one forward pass. Use LoRAX only as a reference design: it was archived on 12 Oct 2026. The local tools (llama.cpp, Ollama, MLX-LM) can load adapters but are built around one adapter, or one fixed set, at a time. None of them batches mixed adapters well.

### Cited Findings
**S-LoRA (paper, Nov 2023) [OLD, but the design is still the reference]**
- Serves "thousands of concurrent LoRA adapters" on one or more GPUs. All adapters live in main memory, and only those needed by running queries are moved to the GPU. "Unified Paging" puts adapter weights of different ranks and the KV cache in one memory pool. Custom CUDA kernels batch heterogeneous LoRA computations. Up to 4x the throughput of HF PEFT and of a naive vLLM. — [S-LoRA arXiv 2311.03285](https://arxiv.org/abs/2311.03285)
- Throughput stays nearly flat from 5 to 2,000 adapters (for example 8.05 to 7.61 req/s in one setup). The naive "vLLM-packed" baseline ran out of GPU memory at fewer than 5 adapters. — [S-LoRA PDF](https://arxiv.org/pdf/2311.03285) (via search summary)
- A secondary summary cites up to 30x over HF PEFT and caching of up to 2,000 adapters on one GPU. — [Spheron blog, Mar/Oct 2026](https://www.spheron.network/blog/lora-multi-adapter-serving-gpu-cloud/) [3P]

**Punica / SGMV (paper, Oct 2023) [OLD; the kernels now live inside vLLM and SGLang]**
- A new CUDA kernel batches GPU operations across different LoRA models. It reports 12x the throughput of state-of-the-art serving systems while "only adding 2ms latency per token." — [Punica arXiv 2310.18547](https://arxiv.org/abs/2310.18547)

**vLLM multi-LoRA (current docs)**
- `max_loras` is how many adapters can be active at once. Requests for different adapters run in parallel with base-model requests when it is set high enough. `max_lora_rank` should equal the largest adapter rank, because a higher value wastes memory. `--lora-target-modules` limits LoRA to some modules. — [vLLM LoRA docs (GitHub)](https://github.com/vllm-project/vllm/blob/main/docs/features/lora.md)
- Runtime loading: set `VLLM_ALLOW_RUNTIME_LORA_UPDATING=True`, then call `POST /v1/load_lora_adapter` (with `lora_name`, `lora_path`) or `/v1/unload_lora_adapter`. `load_inplace: true` replaces an adapter that is already loaded. Resolver plugins load an adapter the first time a request names it: `lora_filesystem_resolver` reads from `VLLM_LORA_RESOLVER_CACHE_DIR`, and `lora_hf_hub_resolver` reads from `VLLM_LORA_RESOLVER_HF_REPO_LIST`. The docs flag the HF resolver as insecure and not for production. — [vLLM LoRA docs](https://github.com/vllm-project/vllm/blob/main/docs/features/lora.md)
- Defaults (secondhand): `max_loras` = 1, and `max_cpu_loras` defaults to `max_num_seqs`. The example config is `--max-loras 8 --max-cpu-loras 64 --max-lora-rank 64 --max-num-seqs 64`. — [Spheron blog](https://www.spheron.network/blog/lora-multi-adapter-serving-gpu-cloud/) [3P]
- Switching cost tiers (secondhand, qualitative): sub-millisecond when the adapter is already on the GPU, tens of ms from CPU RAM, hundreds of ms from disk or S3. — [Spheron blog](https://www.spheron.network/blog/lora-multi-adapter-serving-gpu-cloud/) [3P]
- When each request needs a different adapter that must come from disk, prefill latency rises, but decode latency is mostly unaffected. — [BD-LoRA arXiv 2510.23346](https://arxiv.org/pdf/2510.23346)
- On one RTX 5090 with 3 adapters, "vLLM's LoRA adapter management introduces minimal overhead." A dual-GPU tensor-parallel setup was much slower. — [arXiv 2601.09527](https://arxiv.org/pdf/2601.09527)

**SGLang LoRA (current docs)**
- `--max-loras-per-batch` (default 8) sets how many adapters a batch can use and how much GPU memory is reserved for them. Pinned adapters are capped at `max-loras-per-batch - 1`. `--max-loaded-loras` caps adapters held in CPU memory; it must be at least `max-loras-per-batch`, and at most 2x that with overlap loading. Eviction is LRU by default, or FIFO. — [SGLang LoRA docs](https://docs.sglang.io/advanced_features/lora.html)
- One batch can mix adapters: the client sends a list of prompts and a matching list of adapter names, where `None` means the base model. `/load_lora_adapter` and `/unload_lora_adapter` work at runtime and accept a `pinned` option. — [SGLang LoRA docs](https://docs.sglang.io/advanced_features/lora.html)
- The `csgmv` (chunked SGMV) backend gives "20% to 80% latency improvements" over the Triton backend at high concurrency. Overlap loading cut median TTFT about 35% under adversarial conditions. The docs' illustrative example (not a benchmark): a 2 ms adapter load plus 20 ms prefill gives about 28 ms, but the worst case with overlap loading is about 82 ms because batching is lost. — [SGLang LoRA docs](https://docs.sglang.io/advanced_features/lora.html)
- SGLang v0.5.9 weight-loading overlap: up to 78% lower TTFT than sequential loading. — [Spheron blog](https://www.spheron.network/blog/lora-multi-adapter-serving-gpu-cloud/) [3P]

**LoRAX (Predibase)**
- Claims "thousands of fine-tuned models on a single GPU." Adapters load just-in-time without blocking other requests. "Packs requests for different adapters together into the same batch." "Adapter Exchange Scheduling" prefetches and offloads adapters between GPU and CPU in the background. Needs an Ampere or newer GPU, so it will not run on a T4. **The repository was archived (read-only) on 12 Oct 2026.** — [LoRAX GitHub](https://github.com/predibase/lorax)

**llama.cpp / llama-server**
- `--lora FILE` (scale 1) or `--lora-scaled FILE:SCALE`, repeated for each adapter, all loaded at startup. `GET/POST /lora-adapters` lists adapters and sets global scales by ID. A `/completion` request can pass its own `lora` array, which overrides the global scales for that request (added in PR #10994). **Requests with different LoRA configurations are not batched together.** — [simplified.guide](https://www.simplified.guide/llama-cpp/server-set-lora-adapter) [3P]; [llama.cpp commit #10994](https://cdn04132025.gitlink.org.cn/replica/llama.cpp/commit/0da5d860266c6928b8c9408efbd264ae59fedda6)

**Ollama**
- The Modelfile `ADAPTER` line applies a (Q)LoRA adapter, as Safetensors (Llama, Mistral and Gemma architectures) or GGUF, to the `FROM` base. Use non-QLoRA adapters, and the base must match. Each adapter therefore becomes its own model tag, chosen at model-load time. — [Ollama Modelfile docs](https://docs.ollama.com/modelfile); [Ollama import docs](https://docs.ollama.com/import)
- Ollama has reportedly switched its Apple Silicon backend from llama.cpp Metal to MLX. — via [towardsai article](https://pub.towardsai.net/i-tested-ollama-vs-lm-studio-on-the-same-mac-one-quietly-doubled-its-speed-ad8dcb6a89f7) [3P, unverified]

**MLX-LM**
- Adapters attach at load time with `--adapter-path`. `mlx_lm.fuse` merges an adapter into the base and can upload to HF Hub or export GGUF (fp16 Llama, Mistral and Mixtral only). LORA.md says nothing about multi-adapter serving or choosing an adapter per request. — [MLX-LM LORA.md](https://github.com/ml-explore/mlx-lm/blob/main/mlx_lm/LORA.md)
- vllm-mlx, a vLLM-style server built natively on MLX, reports continuous batching at up to 4.3x aggregate throughput with 16 concurrent requests on an M4 Max. The abstract says nothing about LoRA. — [arXiv 2601.19139](https://arxiv.org/abs/2601.19139)

### Inferences
- **Adapter sizes for this project (my own arithmetic from the Qwen2.5 configs, not sourced):** an r=16 LoRA on all linear layers is about 18 MB fp16 for Qwen2.5-0.5B and about 37 MB for Qwen2.5-1.5B. Attention-only (q,v) r=16 on the 1.5B model is about 4–5 MB. So **100 specialists on 1.5B all-linear r=16 come to about 3.7 GB, and 300 come to about 11 GB.** That decides whether adapters fit on the Mac. Smaller ranks, or targeting fewer modules, cut this linearly.
- For "hundreds of specialists" on a 0.5–1.5B base: vLLM with `--max-loras 16–32 --max-cpu-loras 300+ --max-lora-rank 16`, adapters on local NVMe or prefetched from HF Hub. Expect sub-ms selection for adapters already on the GPU and roughly tens of ms for adapters coming from CPU RAM.
- MLX-LM has no documented per-request adapter switching. Locally, switching means reloading the model (seconds) or keeping a small number of fused models loaded. A custom Python loop that swaps LoRA weights in memory between calls is possible, but it is not a documented feature.
- Do not build on LoRAX: it is archived and needs Ampere or newer.

### Gaps
- No primary-source measured number for vLLM's GPU-to-CPU adapter swap time. The "tens of ms" figure is a qualitative third-party claim.
- Not confirmed whether MLX-LM's `mlx_lm.server` accepts an `adapters` field per request (the source code was not checked).
- Not confirmed whether Ollama allows several ADAPTER lines.

## Q2. Can a graph of specialists run in parallel on one GPU, so wall-clock time follows the critical path instead of the sum of calls?

### Takeaway
Yes, on vLLM and SGLang (and in principle S-LoRA and Punica). Calls for different adapters that arrive at the same time join one continuously batched forward pass. Because small-model decode is memory-bandwidth bound, latency per decode step barely rises with batch size. A fan-out of N independent specialists therefore costs about one specialist call plus a small overhead, not N calls. On llama.cpp and Ollama the same calls run one after another.

### Cited Findings
- Punica: a mixed-adapter batch adds about 2 ms per token over a single-model batch. — [Punica](https://arxiv.org/abs/2310.18547) [OLD]
- S-LoRA: throughput is nearly unchanged from 5 to 2,000 distinct adapters. — [S-LoRA](https://arxiv.org/pdf/2311.03285) [OLD]
- SGLang mixes adapters in one batch. With overlap loading, a request whose adapter is not yet loaded can fall into a separate, smaller prefill batch, which the docs illustrate as about 82 ms versus about 28 ms. — [SGLang LoRA docs](https://docs.sglang.io/advanced_features/lora.html)
- vLLM runs requests for different adapters in parallel with each other and with base-model requests, as long as `max_loras` is high enough. — [vLLM LoRA docs](https://github.com/vllm-project/vllm/blob/main/docs/features/lora.md)
- llama.cpp does not batch requests with different LoRA configurations. — [simplified.guide](https://www.simplified.guide/llama-cpp/server-set-lora-adapter) [3P]
- Batching on Apple Silicon (base model only): vllm-mlx reaches 4.3x aggregate throughput at 16 concurrent requests. — [arXiv 2601.19139](https://arxiv.org/abs/2601.19139)

### Inferences
- To get critical-path latency, fire all specialists at the same DAG depth concurrently from the client (asyncio, or SGLang's list-of-adapters batch call). Set `max_loras` / `max-loras-per-batch` at least as large as the widest fan-out, and pin the specialists you call most.
- Locally on the Mac, parallel heterogeneous adapters are not supported out of the box. The options are to run the graph sequentially (fine if each call takes about 0.2 s) or to run several fused small models as separate processes, which memory limits to a few 0.5B models.

### Gaps
- **No published end-to-end measurement of the DAG critical path versus the sum of calls with multi-LoRA was found.** The team should measure it with `vllm bench serve` or a small asyncio harness. That would make a good original result for the project.

## Q3. Latency for short outputs (10–50 tokens): M4 16GB (MLX, llama.cpp) vs. T4/A10/A100 with vLLM vs. 7–8B models vs. a hosted Haiku-class API

### Takeaway
A 0.5B model on the M4 16GB decodes at roughly 90–230 tok/s with MLX, so a 30-token answer takes about 0.15–0.35 s plus a short prefill. Claude Haiku 4.5 measures 0.48 s TTFT and 86 tok/s, so the same answer takes about 0.8 s. Small local specialists can beat the API per call, and the advantage grows when calls run sequentially.

### Cited Findings
- Qwen2.5-0.5B with MLX on an M4 16 GB (10-core GPU), 1k context: about 90 tok/s in one community run and about 232 tok/s in a later run. An M4 Pro 48 GB gets about 185 tok/s. These are user-submitted and vary by oMLX version. — [oMLX community benchmarks](https://omlx.ai/benchmarks/1o5a72lk) [3P]
- A native MLX server beat llama.cpp by 21–87% throughput across 0.6B–30B models (M4 Max) and reached up to 525 tok/s. — [arXiv 2601.19139](https://arxiv.org/abs/2601.19139)
- Qwen2.5-7B Q4_K_M on an M4 Pro 24 GB is estimated at about 49 tok/s, but this looks modeled, not measured. — [willitrunai](https://willitrunai.com/can-run/qwen-2.5-7b-on-m4-pro-24gb) [3P, low confidence]
- MLX LoRA training runs about 250 tok/s on an M1 Max 32 GB (WikiSQL example). — [MLX-LM LORA.md](https://github.com/ml-explore/mlx-lm/blob/main/mlx_lm/LORA.md)
- Claude 4.5 Haiku (non-reasoning) via Anthropic's API: 0.48 s TTFT, 86.4 tok/s, $1 / $5 per M input/output tokens, measured on a 10k-input workload. AA marks the model **deprecated** and benchmarks only that workload now. — [Artificial Analysis](https://artificialanalysis.ai/models/claude-4-5-haiku)
- The Haiku 4.5 reasoning variant takes about 11–19 s to the first answer token on a 10k input, including thinking time. Do not use reasoning mode for routing or specialist calls. — [AA providers page](https://artificialanalysis.ai/models/claude-4-5-haiku-reasoning/providers)

### Inferences
- **Back-of-envelope (my estimates, to be measured):**
  - 0.5B on M4 via MLX: about 0.05 s prefill for a short prompt, then 30 tokens at 90–230 tok/s, so **about 0.2–0.4 s per call.**
  - 1.5B, 4-bit: roughly half that speed (bandwidth bound), so **about 0.4–0.7 s.**
  - 7B, 4-bit on the M4 base (about 120 GB/s): about 20–30 tok/s, so **about 1.2–1.8 s.**
  - Haiku 4.5: about 0.48 s + 30/86 s, so **about 0.8 s.** Real TTFT on short inputs is likely below the 10k-workload figure, and network RTT is extra.
  - vLLM on A10/A100 for 0.5–1.5B: decode in the hundreds of tok/s per stream, so roughly **under 0.2 s** for 30 tokens, plus network RTT to the cloud. A T4 (fp16, Turing) is slower and cannot use FlashAttention-2 or LoRAX.
- Since Haiku 4.5 is now marked deprecated, the report should compare against whichever Haiku-class model is current. Check the claude-api reference for current IDs and prices.

### Gaps
- **No sourced measured numbers for vLLM on T4/A10/A100 with a 0.5–1.5B model** at 10–50 output tokens. No sourced llama.cpp or Ollama numbers on the M4 base for 1.5B or 7B. The estimates above come from bandwidth reasoning and should be verified with `mlx_lm.benchmark`, `llama-bench` and `vllm bench`.

## Q4. Compute plan, with Modal (modal.com) as the primary platform for training and serving

### Takeaway
Run both training and serving on Modal. Adapters and the base model live on a v2 Volume (1 TiB/month free). Training runs as a `.map()`/`.spawn()` fan-out of LoRA jobs, capped at 10 GPUs at once on Starter. Serving is one vLLM multi-LoRA server on an L4 or A10, exposed as an OpenAI-compatible web endpoint and called concurrently from the Mac. The $30/month Starter credit covers roughly 37 L4-hours or about 27 A10-hours. That is enough for training plus benchmark windows, but not for a GPU kept warm around the clock (about $19/day on an L4). Apply for the academic grant (up to $10k) on day 1.

### Cited Findings
**Modal GPU prices (official pricing page, retrieved 2026-10-27; per-hour = per-second × 3600)**

| GPU (VRAM) | $/second | ≈ $/hour |
|---|---|---|
| T4 (16 GB) | 0.000164 | 0.59 |
| L4 (24 GB) | 0.000222 | 0.80 |
| A10 (24 GB; listed as "A10", no separate A10G) | 0.000306 | 1.10 |
| L40S (48 GB) | 0.000542 | 1.95 |
| A100 40 GB | 0.000583 | 2.10 |
| A100 80 GB | 0.000694 | 2.50 |
| RTX PRO 6000 | 0.000842 | 3.03 |
| H100 SXM5 | 0.001097 | 3.95 |
| H200 SXM | 0.001261 | 4.54 |
| B200 / B300 | 0.001736 / 0.001972 | 6.25 / 7.10 |

— [Modal pricing](https://modal.com/pricing)

- Other rates: CPU $0.0000131 per physical core per second (1 core = 2 vCPU, minimum 0.125 cores). Memory $0.00000222 per GiB per second. **Volumes $0.09/GiB-month with 1 TiB free each month.** Egress $0.04/GiB. — [Modal pricing](https://modal.com/pricing)
- **Plans:**
  - Starter: $0 + compute, **$30/month credits**, up to 3 seats, 100 containers, **GPU concurrency 10**, 200 deployed apps.
  - Team: $250/month + compute, $100 credits, 5,000 containers, GPU concurrency 50.
  
  — [Modal pricing](https://modal.com/pricing). One third-party changelog lists Team containers at 1,000; the official page says 5,000. — [search summary of usagepricing.com](https://usagepricing.com/blueprint/modal) [3P]
- **Credit programs:** up to **$10k for graduate students, labs and researchers** (academic program). Free credits for early-stage startups, and more via AWS Activate. **AWS, GCP and Azure credits cannot be spent on Modal.** — [Modal pricing](https://modal.com/pricing)
- Billing includes startup time and idle time before scale-down. — [morphllm](https://www.morphllm.com/modal-pricing) [3P]; consistent with [Modal cold-start guide](https://modal.com/docs/guide/cold-start) ("idle containers are billed")
- Reported change: since 1 Sep 2026 the Starter $30 no longer covers Modal's hosted "Shared Endpoints" token API. This does not affect your own vLLM container. — [usagepricing.com](https://usagepricing.com/blueprint/activity/modal-2026-08-14-packaging) [3P, two sources describe it differently]

**Modal Volumes (storing the base model and hundreds of adapters)**
- **Use v2:** no limit on total file count (max 262,144 files per directory), better throughput, faster commits and reloads, and hundreds of containers can write *distinct* files concurrently. v1 is still the default, tops out around 50k files and 500k inodes, and should have no more than about 5 concurrent writers. — [Modal Volumes guide](https://modal.com/docs/guide/volumes)
- Designed for up to 2.5 GB/s, not guaranteed. A container sees the Volume as of mount time and needs `.reload()` to see later commits. `.reload()` fails with "volume busy" while files are open. Background commits run every few seconds, and `.commit()` forces one. Concurrent writes to the same file are last-write-wins, and there is no file locking. — [Modal Volumes guide](https://modal.com/docs/guide/volumes)
- Guidance: bake a single model into the Image, or use a Volume when there are many models. In serving code, if a model is missing, reload the Volume and retry. Upload with `modal volume put` or `batch_upload()`; download with `modal volume get`. — [Modal Volumes guide](https://modal.com/docs/guide/volumes)

**vLLM (multi-LoRA) as a Modal web endpoint**
- Modal's official vLLM example:
  - CUDA 12.9 image with `vllm==0.21.0` and `HF_XET_HIGH_PERFORMANCE=1`.
  - Volumes `huggingface-cache` (at `/root/.cache/huggingface`) and `vllm-cache` (at `/root/.cache/vllm`, holding compile artifacts).
  - `@app.server(port=8000, scaledown_window=15*MINUTES, startup_timeout=10*MINUTES, target_concurrency=100)`.
  - `@modal.enter()` starts `vllm serve` with Popen.
  - OpenAI-compatible `/v1/chat/completions` at `https://<workspace>--<app>-server.us-east.modal.direct`.
  - `/health` returns **503 while no container is up, so clients must retry**.
  - A Locust load-test script is included.
  
  — [Modal vLLM example](https://modal.com/docs/examples/vllm_inference)
- **Cold start:** containers boot in about 1 s, but vLLM torch.compile and CUDA-graph capture take "tens of seconds to a few minutes" (about 10 s with a warm `vllm-cache`). `FAST_BOOT=True` (`--enforce-eager`) skips compilation, which suits services that often scale from zero. — [Modal vLLM example](https://modal.com/docs/examples/vllm_inference); [Modal cold-start guide](https://modal.com/docs/guide/cold-start)
- **GPU memory snapshots** (vLLM sleep mode plus `enable_memory_snapshot=True, experimental_options={"enable_gpu_snapshot": True}`) cut the median cold start for a 3B Ministral from about 118 s to about 12 s. These are Modal's own numbers, the feature was alpha as of Dec 2025, and current status is unverified. — [Modal blog, Ministral 3](https://modal.com/blog/mistral-3); [Modal vllm_snapshot example](https://modal.com/docs/examples/vllm_snapshot)
- **Keep-warm settings:**
  - `scaledown_window` defaults to 60 s and can be set from 2 s to 20 min.
  - `min_containers` sets a floor so the Function never scales to zero.
  - `buffer_containers` keeps spare idle containers for bursts.
  - Idle warm containers are billed.
  
  — [Modal cold-start guide](https://modal.com/docs/guide/cold-start)
- **Concurrency and endpoint options:** `@modal.concurrent(max_inputs=...)` lets one container take many requests at once, which vLLM needs for its continuous batching. `@modal.web_server(port)` exposes any HTTP server bound to 0.0.0.0. `@modal.asgi_app` and `@modal.fastapi_endpoint` also exist. — [Modal web endpoints guide](https://modal.com/docs/guide/webhooks)
- **Auth and limits:** proxy auth requires `Modal-Key` and `Modal-Secret` headers. Alternatively, check a Bearer token stored in a Modal Secret. New accounts get **200 req/s** (5 s burst multiplier), then HTTP 429. Request bodies can be up to 4 GiB. — [Modal web endpoints guide](https://modal.com/docs/guide/webhooks)
- Modal's examples include no official multi-LoRA example (none found). vLLM's own flags (`--enable-lora --max-loras --max-cpu-loras --max-lora-rank`, the runtime load endpoints, and `lora_filesystem_resolver` pointed at a mounted Volume path) carry over unchanged. — [vLLM LoRA docs](https://github.com/vllm-project/vllm/blob/main/docs/features/lora.md)

**Fanning out hundreds of LoRA training jobs**
- `.map()` / `.starmap()` run synchronously with at most **1,000 concurrent inputs per call**, and the SDK applies back-pressure. `.spawn()` returns a `FunctionCall` immediately; collect with `.get(timeout=…)` or later with `FunctionCall.from_id()`. `.spawn_map()` fires without handles, so jobs should write results to a Volume. — [Modal invocation methods](https://modal.com/docs/guide/function-invocation-methods)
- Queue limits: sync mode allows 2,000 pending and 25,000 total inputs per function. Async (spawn) allows **1M pending**. Submission rate limits are 200/s sync and 1,500/s async. Async results are kept 7 days, and **async calls keep running if the local caller exits**, whereas sync calls are cancelled about 2 min after the caller disconnects. — [Modal invocation methods](https://modal.com/docs/guide/function-invocation-methods)
- Real parallelism is capped by the plan: **10 GPUs at once on Starter**, 50 on Team. Parallelism can also be limited per function with `max_containers`. — [Modal pricing](https://modal.com/pricing); [Modal scaling guide](https://modal.com/docs/guide/scale)
- Modal now promotes "modal-dojo" for fine-tuning and RL; its Qwen3.5-4B GSM8K example is launched with `config.launch()`. The page gives no GPU, LoRA or timing details. — [Modal unsloth/dojo example page](https://modal.com/docs/examples/unsloth_finetune)

**Fallback platforms (short)**
- **Kaggle:** free 2xT4 or P100, about 30 GPU-h/week (shown in account settings, undocumented), 12 h sessions. — [gpuperhour, Sep 2026](https://gpuperhour.com/blog/free-cloud-gpus-and-credits) [3P]
- **Colab free:** a T4 when available, 12 h maximum session. Colab Pro for Education is closed to new signups. — [gpuperhour](https://gpuperhour.com/blog/free-cloud-gpus-and-credits) [3P]
- **Lightning AI free:** 1 Studio, 4 h restarts, 50 GB storage. **HF ZeroGPU:** 5 min/day free, 40 min/day on PRO. — [gpuperhour](https://gpuperhour.com/blog/free-cloud-gpus-and-credits) [3P]
- **Cheapest on-demand (28 Oct 2026):** RTX 3090 $0.29/h (LeaderGPU), L4 $0.59/h (RunPod, cheaper than Modal's $0.80), A100 $0.68/h (LeaderGPU), 4090 $0.73/h (Vast.ai). RunPod gives a $5–500 referral bonus after a $10 deposit. — [gpuperhour](https://gpuperhour.com/blog/free-cloud-gpus-and-credits) [3P]
- **Big-cloud student and trial credits:** Azure for Students $100 for 12 months, no card. The GitHub Student Pack includes $100 Azure. GCP gives $300 but trials cannot attach GPUs. AWS Free Tier is $200 on select services. None of these can be spent on Modal. — [gpuperhour](https://gpuperhour.com/blog/free-cloud-gpus-and-credits) [3P]; [Modal pricing](https://modal.com/pricing)
- LoRAX on any platform needs Ampere or newer and is archived. — [LoRAX GitHub](https://github.com/predibase/lorax)

### Inferences
**Recommended Modal architecture** (my design, built from the cited pieces)
1. **Volume `slm-lora` (v2):**
   - `/base/` holds the HF snapshot of Qwen2.5-0.5B or 1.5B (about 1–3 GB fp16).
   - `/adapters/<name>/` holds one directory per specialist (`adapter_config.json` plus `adapter_model.safetensors`).
   - `/data/` holds the training sets.
   
   Hundreds of 0.5–1.5B adapters come to about 2–20 GB, all inside the 1 TiB free tier, so storage costs $0. Each training job writes only its own directory, which is safe on v2.
2. **Training:**
   - One `@app.function(gpu="L4", volumes={...}, timeout=3600)` named `train_adapter(spec)`.
   - Driven from the Mac with `list(train_adapter.map(specs))`, or with `.spawn_map(specs)` plus results written to the Volume, so the jobs survive the laptop sleeping.
   - With 10 concurrent GPUs, 300 jobs of about 5 min each finish in about 2.5 h of wall time and use about 25 L4-hours, roughly **$20**.
   - Pack 5–10 adapters per container call, training them in sequence, so the base-model load and image cold start are paid once per container instead of once per adapter.
3. **Serving:**
   - One `@app.cls(gpu="L4" or "A10", volumes={...}, scaledown_window=300–900)` with `@modal.concurrent(max_inputs=64–128)` and `@modal.web_server(8000)`.
   - Runs `vllm serve /vol/base --enable-lora --max-loras 16–32 --max-cpu-loras 512 --max-lora-rank 16`.
   - Uses `VLLM_ALLOW_RUNTIME_LORA_UPDATING=True` plus `lora_filesystem_resolver` with `VLLM_LORA_RESOLVER_CACHE_DIR=/vol/adapters`, so any adapter name on the Volume loads on first use.
   - Keep the `vllm-cache` Volume so recompiles take about 10 s. Use `--enforce-eager` while iterating, then try GPU snapshots.
   - Choose L4 or A10 (24 GB, Ampere or Ada) over T4. Turing-era T4 support for vLLM's LoRA kernels is unverified (see Gaps), and 24 GB holds the base model, KV cache and dozens of GPU-resident adapters for a 1.5B model.
4. **Keep-warm cost** (arithmetic from the official rates):
   - `min_containers=1` around the clock: T4 about $14/day, **L4 about $19/day, A10 about $26/day**. That would use up $30 in under 2 days.
   - Instead, set `min_containers=0` with `scaledown_window` at 10–20 min, and warm the server only during benchmark and demo windows. For example, 2 h/day on an A10 for 10 days is about $22.
   - For the demo itself, set `min_containers=1` for that hour (about $1).
5. **Calling it from the Mac orchestrator:**
   - Use the OpenAI Python client, async, with `base_url="https://<ws>--<app>-serve.modal.run/v1"` (or the `.modal.direct` URL from the example) and `model="<adapter_name>"`.
   - Run each graph level with `asyncio.gather(...)` so sibling specialists land in the same vLLM batch. Wall time then tracks the critical path, plus roughly 50–100 ms of network RTT per graph level (my estimate, to be measured).
   - Send `Modal-Key`/`Modal-Secret` headers through the client's `default_headers` if proxy auth is on.
   - Add retry/backoff for the 503 returned while the container is cold.
   - The local footprint is only the `modal` and `openai` pip packages, which suits the 2.7 GB-free disk.
6. **Total 10-day budget estimate:** about $20 training plus $20–25 serving and benchmarks, roughly $40–45. That is a little over one Starter month ($30). Either spend across a month boundary, add a few dollars from a card, or get academic or hackathon credits. The Kaggle and Colab fallbacks cover dataset prep and extra training at $0.

### Gaps
- **Whether vLLM's LoRA kernels run on T4 (compute capability 7.5) as of vLLM 0.21 was not verified.** Avoid T4 for serving unless the team tests it.
- No Modal-published multi-LoRA example was found, and no measured Modal-specific numbers for adapter load time from a Volume.
- Whether GPU memory snapshots are generally available as of Oct 2026 is unconfirmed (alpha in Dec 2025).
- `modal.Function.from_name` / `modal.Cls.from_name` (for calling deployed functions without HTTP) were not in the fetched docs page, though they are standard SDK usage.
- No measured cold-start time for a 0.5–1.5B vLLM container on an L4 or A10. Extrapolating from the 3B Ministral numbers (about 118 s without a snapshot), expect roughly 30–120 s without snapshots or caches.
- The academic grant's turnaround time is unknown, and with a 10-day window it may not arrive in time.

## Q5. What fits on the Mac (16 GB unified memory, about 2.7 GB free disk)?

### Takeaway
Disk, not RAM, is the binding limit. Keep exactly one 4-bit base model of 0.5B or 1.5B (about 0.3–1 GB) plus a few dozen small adapters on the Mac. Keep the full adapter library, datasets, checkpoints and every 7B or fp16 model on HF Hub and in the cloud. Free disk space before installing anything.

### Cited Findings
- The MLX QLoRA path trains on a quantized base (`convert.py -q`), and `mlx_lm.fuse` can push to HF Hub (`--upload-repo`). That supports a "train or fuse, then push to the Hub" workflow. — [MLX-LM LORA.md](https://github.com/ml-explore/mlx-lm/blob/main/mlx_lm/LORA.md)
- vLLM's `lora_hf_hub_resolver` can fetch adapters from HF repos on demand, so the cloud server needs no local copy. — [vLLM LoRA docs](https://github.com/vllm-project/vllm/blob/main/docs/features/lora.md)
- Ollama recommends non-QLoRA adapters, and importing creates new model blobs on disk. — [Ollama import](https://docs.ollama.com/import)

### Inferences (sizes are standard approximations, not sourced)
- **Local:** MLX 4-bit Qwen2.5-0.5B (about 0.3 GB) or 1.5B (about 0.9 GB). About 20–50 adapters at r=8–16 (4–40 MB each, so roughly 0.2–1 GB). The `mlx-lm` pip install is a few hundred MB. Total about 1.5–2.5 GB, which is already close to the 2.7 GB free.
- **Avoid locally:**
  - Installing both Ollama and MLX: each keeps its own copy of model weights.
  - 7–8B models (about 4.5 GB at 4-bit).
  - fp16 bases.
  - Datasets and training checkpoints.
  - The HF cache by default: point `HF_HOME` at an external drive or clean it often.
- **Cloud (Modal v2 Volume, primary; HF Hub as backup and for sharing):** the full library of hundreds of adapters (about 2–20 GB, depending on rank and modules, inside Modal's 1 TiB/month free Volume storage), the fp16 base model, training data and checkpoints, 7B comparison models, and the vLLM server. Upload from the Mac with `modal volume put`, or better, have Modal functions pull datasets and models straight from HF Hub so nothing large passes through the Mac's disk.
- **RAM:** 16 GB comfortably runs a 1.5B model, or even a 7B 4-bit model, for inference. The 2.7 GB of free disk means macOS swap and Xcode or MLX caches may fail. Free 10–20 GB first (for example with the mac-cleanup skill).

### Gaps
- None of the frameworks document actual on-disk install sizes; the figures above are estimates.
