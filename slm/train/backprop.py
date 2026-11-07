"""LoRA training without Modal: a plain PyTorch backprop loop for any GPU you can get for free.

Runs on CUDA (Kaggle / Colab free T4, a lab box), Apple MPS, or CPU (slow; smoke tests only).
Trains the four specialists and the manager with the same data, prompts and loss mask as the
Modal apps, and writes adapters in the Volume layout so they can be uploaded unchanged:

    <root>/adapters/<seed>/spec-<domain>/   (PEFT dir + registry_entry.json + train_meta.json)
    <root>/manager/<run>/                   (PEFT dir + tokenizer + train_meta.json)

    python -m slm.train build-data --root out            # CPU, seconds
    python -m slm.train backprop --role all --root out   # GPU

Everything above `# --- torch ---` is pure Python and tested offline. torch / transformers / peft
are imported inside functions only, so `uv run pytest` never needs them.
"""

from __future__ import annotations

import json
import math
import random
import time
from dataclasses import asdict, dataclass
from pathlib import Path

from slm import contracts as C
from slm.manager.train_logic import IGNORE, TooLong, build_labels

ROLES = (*C.DOMAINS, "manager")


@dataclass
class Recipe:
    """Same defaults as modal_apps/train_app.py RECIPE (r16, alpha 2r, lr 2e-4, 2 epochs)."""

    r: int = 16
    alpha: int = 32
    lr: float = 2e-4
    epochs: int = 2
    batch: int = 8  # examples per optimizer step
    micro_batch: int = 2  # examples per forward/backward (gradient accumulation)
    max_len: int = 3072  # longer rows are DROPPED, never truncated
    warmup: float = 0.05
    grad_clip: float = 1.0
    max_train: int | None = None  # cap train rows (pilots / data-efficiency probes)
    gate_limit: int = 64  # eval rows generated for the gate after training (0 = skip)
    gate_max_new_tokens: int = 1024
    seed: int = 0
    target: str = "all"  # which modules get LoRA weights: a key of TARGET_MODULES


# "attn" names the Qwen attention projections. PEFT raises if none match, so a wrong name fails loudly.
TARGET_MODULES = {"all": "all-linear", "attn": ["q_proj", "k_proj", "v_proj", "o_proj"]}


@dataclass
class Row:
    system: str
    prompt: str
    completion: str
    kind: str = ""
    target: str = ""


# --- pure logic ------------------------------------------------------------------


def data_path(root: str | Path, key: str, name: str) -> Path:
    """contracts.PATHS with /vol replaced by `root` (same layout as slm.bench.build)."""
    return Path(str(root) + C.PATHS[key].format(name=name)[len(C.VOL):])


def adapter_dir(root: str | Path, role: str, seed: int, run: str = "m-free") -> Path:
    if role == "manager":
        return Path(str(root) + C.PATHS["manager"].format(run=run)[len(C.VOL):])
    from slm.domains import ADAPTER

    return Path(str(root) + C.PATHS["adapter"].format(seed=seed, adapter_name=ADAPTER[role])[len(C.VOL):])


def base_model(role: str) -> str:
    return C.MANAGER_BASE if role == "manager" else C.BASE_MODEL


def load_rows(root: str | Path, role: str) -> tuple[list[Row], list[Row]]:
    """(train, eval) rows for one role, read from the files slm.bench.build writes."""
    if role == "manager":
        def read(split: str) -> list[Row]:
            p = data_path(root, "manager_data", split)
            if not p.exists():
                raise FileNotFoundError(f"missing manager data: {p} (run `python -m slm.train build-data`)")
            return [Row(**json.loads(x)) for x in p.read_text().splitlines() if x.strip()]

        return read("train"), read("dev")
    if role not in C.DOMAINS:
        raise ValueError(f"role must be one of {ROLES}, got {role!r}")
    p = data_path(root, "domain_data", role)
    if not p.exists():
        raise FileNotFoundError(f"missing domain data: {p} (run `python -m slm.train build-data`)")
    train, ev = [], []
    system = C.specialist_system(role)  # the exact serving prompt
    for line in p.read_text().splitlines():
        if not line.strip():
            continue
        ex = C.TrainExample.model_validate_json(line)
        if ex.domain != role:
            continue
        row = Row(system, ex.prompt, ex.completion, ex.kind, ex.target or "")
        (train if ex.split == "train" else ev).append(row)
    return train, ev


def encode_rows(rows: list[Row], encode_prompt, encode_completion, eos_id: int, max_len: int):
    """Tokenize rows into (input_ids, labels). Loss only on completion + eos; too-long rows dropped.

    encode_prompt(system, prompt) -> ids of the chat-templated prompt with the generation prompt.
    encode_completion(text) -> ids without special tokens.
    Returns (examples, lengths, n_dropped).
    """
    examples, lengths, dropped = [], [], 0
    for r in rows:
        p_ids = list(encode_prompt(r.system, r.prompt))
        c_ids = list(encode_completion(r.completion))
        lengths.append(len(p_ids) + len(c_ids) + 1)
        try:
            examples.append(build_labels(p_ids, c_ids, eos_id, max_len))
        except TooLong:
            dropped += 1
    return examples, lengths, dropped


def lr_at(step: int, total: int, peak: float, warmup_frac: float) -> float:
    """Linear warmup, then cosine decay to 0."""
    warm = max(1, int(warmup_frac * total))
    if step < warm:
        return peak * (step + 1) / warm
    return peak * 0.5 * (1 + math.cos(math.pi * (step - warm) / max(1, total - warm)))


def total_steps(n_examples: int, batch: int, epochs: int) -> int:
    return epochs * math.ceil(n_examples / batch)


def pad_batch(batch: list[tuple[list[int], list[int]]], pad_id: int):
    """Right-pad to the longest row: (ids, labels, attention) as nested lists."""
    width = max(len(x) for x, _ in batch)
    ids = [x + [pad_id] * (width - len(x)) for x, _ in batch]
    labels = [y + [IGNORE] * (width - len(y)) for _, y in batch]
    att = [[1] * len(x) + [0] * (width - len(x)) for x, _ in batch]
    return ids, labels, att


def target_tokens(labels: list[int]) -> int:
    """Tokens that carry loss after the causal shift (the first position predicts nothing)."""
    return sum(1 for t in labels[1:] if t != IGNORE)


def gate_ok_text(text: str, domain: str, kind: str, target: str) -> bool:
    """The trainer's gate for one generated artifact (same rule as modal_apps/train_app.py)."""
    from slm.bench.score import gate_ok
    from slm.llm.base import _strip_fences

    try:
        artifact = C.Artifact.model_validate_json(_strip_fences(text))
    except Exception:  # noqa: BLE001
        return False
    return gate_ok(domain, kind, target, artifact)


# --- torch -----------------------------------------------------------------------


def pick_device(prefer: str | None = None) -> str:
    import torch

    if prefer:
        return prefer
    if torch.cuda.is_available():
        return "cuda"
    if getattr(torch.backends, "mps", None) and torch.backends.mps.is_available():
        return "mps"
    return "cpu"


def train_dtype(device: str):
    """bf16 where the hardware does it natively; fp32 otherwise (T4, MPS, CPU) for stable grads."""
    import torch

    if device == "cuda" and torch.cuda.is_bf16_supported():
        return torch.bfloat16
    return torch.float32


def _prompt_encoder(tok):
    def enc(system: str, prompt: str) -> list[int]:
        msgs = [{"role": "system", "content": system}, {"role": "user", "content": prompt}]
        out = tok.apply_chat_template(msgs, tokenize=True, add_generation_prompt=True, enable_thinking=False)
        return list(out["input_ids"] if hasattr(out, "keys") else out)

    return enc


def train_role(role: str, root: str | Path, recipe: Recipe | None = None, *, device: str | None = None,
               base: str | None = None, run: str = "m-free", log=print, out_root: str | Path | None = None) -> dict:
    """Train one LoRA with an explicit forward / loss.backward() / optimizer.step() loop."""
    import torch
    from peft import LoraConfig, get_peft_model
    from transformers import AutoModelForCausalLM, AutoTokenizer

    recipe = recipe or Recipe()
    device = pick_device(device)
    base = base or base_model(role)
    torch.manual_seed(recipe.seed)
    rng = random.Random(recipe.seed)

    train_rows, eval_rows = load_rows(root, role)
    rng.shuffle(train_rows)
    if recipe.max_train:
        train_rows = train_rows[: recipe.max_train]

    tok = AutoTokenizer.from_pretrained(base)
    eos = tok.convert_tokens_to_ids("<|im_end|>")
    pad = tok.pad_token_id if tok.pad_token_id is not None else eos
    enc_c = lambda text: tok(text, add_special_tokens=False)["input_ids"]  # noqa: E731
    examples, lengths, dropped = encode_rows(train_rows, _prompt_encoder(tok), enc_c, eos, recipe.max_len)
    if not examples:
        raise RuntimeError(f"{role}: no training examples left (dropped {dropped} as too long)")
    log(f"[{role}] {len(examples)} examples on {device} ({base}); dropped {dropped}; "
        f"max len {max(lengths)}")

    t0 = time.time()
    model = AutoModelForCausalLM.from_pretrained(base, torch_dtype=train_dtype(device)).to(device)
    model.config.use_cache = False
    model.gradient_checkpointing_enable()
    model.enable_input_require_grads()
    model = get_peft_model(model, LoraConfig(
        r=recipe.r, lora_alpha=recipe.alpha, lora_dropout=0.0, target_modules=TARGET_MODULES[recipe.target],
        task_type="CAUSAL_LM"))
    params = [p for p in model.parameters() if p.requires_grad]
    for p in params:  # LoRA weights train in fp32 even when the frozen base is bf16
        p.data = p.data.float()
    opt = torch.optim.AdamW(params, lr=recipe.lr, weight_decay=0.0)
    steps = total_steps(len(examples), recipe.batch, recipe.epochs)
    log(f"[{role}] {sum(p.numel() for p in params):,} trainable params, {steps} optimizer steps")

    model.train()
    step, losses = 0, []
    for epoch in range(recipe.epochs):
        rng.shuffle(examples)
        for i in range(0, len(examples), recipe.batch):
            batch = sorted(examples[i:i + recipe.batch], key=lambda e: len(e[0]))
            n_tok = sum(target_tokens(y) for _, y in batch)
            total = 0.0
            for j in range(0, len(batch), recipe.micro_batch):
                mb = batch[j:j + recipe.micro_batch]
                ids, lab, att = (torch.tensor(t, device=device) for t in pad_batch(mb, pad))
                mb_tok = sum(target_tokens(y) for _, y in mb)
                with torch.autocast(device_type="cuda", dtype=torch.bfloat16,
                                    enabled=device == "cuda" and train_dtype(device) == torch.bfloat16):
                    loss = model(input_ids=ids, attention_mask=att, labels=lab).loss  # forward
                (loss * mb_tok / n_tok).backward()  # backprop: token-weighted mean over the batch
                total += loss.item() * mb_tok / n_tok
            torch.nn.utils.clip_grad_norm_(params, recipe.grad_clip)
            for g in opt.param_groups:
                g["lr"] = lr_at(step, steps, recipe.lr, recipe.warmup)
            opt.step()  # gradient descent on the LoRA weights only
            opt.zero_grad(set_to_none=True)
            losses.append(total)
            step += 1
            if step % 10 == 0 or step == steps:
                log(f"[{role}] epoch {epoch + 1} step {step}/{steps} loss {total:.4f} "
                    f"({time.time() - t0:.0f}s)")
    train_s = time.time() - t0

    out = adapter_dir(out_root or root, role, recipe.seed, run)
    out.mkdir(parents=True, exist_ok=True)
    model.save_pretrained(str(out))
    if role == "manager":
        tok.save_pretrained(str(out))

    rec = {"role": role, "base": base, "device": device, "n_train": len(examples), "dropped": dropped,
           "steps": steps, "first_loss": losses[0], "final_loss": losses[-1], "train_seconds": train_s,
           "recipe": asdict(recipe), "path": str(out)}
    if recipe.gate_limit and eval_rows:
        rec.update(_gate(model, tok, role, eval_rows[: recipe.gate_limit], device, recipe))
    _write_meta(out, role, rec, root)
    log(json.dumps({k: v for k, v in rec.items() if k not in ("recipe", "per_kind", "failures", "gate_flags",
                                                              "gate_clusters")}))
    del model, opt
    if device == "cuda":
        torch.cuda.empty_cache()
    return rec


def _gate(model, tok, role: str, rows: list[Row], device: str, recipe: Recipe, bs: int = 8) -> dict:
    """Greedy-generate the eval rows and score them: artifact gate (specialists) or plan score (manager)."""
    import torch

    model.eval()
    model.config.use_cache = True
    tok.padding_side = "left"
    texts = []
    for i in range(0, len(rows), bs):
        chunk = rows[i:i + bs]
        prompts = [tok.apply_chat_template(
            [{"role": "system", "content": r.system}, {"role": "user", "content": r.prompt}],
            tokenize=False, add_generation_prompt=True, enable_thinking=False) for r in chunk]
        enc = tok(prompts, return_tensors="pt", padding=True).to(device)
        with torch.no_grad():
            out = model.generate(**enc, max_new_tokens=recipe.gate_max_new_tokens, do_sample=False,
                                 pad_token_id=tok.pad_token_id)
        texts += [tok.decode(o[enc["input_ids"].shape[1]:], skip_special_tokens=True) for o in out]
    if role == "manager":
        from slm.contracts import ProjectPlan
        from slm.manager.score import score_json, summarize

        scores = [score_json(t, ProjectPlan.model_validate_json(r.completion)) for t, r in zip(texts, rows)]
        return {"gate_task_ok": summarize(scores).get("isomorphic", 0.0), "plan_eval": summarize(scores)}
    flags = [gate_ok_text(t, role, r.kind, r.target) for t, r in zip(texts, rows)]
    per_kind: dict[str, list[int]] = {}
    for r, f in zip(rows, flags):
        per_kind.setdefault(r.kind, []).append(int(f))
    return {"gate_task_ok": sum(flags) / len(flags), "n_gate": len(flags), "gate_flags": flags,
            "gate_clusters": [r.target for r in rows],
            "per_kind": {k: sum(v) / len(v) for k, v in sorted(per_kind.items())},
            "failures": [t[:400] for t, f in zip(texts, flags) if not f][:3]}


def _write_meta(out: Path, role: str, rec: dict, root: str | Path) -> None:
    manifest_p = Path(root) / "data" / "manifest.json"
    version = json.loads(manifest_p.read_text()).get("data_version") if manifest_p.exists() else None
    Path(out, "train_meta.json").write_text(json.dumps({**rec, "data_version": version}, indent=2))
    if role == "manager":
        return
    from slm.domains import ADAPTER

    entry = C.RegistryEntry(
        adapter_name=ADAPTER[role], domain=role, seed=rec["recipe"]["seed"],
        path=C.PATHS["adapter"].format(seed=rec["recipe"]["seed"], adapter_name=ADAPTER[role]),
        train_examples=rec["n_train"], gate_task_ok=float(rec.get("gate_task_ok", float("nan"))),
        train_seconds=rec["train_seconds"], gpu=rec["device"], data_version=version,
    )
    Path(out, "registry_entry.json").write_text(entry.model_dump_json(indent=2))
