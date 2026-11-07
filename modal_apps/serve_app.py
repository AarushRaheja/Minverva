"""vLLM multi-LoRA server on Modal (app `slm-serve`): one deployment serves all four specialists.

  uv run modal deploy modal_apps/serve_app.py            # server only; URL printed
  uv run modal run modal_apps/serve_app.py::main         # dummy adapters + smoke test
  uv run modal run modal_apps/serve_app.py::panel        # score the specialists on gold plans
  uv run modal run modal_apps/serve_app.py::panel --single-adapter spec-general   # the single arm
  uv run modal run modal_apps/serve_app.py::window       # latency window: levels vs tasks (AR2)
  uv run modal app stop slm-serve                        # when done

Any adapter directory under /vol/adapters/<SLM_ADAPTER_SEED>/<name> is loaded on first request
by vLLM's filesystem LoRA resolver. Set SLM_ADAPTER_SEED at deploy time (default "0").
Adapters written to the Volume after the server container started need `vol.reload()` /
a fresh container to be visible.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import modal

from slm.contracts import BASE_MODEL, DOMAINS, MODAL_VOLUME, VOL
from slm.domains import ADAPTER

SEED = os.environ.get("SLM_ADAPTER_SEED", "0")  # which /vol/adapters/<seed> the resolver serves
VLLM_VERSION = "0.10.2"
PORT = 8000
ADAPTERS = [ADAPTER[d] for d in DOMAINS]

app = modal.App("slm-serve")
vol = modal.Volume.from_name(MODAL_VOLUME, create_if_missing=True, version=2)
ENV = {"HF_HOME": f"{VOL}/hf", "SLM_ADAPTER_SEED": SEED, "HF_HUB_ENABLE_HF_TRANSFER": "1"}

serve_image = (
    modal.Image.debian_slim(python_version="3.12")
    .uv_pip_install(f"vllm=={VLLM_VERSION}", "transformers==4.56.2", "huggingface_hub[hf_transfer]")
    .env({
        **ENV,
        "VLLM_ALLOW_RUNTIME_LORA_UPDATING": "True",
        "VLLM_PLUGINS": "lora_filesystem_resolver",
        "VLLM_LORA_RESOLVER_CACHE_DIR": f"{VOL}/adapters/{SEED}",
        # torch.compile cache on the Volume: skips ~75 s of the cold start after the first boot
        "VLLM_CACHE_ROOT": f"{VOL}/vllm_cache",
        "SLM_VLLM_EXTRA": os.environ.get("SLM_VLLM_EXTRA", ""),  # experiments, e.g. "--enforce-eager"
    })
    .add_local_python_source("slm")
)
peft_image = (
    modal.Image.debian_slim(python_version="3.12")
    .uv_pip_install("torch", "transformers==4.56.2", "peft", "pydantic", "huggingface_hub[hf_transfer]")
    .env(ENV)
    .add_local_python_source("slm")
)
client_image = (
    modal.Image.debian_slim(python_version="3.12")
    .uv_pip_install("httpx", "pydantic").add_local_python_source("slm")
)


@app.function(
    image=serve_image, gpu="L4", volumes={VOL: vol}, min_containers=0,
    scaledown_window=10 * 60, timeout=60 * 60,
)
@modal.concurrent(max_inputs=128)
@modal.web_server(port=PORT, startup_timeout=15 * 60)
def serve():
    cmd = [
        "vllm", "serve", BASE_MODEL, "--served-model-name", BASE_MODEL,
        "--host", "0.0.0.0", "--port", str(PORT),
        "--enable-lora", "--max-loras", "8", "--max-cpu-loras", "32", "--max-lora-rank", "16",
        "--max-model-len", "4096", "--gpu-memory-utilization", "0.90",
        "--uvicorn-log-level", "warning",
    ]
    cmd += os.environ.get("SLM_VLLM_EXTRA", "").split()
    print("launching:", " ".join(cmd), flush=True)
    subprocess.Popen(cmd)


@app.function(image=peft_image, volumes={VOL: vol}, cpu=4, memory=8192, timeout=20 * 60)
def make_dummy_adapters(names: list[str] = ADAPTERS, rank: int = 16) -> str:
    """Random-init (untrained) PEFT LoRA r=16 on BASE_MODEL, copied under each specialist name
    that has no trained adapter yet (trained ones are kept and served as they are)."""
    import shutil

    from peft import LoraConfig, get_peft_model
    from transformers import AutoModelForCausalLM

    from slm.serve.adapters import dummy_targets

    root = Path(VOL) / "adapters" / SEED
    root.mkdir(parents=True, exist_ok=True)
    names, kept = dummy_targets(root, names)
    if not names:
        return f"all {len(kept)} adapters under {root} are trained; no dummies written"
    model = AutoModelForCausalLM.from_pretrained(BASE_MODEL, torch_dtype="bfloat16")
    cfg = LoraConfig(
        r=rank, lora_alpha=2 * rank, lora_dropout=0.0, task_type="CAUSAL_LM",
        target_modules=["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"],
    )
    peft_model = get_peft_model(model, cfg)
    first = root / names[0]
    peft_model.save_pretrained(first)
    for n in names[1:]:
        shutil.copytree(first, root / n, dirs_exist_ok=True)
    vol.commit()
    return f"wrote {len(names)} dummy adapters to {root}; kept trained: {kept or 'none'}"


@app.function(image=client_image, cpu=2, timeout=30 * 60)
def smoke(url: str) -> dict:
    from slm.serve.smoke import run_smoke

    return run_smoke(url)


@app.local_entrypoint()
def main(skip_adapters: bool = False):
    import json

    if not skip_adapters:
        print(make_dummy_adapters.remote())
    url = serve.get_web_url()
    print("server:", url)
    print(json.dumps(smoke.remote(url), indent=2))


@app.function(image=client_image, volumes={VOL: vol}, cpu=2, memory=4096, timeout=3 * 60 * 60)
def evaluate(url: str, split: str = "dev", gold_plan: bool = True, parallel: bool = True,
             limit: int = 0, single_adapter: str = "") -> dict:
    """Run whole projects through the pipeline from inside Modal (same region as the server).

    Arm: "specialists" (each task goes to its domain's spec-* adapter), or "single" when
    `single_adapter` names one adapter that serves every task.
    gold_plan=True isolates the specialists (the manager is graded in modal_apps/manager_app.py).
    gold_plan=False plans with the server's untuned base model, a stand-in for the trained manager.
    """
    import time

    from slm.bench.build import load_projects
    from slm.bench.score import score_runs
    from slm.contracts import BASE_MODEL
    from slm.llm.vllm import VLLMLoRAClient
    from slm.pipeline.dispatch import solve
    from slm.trace import Tracer

    vol.reload()
    projects = load_projects(split)[: limit or None]
    mode = "single" if single_adapter else "specialists"
    plan_src = "goldplan" if gold_plan else "baseplan"
    # one trace file per invocation: score_runs groups by run_id, so a reused id merges runs
    tracer = Tracer(run_id=f"serve-{split}-{mode}-{plan_src}-{time.strftime('%Y%m%d-%H%M%S')}",
                    trace_dir=Path(VOL, "traces"))

    def client(model: str, **kw) -> VLLMLoRAClient:
        return VLLMLoRAClient(model, tracer=tracer, base_url=url, cold_start_timeout_s=900, **kw)

    shared = client(single_adapter or BASE_MODEL)  # "specialists": the dispatcher re-addresses per domain
    clients = {d: shared for d in DOMAINS}
    # a whole ProjectPlan needs more room than one artifact; same budget as manager_app.eval_manager
    manager = None if gold_plan else client(BASE_MODEL, max_tokens=2048)
    for p in projects:
        solve(p, manager_client=manager, specialist_clients=clients, tracer=tracer,
              gold_plan=gold_plan, mode=mode, parallel=parallel)
    metrics, _ = score_runs(tracer.events(), {p.id: p for p in projects})
    vol.commit()
    return (metrics[0].model_dump() | {"trace": str(tracer.path)}) if metrics else {}


@app.function(image=client_image, volumes={VOL: vol}, cpu=2, memory=4096, timeout=60 * 60)
def latency_window(url: str, concurrency: list[int] | None = None, repeats: int = 3,
                   template: int = 0) -> dict:
    """Task 3 / AR2: one gold plan in three shapes x parallel/serial x concurrency (slm/serve/latency.py)."""
    import asyncio
    import time

    from slm.bench.catalog import TRAIN_TEMPLATES, build_plan
    from slm.llm.vllm import VLLMLoRAClient
    from slm.serve.latency import report, run_window
    from slm.trace import Tracer

    plan = build_plan(TRAIN_TEMPLATES[template])
    tracer = Tracer(run_id=f"window-{time.strftime('%Y%m%d-%H%M%S')}", trace_dir=Path(VOL, "traces"))
    shared = VLLMLoRAClient(BASE_MODEL, tracer=tracer, base_url=url, cold_start_timeout_s=900)
    asyncio.run(run_window(plan, {d: shared for d in DOMAINS}, tracer,
                           concurrency=tuple(concurrency or (1, 4)), repeats=repeats))
    vol.commit()
    return report(tracer.events(), plan).model_dump() | {"trace": str(tracer.path)}


@app.local_entrypoint()
def window(concurrency: str = "1,4", repeats: int = 3, template: int = 0):
    import json

    from slm.bench.catalog import TRAIN_TEMPLATES, build_plan
    from slm.serve.latency import estimate

    levels = [int(c) for c in concurrency.split(",")]
    plan = build_plan(TRAIN_TEMPLATES[template])
    print("projected:", estimate(plan, concurrency=tuple(levels), repeats=repeats), flush=True)
    print(json.dumps(latency_window.remote(serve.get_web_url(), levels, repeats, template), indent=2))


@app.local_entrypoint()
def panel(split: str = "dev", gold_plan: bool = True, limit: int = 0, single_adapter: str = ""):
    import json

    out = evaluate.remote(serve.get_web_url(), split, gold_plan, True, limit, single_adapter)
    print(json.dumps(out, indent=2))
