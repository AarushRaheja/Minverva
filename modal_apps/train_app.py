"""Modal training factory (app `slm-train`, owner claude-2): one LoRA per domain specialist.

    uv run modal run modal_apps/train_app.py::pilot          # train data/domains on a small share
    uv run modal run modal_apps/train_app.py::sweep          # all four domains, from the manifest
    uv run modal run modal_apps/train_app.py::registry       # rebuild /vol/adapters/registry.json

torch/transformers/peft/trl are imported only inside Modal functions.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import modal

from slm import contracts as C
from slm.domains import ADAPTER
from slm.train import logic
from slm.train.jobs import Job, jobs

APP = "slm-train"
GPU = "L4"
L4_USD_PER_HOUR = 0.80
MANIFEST = "/vol/data/manifest.json"
PILOT_SEED = 900  # seeds >= 900 are pilot runs; merge_registry skips them by default

app = modal.App(APP)
vol = modal.Volume.from_name(C.MODAL_VOLUME, create_if_missing=True, version=2)

image = (
    modal.Image.debian_slim(python_version="3.11")
    .pip_install(
        "torch==2.8.0", "transformers==4.57.1", "peft==0.17.1", "trl==0.23.0",
        "accelerate==1.10.1", "datasets==4.1.1", "pydantic>=2.7",
    )
    .env({"HF_HOME": f"{C.VOL}/hf", "TOKENIZERS_PARALLELISM": "false"})
    .add_local_python_source("slm")
)

RECIPE = dict(r=16, alpha=32, lr=2e-4, epochs=2, batch=8, max_len=1536, warmup=0.05)


# --- pure helpers --------------------------------------------------------------


def chat_prompt(tok, domain: str, prompt: str) -> str:
    """The exact serving prompt: chat template, non-thinking, generation prompt appended."""
    msgs = [{"role": "system", "content": C.specialist_system(domain)},
            {"role": "user", "content": prompt}]
    return tok.apply_chat_template(msgs, tokenize=False, add_generation_prompt=True, enable_thinking=False)


def gate_artifact(text: str, domain: str, kind: str, target: str) -> bool:
    """Gate metric: valid JSON, canonical file, and every provided interface symbol present."""
    from slm.bench.score import gate_ok
    from slm.llm.base import _strip_fences

    try:
        artifact = C.Artifact.model_validate_json(_strip_fences(text))
    except Exception:
        return False
    return gate_ok(domain, kind, target, artifact)


# --- GPU work ------------------------------------------------------------------


def _eval_gate(model, tok, job: Job, ev: list[C.TrainExample], bs: int = 16) -> tuple[float, dict]:
    import torch

    if not ev:
        return float("nan"), {}
    ev = logic.stratified_eval(ev)
    flags: list[bool] = []
    tok.padding_side = "left"
    model.eval()
    for i in range(0, len(ev), bs):
        batch = ev[i:i + bs]
        texts = [chat_prompt(tok, ex.domain, ex.prompt) for ex in batch]
        enc = tok(texts, return_tensors="pt", padding=True).to("cuda")
        with torch.no_grad():
            out = model.generate(**enc, max_new_tokens=768, do_sample=False, pad_token_id=tok.pad_token_id)
        for ex, o in zip(batch, out):
            text = tok.decode(o[enc["input_ids"].shape[1]:], skip_special_tokens=True)
            flags.append(gate_artifact(text, ex.domain, ex.kind, ex.target or ""))
    return sum(flags) / len(ev), logic.per_kind_accuracy(ev, flags)


def _build_dataset(tok, job: Job, train: list[C.TrainExample]):
    from datasets import Dataset

    rows = {"input_ids": [], "completion_mask": []}
    for ex in train:
        p_ids = tok(chat_prompt(tok, job.domain, ex.prompt), add_special_tokens=False)["input_ids"]
        c_ids = tok(ex.completion + tok.eos_token, add_special_tokens=False)["input_ids"]
        ids = (p_ids + c_ids)[: RECIPE["max_len"]]
        rows["input_ids"].append(ids)
        rows["completion_mask"].append(([0] * len(p_ids) + [1] * len(c_ids))[: RECIPE["max_len"]])
    return Dataset.from_dict(rows)


def _train_one(base, tok, job: Job, max_train: int | None, base_only: bool,
               manifest: dict | None = None, allow_missing: bool = False, escalated: bool = False,
               epochs: int | None = None):
    import torch
    from peft import LoraConfig
    from trl import SFTConfig, SFTTrainer

    train, ev = logic.load_examples(job, C.PATHS["domain_data"], allow_missing=allow_missing)
    if manifest is not None and not escalated and not max_train and not allow_missing:
        logic.check_counts(job, len(train), manifest)  # fixed-budget guard
    if max_train:
        train = train[:max_train]
    rec: dict = {"adapter": job.adapter_name, "domain": job.domain, "n_train": len(train),
                 "n_eval": len(ev)}
    t0 = time.time()
    if base_only:  # untuned base on the same eval
        rec["gate_task_ok"], rec["per_kind"] = _eval_gate(base, tok, job, ev)
        rec["eval_seconds"] = time.time() - t0
        return rec, base
    ds = _build_dataset(tok, job, train)
    out_dir = C.PATHS["adapter"].format(seed=job.seed, adapter_name=job.adapter_name)
    cfg = SFTConfig(
        output_dir=f"/tmp/sft/{job.adapter_name}", num_train_epochs=epochs or RECIPE["epochs"],
        per_device_train_batch_size=RECIPE["batch"], gradient_accumulation_steps=1,
        learning_rate=RECIPE["lr"], lr_scheduler_type="cosine", warmup_ratio=RECIPE["warmup"],
        bf16=True, max_length=RECIPE["max_len"], completion_only_loss=True,
        logging_steps=10, save_strategy="no", report_to=[], seed=job.seed, dataset_kwargs={},
    )
    peft_cfg = LoraConfig(r=RECIPE["r"], lora_alpha=RECIPE["alpha"], lora_dropout=0.0,
                          target_modules="all-linear", task_type="CAUSAL_LM")
    trainer = SFTTrainer(model=base, args=cfg, train_dataset=ds, processing_class=tok, peft_config=peft_cfg)
    b = next(iter(trainer.get_train_dataloader()))
    rec["masked_frac_first_batch"] = float((b["labels"] == -100).float().mean())  # loss-mask sanity
    trainer.train()
    losses = [h["loss"] for h in trainer.state.log_history if "loss" in h]
    rec["final_loss"] = losses[-1] if losses else None
    train_s = time.time() - t0
    model = trainer.model
    for p in model.parameters():  # LoRA weights saved (and gated) in bf16
        if p.requires_grad:
            p.data = p.data.to(torch.bfloat16)
    rec["gate_task_ok"], rec["per_kind"] = _eval_gate(model, tok, job, ev)
    rec["escalated"] = escalated
    Path(out_dir).mkdir(parents=True, exist_ok=True)
    model.save_pretrained(out_dir)
    rec["train_seconds"] = train_s
    entry = C.RegistryEntry(
        adapter_name=job.adapter_name, domain=job.domain, seed=job.seed, path=out_dir,
        train_examples=len(train), gate_task_ok=rec["gate_task_ok"], train_seconds=train_s, gpu=GPU,
        data_version=(manifest or {}).get("data_version"), escalated=escalated,
    )
    Path(out_dir, "registry_entry.json").write_text(entry.model_dump_json(indent=2))
    Path(out_dir, "train_meta.json").write_text(json.dumps(
        {"data_version": (manifest or {}).get("data_version"), "per_kind": rec["per_kind"],
         "n_eval": len(ev), "escalated": escalated}, indent=2))
    base = model.unload()  # strip LoRA layers, reuse the base for the next job
    del trainer, model
    torch.cuda.empty_cache()
    return rec, base


@app.function(image=image, gpu=GPU, volumes={C.VOL: vol}, timeout=4 * 3600, min_containers=0,
              scaledown_window=30)
def train_domains(domains: list[str] | None = None, seed: int = 0, max_train: int | None = None,
                  base_only: bool = False, run: str = "sweep", allow_missing: bool = False,
                  require_manifest: bool = True) -> dict:
    """Train every requested domain back to back on one container; base model loaded once."""
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer

    vol.reload()
    manifest = json.loads(Path(MANIFEST).read_text()) if Path(MANIFEST).exists() else None
    if require_manifest and manifest is None:
        raise RuntimeError("no data manifest on the Volume; run modal_apps/data_app.py first")
    todo = [j for j in jobs(seed) if domains is None or j.domain in domains]
    t_start = time.time()
    tok = AutoTokenizer.from_pretrained(C.BASE_MODEL)
    base = AutoModelForCausalLM.from_pretrained(C.BASE_MODEL, torch_dtype=torch.bfloat16).to("cuda")
    load_s = time.time() - t_start
    vol.commit()  # persist HF cache
    results = []
    for job in todo:
        rec, base = _train_one(base, tok, job, max_train, base_only, manifest=manifest,
                               allow_missing=allow_missing)
        if not base_only and logic.needs_retry(job, rec["gate_task_ok"], False):
            first = rec["gate_task_ok"]
            rec, base = _train_one(base, tok, job, None, False, manifest=manifest,
                                   escalated=True, epochs=RECIPE["epochs"] + 2)
            rec["first_gate"] = first
        results.append(rec)
        print(json.dumps({k: v for k, v in rec.items() if k != "per_kind"}), flush=True)
        log = Path(C.VOL, "train_logs", run, f"{job.adapter_name}.json")
        log.parent.mkdir(parents=True, exist_ok=True)
        log.write_text(json.dumps(rec, indent=2))
        vol.commit()
    total = time.time() - t_start
    return {"model_load_seconds": load_s, "total_seconds": total,
            "gpu_usd": total / 3600 * L4_USD_PER_HOUR,
            "jobs": [{k: v for k, v in r.items() if k != "per_kind"} for r in results]}


@app.function(image=image, volumes={C.VOL: vol}, timeout=600, min_containers=0, scaledown_window=10)
def merge_registry(include_pilot: bool = False) -> dict:
    """Rebuild registry.json from every registry_entry.json (never written by parallel trainers)."""
    vol.reload()
    entries = []
    for p in sorted(Path(C.VOL, "adapters").glob("*/*/registry_entry.json")):
        e = C.RegistryEntry.model_validate_json(p.read_text())
        if e.seed < PILOT_SEED or include_pilot:
            entries.append(e)
    Path(C.PATHS["registry"]).write_text(json.dumps([e.model_dump() for e in entries], indent=2))
    vol.commit()
    return {"total": len(entries), "domains": logic.registry_summary(entries)}


@app.function(image=image, volumes={C.VOL: vol}, timeout=600, min_containers=0, scaledown_window=10)
def pending(seed: int) -> list[dict]:
    """Idempotent plan: domains whose adapter is not yet done for this seed and data_version."""
    vol.reload()
    manifest = json.loads(Path(MANIFEST).read_text())
    version = manifest.get("data_version")
    out = []
    for j in jobs(seed):
        path = Path(C.PATHS["adapter"].format(seed=seed, adapter_name=j.adapter_name))
        if not logic.is_done(j, path, version):
            out.append(j.model_dump())
    return out


# --- local entrypoints ---------------------------------------------------------


@app.local_entrypoint()
def pilot(n_train: int = 200):
    """One small adapter per domain on the real data, to measure time/$ and the gate."""
    call = train_domains.spawn(None, PILOT_SEED, n_train, False, "pilot", True, False)
    out = call.get()
    print(json.dumps(out, indent=2))
    print("registry:", json.dumps(merge_registry.remote(include_pilot=True), indent=2))


@app.local_entrypoint()
def sweep(seed: int = 0):
    todo = pending.remote(seed)
    if not todo:
        print("nothing pending")
        return
    print(f"{len(todo)} adapters: {[j['adapter_name'] for j in todo]}")
    out = train_domains.remote([j["domain"] for j in todo], seed, None, False, f"sweep-s{seed}")
    print(json.dumps(out, indent=2))
    print("registry:", json.dumps(merge_registry.remote(), indent=2))


@app.local_entrypoint()
def registry(include_pilot: bool = False):
    print(json.dumps(merge_registry.remote(include_pilot=include_pilot), indent=2))


@app.local_entrypoint()
def adapters():
    print(json.dumps({d: ADAPTER[d] for d in ADAPTER}, indent=1))
