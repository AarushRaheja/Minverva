"""Manager SFT + plan eval on Modal (app `slm-manager`).

  uv run modal run modal_apps/manager_app.py::train --run m1 --n-examples 4000 --epochs 2
  uv run modal run modal_apps/manager_app.py::evaluate --run m1 --split dev
  uv run modal run modal_apps/manager_app.py::evaluate --split dev          # M0: untuned base

Nested spec (AR9): its rows reach 5,432 tokens, so it needs longer limits than the flat plan.
  uv run modal run modal_apps/manager_app.py::train --run m-spec --data spec-train --max-len 6144 --micro-batch 1
  uv run modal run modal_apps/manager_app.py::evaluate --run m-spec --split dev --nested

GPU-only imports happen inside the functions.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import modal

from slm.contracts import MANAGER_BASE, MODAL_VOLUME, PATHS, VOL

app = modal.App("slm-manager")
vol = modal.Volume.from_name(MODAL_VOLUME, version=2, create_if_missing=True)

_common = {"HF_HOME": f"{VOL}/hf", "TOKENIZERS_PARALLELISM": "false",
           "PYTORCH_CUDA_ALLOC_CONF": "expandable_segments:True"}
train_image = (
    modal.Image.debian_slim(python_version="3.11")
    .pip_install("torch==2.7.1", "transformers==4.56.1", "peft==0.17.1", "accelerate==1.10.1",
                 "pydantic>=2.7")
    .env(_common)
    .add_local_python_source("slm")
)
eval_image = (
    modal.Image.debian_slim(python_version="3.11")
    .pip_install("vllm==0.10.1.1", "transformers==4.56.1", "pydantic>=2.7")  # tf>=5 breaks vllm tokenizer
    .env(_common)
    .add_local_python_source("slm")
)


def _read_jsonl(name: str) -> list[dict]:
    path = PATHS["manager_data"].format(name=name)
    return [json.loads(line) for line in Path(path).read_text().splitlines() if line.strip()]


def _read_projects(split: str):
    from slm.contracts import Project

    path = PATHS["projects"].format(name=split)
    return [Project.model_validate_json(line) for line in Path(path).read_text().splitlines() if line.strip()]


@app.function(image=train_image, gpu="L4", volumes={VOL: vol}, timeout=10 * 3600,
              min_containers=0, scaledown_window=60)
def train_manager(run: str, n_examples: int = 4000, epochs: int = 2, data: str = "train",
                  max_len: int = 3072, batch_size: int = 8, micro_batch: int = 2, lr: float = 2e-4,
                  seed: int = 0) -> dict:
    import math
    import random

    import torch
    from peft import LoraConfig, get_peft_model
    from transformers import AutoModelForCausalLM, AutoTokenizer

    from slm.manager.train_logic import IGNORE, TooLong, build_labels, chat_messages, length_stats

    vol.reload()
    t0 = time.time()
    rows = _read_jsonl(data)
    rng = random.Random(seed)
    rng.shuffle(rows)
    rows = rows[:n_examples]
    tok = AutoTokenizer.from_pretrained(MANAGER_BASE)
    eos = tok.convert_tokens_to_ids("<|im_end|>")

    examples, lengths, too_long = [], [], 0
    for r in rows:
        prompt_ids = tok.apply_chat_template(chat_messages(r), add_generation_prompt=True,
                                             enable_thinking=False, tokenize=True)
        completion_ids = tok(r["completion"], add_special_tokens=False)["input_ids"]
        lengths.append(len(prompt_ids) + len(completion_ids) + 1)
        try:  # never truncate: a clipped completion teaches the model not to finish
            examples.append(build_labels(prompt_ids, completion_ids, eos, max_len))
        except TooLong:
            too_long += 1
    stats = length_stats(lengths)
    print(f"token lengths {stats}; dropped as too long: {too_long}; kept {len(examples)}", flush=True)
    assert all(sum(1 for y in lab if y != IGNORE) > 0 and lab[-1] == eos for _, lab in examples)

    model = AutoModelForCausalLM.from_pretrained(MANAGER_BASE, torch_dtype=torch.bfloat16).cuda()
    model.gradient_checkpointing_enable()
    model.enable_input_require_grads()
    model = get_peft_model(model, LoraConfig(
        r=16, lora_alpha=32, target_modules="all-linear", lora_dropout=0.0, task_type="CAUSAL_LM"))
    params = [p for p in model.parameters() if p.requires_grad]
    opt = torch.optim.AdamW(params, lr=lr, weight_decay=0.0)
    steps = epochs * math.ceil(len(examples) / batch_size)
    warm = max(1, int(0.05 * steps))

    def lr_at(s: int) -> float:
        if s < warm:
            return lr * (s + 1) / warm
        return lr * 0.5 * (1 + math.cos(math.pi * (s - warm) / max(1, steps - warm)))

    model.train()
    # Fail in the first minute, not hours in: the longest row sets peak memory.
    x, y = max(examples, key=lambda e: len(e[0]))
    model(input_ids=torch.tensor([x]).cuda(), labels=torch.tensor([y]).cuda()).loss.backward()
    opt.zero_grad(set_to_none=True)
    print(f"longest row ({len(x)} tokens) fits; peak GPU memory "
          f"{torch.cuda.max_memory_allocated() / 2**30:.1f} GiB", flush=True)
    t_train = time.time()
    step, last_loss = 0, float("nan")
    for _ in range(epochs):
        rng.shuffle(examples)
        for i in range(0, len(examples), batch_size):
            batch = sorted(examples[i:i + batch_size], key=lambda e: len(e[0]))
            n_tok = sum(sum(1 for t in y[1:] if t != IGNORE) for _, y in batch)
            total = 0.0
            for j in range(0, len(batch), micro_batch):  # grad accumulation keeps logits memory small
                mb = batch[j:j + micro_batch]
                width = max(len(x) for x, _ in mb)
                ids = torch.tensor([x + [tok.pad_token_id] * (width - len(x)) for x, _ in mb]).cuda()
                lab = torch.tensor([y + [IGNORE] * (width - len(y)) for _, y in mb]).cuda()
                att = torch.tensor([[1] * len(x) + [0] * (width - len(x)) for x, _ in mb]).cuda()
                mb_tok = sum(sum(1 for t in y[1:] if t != IGNORE) for _, y in mb)
                mb_loss = model(input_ids=ids, attention_mask=att, labels=lab).loss
                (mb_loss * mb_tok / n_tok).backward()  # token-weighted mean over the whole batch
                total += mb_loss.item() * mb_tok / n_tok
            loss = torch.tensor(total)
            torch.nn.utils.clip_grad_norm_(params, 1.0)
            for g in opt.param_groups:
                g["lr"] = lr_at(step)
            opt.step()
            opt.zero_grad(set_to_none=True)
            last_loss = loss.item()
            step += 1
            if step % 20 == 0:
                print(f"step {step}/{steps} loss {last_loss:.4f}", flush=True)

    out = PATHS["manager"].format(run=run)
    model.save_pretrained(out)
    tok.save_pretrained(out)
    vol.commit()
    train_tokens = sum(len(x) for x, _ in examples) * epochs
    train_seconds = time.time() - t_train
    info = {"run": run, "data": data, "train_tokens": train_tokens,
            "train_seconds": round(train_seconds, 1),
            "tokens_per_second": round(train_tokens / train_seconds, 1),
            "usd_estimate": round((time.time() - t0) / 3600 * 0.80, 3),
            "examples": len(examples), "dropped": len(rows) - len(examples),
            "too_long": too_long, "length_stats": stats, "max_len": max_len, "epochs": epochs,
            "steps": steps, "final_loss": last_loss, "seconds": round(time.time() - t0, 1), "gpu": "L4"}
    print(json.dumps(info))
    return info


USD_PER_HOUR = {"L4": 0.80, "H100": 3.95}


def _write_raw(tag: str, rows: list[dict]) -> None:
    """Every full model output, so generated tests survive for later scoring."""
    pdir = Path(PATHS["results"].format(name="plans/x")).parent
    pdir.mkdir(parents=True, exist_ok=True)
    with open(pdir / f"{tag}-raw.jsonl", "w") as f:
        for row in rows:
            f.write(json.dumps(row) + "\n")


def _eval(run: str | None, split: str, limit: int | None, export_plans: bool, seed: int, nested: bool,
          gpu: str, heldout_briefs: list[dict] | None) -> dict:
    """Greedy plans for a split, scored against the gold plan; plans exported for the pipeline.

    heldout_briefs are extra [{"id", "brief"}] with no gold plan: they are generated, saved and
    counted, never scored against a plan, and never used for training.
    """
    import os

    from vllm import LLM, SamplingParams
    from vllm.lora.request import LoRARequest
    from vllm.sampling_params import GuidedDecodingParams

    from slm.manager.manager import MANAGER_SYSTEM, user_prompt
    from slm.manager.spec import SPEC_SYSTEM
    from slm.manager.train_logic import (
        chat_messages, parse_plan, parse_spec_plan, plan_json_schema, retry_prompt, score_outputs,
        score_spec_outputs, spec_json_schema, summarize_records, summarize_spec_records,
    )

    system = SPEC_SYSTEM if nested else MANAGER_SYSTEM
    parse = parse_spec_plan if nested else parse_plan

    def scored(outputs: list[str]) -> dict:
        if nested:
            return summarize_spec_records(score_spec_outputs(projects, outputs))
        return summarize_records(score_outputs(projects, outputs))

    vol.reload()
    t0 = time.time()
    projects = _read_projects(split)
    if limit:
        projects = projects[:limit]
    users = [user_prompt(p.description) for p in projects]
    llm = LLM(MANAGER_BASE, enable_lora=run is not None, max_lora_rank=16,
              max_model_len=8192 if nested else 4096,
              gpu_memory_utilization=0.85, download_dir=f"{VOL}/hf")
    guided = GuidedDecodingParams(json=spec_json_schema() if nested else plan_json_schema())
    greedy = SamplingParams(temperature=0.0, max_tokens=6000 if nested else 2048, guided_decoding=guided)
    lora = LoRARequest(run, 1, PATHS["manager"].format(run=run)) if run else None
    kw = {"lora_request": lora, "chat_template_kwargs": {"enable_thinking": False}}

    def gen(user_turns: list[str], params):
        return llm.chat([chat_messages({"system": system, "prompt": u}) for u in user_turns],
                        params, **kw)

    t_gen = time.time()
    outs = gen(users, greedy)
    gen_seconds = time.time() - t_gen
    texts = [o.outputs[0].text for o in outs]
    finish = [o.outputs[0].finish_reason for o in outs]
    summary = scored(texts)
    summary["generation_seconds"] = round(gen_seconds, 1)
    first_texts, first_tokens = list(texts), [len(o.outputs[0].token_ids) for o in outs]
    summary["length_stops"] = sum(f == "length" for f in finish)
    summary["output_tokens"] = sum(len(o.outputs[0].token_ids) for o in outs)

    bad = [i for i, t in enumerate(texts) if parse(t)[0] is None]
    if bad:  # greedy + one retry for invalid plans (same wording as LLMClient's retry)
        routs = gen([retry_prompt(users[i], texts[i], parse(texts[i])[1]) for i in bad], greedy)
        for i, o in zip(bad, routs):
            texts[i] = o.outputs[0].text
    summary["greedy_retry"] = scored(texts)
    summary["retried"] = len(bad)

    tag = (run or "base") + ("-nested" if nested else "")
    summary |= {"run": tag, "split": split, "n": len(projects), "seconds": round(time.time() - t0, 1),
                "usd_estimate": round((time.time() - t0) / 3600 * USD_PER_HOUR[gpu], 3), "gpu": gpu}
    _write_raw(f"{tag}-{split}", [
        {"project_id": p.id, "brief": p.description, "first_output": a, "first_finish_reason": fr,
         "first_output_tokens": n, "output": b, "retried": i in bad}
        for i, (p, a, fr, n, b) in enumerate(zip(projects, first_texts, finish, first_tokens, texts))
    ])
    if heldout_briefs:
        t_heldout = time.time()
        held = gen([user_prompt(b["brief"]) for b in heldout_briefs], greedy)
        held_rows = [{"id": b["id"], "brief": b["brief"], "output": o.outputs[0].text,
                      "finish_reason": o.outputs[0].finish_reason, "output_tokens": len(o.outputs[0].token_ids),
                      "compile_error": parse(o.outputs[0].text)[1]}
                     for b, o in zip(heldout_briefs, held)]
        _write_raw(f"{tag}-webgen-test", held_rows)
        summary["heldout"] = {"n": len(held_rows), "compiled": sum(r["compile_error"] is None for r in held_rows),
                              "length_stops": sum(r["finish_reason"] == "length" for r in held_rows),
                              "seconds": round(time.time() - t_heldout, 1)}
        summary["seconds"] = round(time.time() - t0, 1)
        summary["usd_estimate"] = round((time.time() - t0) / 3600 * USD_PER_HOUR[gpu], 3)
    path = PATHS["results"].format(name=f"manager-{tag}-{split}")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    Path(path).write_text(json.dumps(summary, indent=1))
    if export_plans:  # the plans the pipeline will actually receive
        pdir = Path(PATHS["results"].format(name="plans/x")).parent
        pdir.mkdir(parents=True, exist_ok=True)
        with open(pdir / f"{tag}-{split}.jsonl", "w") as f:
            for p, t in zip(projects, texts):
                compiled = parse(t)[0] if nested else None  # the pipeline runs flat plans only
                f.write(json.dumps({"project_id": p.id, "plan": compiled.model_dump_json() if compiled else t}) + "\n")
    vol.commit()
    print(json.dumps(summary["overall"]))
    return summary


_eval_kw = {"image": eval_image, "volumes": {VOL: vol}, "min_containers": 0, "scaledown_window": 60}


@app.function(gpu="L4", timeout=2 * 3600, **_eval_kw)
def eval_manager(run: str | None = None, split: str = "dev", limit: int | None = None,
                 export_plans: bool = True, seed: int = 0, nested: bool = False,
                 heldout_briefs: list[dict] | None = None) -> dict:
    return _eval(run, split, limit, export_plans, seed, nested, "L4", heldout_briefs)


@app.function(gpu="H100", timeout=1800, **_eval_kw)  # the timeout caps one run at about $2 of GPU
def eval_manager_h100(run: str | None = None, split: str = "dev", limit: int | None = None,
                      export_plans: bool = True, seed: int = 0, nested: bool = False,
                      heldout_briefs: list[dict] | None = None) -> dict:
    return _eval(run, split, limit, export_plans, seed, nested, "H100", heldout_briefs)


@app.function(gpu="H100", timeout=1800, **_eval_kw)
def plan_briefs(run: str, briefs: list[str]) -> dict:
    """Nested plans for free-form briefs with no gold answer. Saves nothing over the scored dev runs."""
    from vllm import LLM, SamplingParams
    from vllm.lora.request import LoRARequest
    from vllm.sampling_params import GuidedDecodingParams

    from slm.manager.manager import user_prompt
    from slm.manager.spec import SPEC_SYSTEM
    from slm.manager.train_logic import chat_messages, parse_spec_plan, spec_json_schema

    vol.reload()
    t0 = time.time()
    llm = LLM(MANAGER_BASE, enable_lora=True, max_lora_rank=16, max_model_len=8192,
              gpu_memory_utilization=0.85, download_dir=f"{VOL}/hf")
    params = SamplingParams(temperature=0.0, max_tokens=6000, guided_decoding=GuidedDecodingParams(json=spec_json_schema()))
    t1 = time.time()
    outs = llm.chat([chat_messages({"system": SPEC_SYSTEM, "prompt": user_prompt(b)}) for b in briefs], params,
                    lora_request=LoRARequest(run, 1, PATHS["manager"].format(run=run)),
                    chat_template_kwargs={"enable_thinking": False})
    rows = [{"project_id": f"seed-{i:02d}", "brief": b, "output": o.outputs[0].text,
             "finish_reason": o.outputs[0].finish_reason, "output_tokens": len(o.outputs[0].token_ids),
             "compile_error": parse_spec_plan(o.outputs[0].text)[1]}
            for i, (b, o) in enumerate(zip(briefs, outs), 1)]
    return {"generation_seconds": round(time.time() - t1, 1), "seconds": round(time.time() - t0, 1),
            "usd_estimate": round((time.time() - t0) / 3600 * USD_PER_HOUR["H100"], 3), "rows": rows}


@app.local_entrypoint()
def briefs(file: str, out: str, run: str = "m-spec"):
    result = plan_briefs.remote(run, json.loads(Path(file).read_text()))
    Path(out).write_text("".join(json.dumps(r) + "\n" for r in result["rows"]))
    print({k: v for k, v in result.items() if k != "rows"}, "compiled",
          sum(r["compile_error"] is None for r in result["rows"]), "of", len(result["rows"]))


@app.local_entrypoint()
def train(run: str, n_examples: int = 4000, epochs: int = 2, data: str = "train", max_len: int = 3072,
          micro_batch: int = 2):
    print(train_manager.remote(run, n_examples, epochs, data=data, max_len=max_len, micro_batch=micro_batch))


@app.local_entrypoint()
def evaluate(split: str = "dev", run: str = "", limit: int = 0, nested: bool = False, gpu: str = "L4",
             heldout_file: str = ""):
    heldout = json.loads(Path(heldout_file).read_text()) if heldout_file else None
    fn = {"L4": eval_manager, "H100": eval_manager_h100}[gpu]
    out = fn.remote(run or None, split, limit or None, nested=nested, heldout_briefs=heldout)
    print(json.dumps(out.get("heldout", {}), indent=1))
    print(json.dumps(out["overall"], indent=1))
    print(json.dumps(out["greedy_retry"]["overall"], indent=1))
    print(json.dumps({k: out[k] for k in ("generation_seconds", "output_tokens", "length_stops", "retried",
                                          "seconds", "usd_estimate")}, indent=1))
