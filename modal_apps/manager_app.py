"""Manager SFT + plan eval on Modal (app `slm-manager`).

  uv run modal run modal_apps/manager_app.py::train --run m1 --n-examples 4000 --epochs 2
  uv run modal run modal_apps/manager_app.py::evaluate --run m1 --split dev
  uv run modal run modal_apps/manager_app.py::evaluate --split dev          # M0: untuned base

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

_common = {"HF_HOME": f"{VOL}/hf", "TOKENIZERS_PARALLELISM": "false"}
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
    info = {"run": run, "examples": len(examples), "dropped": len(rows) - len(examples),
            "too_long": too_long, "length_stats": stats, "max_len": max_len, "epochs": epochs,
            "steps": steps, "final_loss": last_loss, "seconds": round(time.time() - t0, 1), "gpu": "L4"}
    print(json.dumps(info))
    return info


@app.function(image=eval_image, gpu="L4", volumes={VOL: vol}, timeout=2 * 3600,
              min_containers=0, scaledown_window=60)
def eval_manager(run: str | None = None, split: str = "dev", limit: int | None = None,
                 export_plans: bool = True, seed: int = 0) -> dict:
    """Greedy plans for a split, scored against the gold plan; plans exported for the pipeline."""
    import os

    from vllm import LLM, SamplingParams
    from vllm.lora.request import LoRARequest
    from vllm.sampling_params import GuidedDecodingParams

    from slm.manager.manager import MANAGER_SYSTEM, user_prompt
    from slm.manager.train_logic import (
        chat_messages, plan_json_schema, retry_prompt, score_outputs, summarize_records,
    )

    vol.reload()
    t0 = time.time()
    projects = _read_projects(split)
    if limit:
        projects = projects[:limit]
    users = [user_prompt(p.description) for p in projects]
    llm = LLM(MANAGER_BASE, enable_lora=run is not None, max_lora_rank=16, max_model_len=4096,
              gpu_memory_utilization=0.85, download_dir=f"{VOL}/hf")
    guided = GuidedDecodingParams(json=plan_json_schema())
    greedy = SamplingParams(temperature=0.0, max_tokens=2048, guided_decoding=guided)
    lora = LoRARequest(run, 1, PATHS["manager"].format(run=run)) if run else None
    kw = {"lora_request": lora, "chat_template_kwargs": {"enable_thinking": False}}

    def gen(user_turns: list[str], params):
        return llm.chat([chat_messages({"system": MANAGER_SYSTEM, "prompt": u}) for u in user_turns],
                        params, **kw)

    outs = gen(users, greedy)
    texts = [o.outputs[0].text for o in outs]
    finish = [o.outputs[0].finish_reason for o in outs]
    summary = summarize_records(score_outputs(projects, texts))
    summary["length_stops"] = sum(f == "length" for f in finish)
    summary["output_tokens"] = sum(len(o.outputs[0].token_ids) for o in outs)

    from slm.manager.train_logic import parse_plan

    bad = [i for i, t in enumerate(texts) if parse_plan(t)[0] is None]
    if bad:  # greedy + one retry for invalid plans (same wording as LLMClient's retry)
        routs = gen([retry_prompt(users[i], texts[i], parse_plan(texts[i])[1]) for i in bad], greedy)
        for i, o in zip(bad, routs):
            texts[i] = o.outputs[0].text
    summary["greedy_retry"] = summarize_records(score_outputs(projects, texts))
    summary["retried"] = len(bad)

    tag = run or "base"
    summary |= {"run": tag, "split": split, "n": len(projects), "seconds": round(time.time() - t0, 1),
                "gpu": "L4"}
    path = PATHS["results"].format(name=f"manager-{tag}-{split}")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    Path(path).write_text(json.dumps(summary, indent=1))
    if export_plans:  # the plans the pipeline will actually receive
        pdir = Path(PATHS["results"].format(name="plans/x")).parent
        pdir.mkdir(parents=True, exist_ok=True)
        with open(pdir / f"{tag}-{split}.jsonl", "w") as f:
            for p, t in zip(projects, texts):
                f.write(json.dumps({"project_id": p.id, "plan": t}) + "\n")
    vol.commit()
    print(json.dumps(summary["overall"]))
    return summary


@app.local_entrypoint()
def train(run: str, n_examples: int = 4000, epochs: int = 2):
    print(train_manager.remote(run, n_examples, epochs))


@app.local_entrypoint()
def evaluate(split: str = "dev", run: str = "", limit: int = 0):
    out = eval_manager.remote(run or None, split, limit or None)
    print(json.dumps(out["overall"], indent=1))
    print(json.dumps(out["greedy_retry"]["overall"], indent=1))
