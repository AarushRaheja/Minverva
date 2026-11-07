"""Run trained adapters in-process with transformers + peft (no vLLM server, no Modal).

For a laptop or a free notebook GPU. Each base model is loaded once and every adapter on it is
attached by name; `for_model(adapter)` returns a sibling that switches adapter per call. Generation
is serialized with a lock (one GPU, one model), so the dispatcher's parallel levels still run, just
not concurrently. Needs torch, transformers and peft (imported lazily).

    adapters = local_adapters("out", seed=0, manager_run="m-free")
    specialists = {d: LocalClient(ADAPTER[d], adapters) for d in DOMAINS}
"""

from __future__ import annotations

import copy
import threading
from contextlib import nullcontext
from pathlib import Path

from slm import contracts as C
from slm.domains import ADAPTER
from slm.llm.base import LLMClient, RawResponse
from slm.trace import Tracer

MANAGER = "manager"
_LOCK = threading.Lock()
_BASES: dict[str, object] = {}  # base model name -> (model, tokenizer, loaded adapter names)


def local_adapters(root: str | Path, seed: int = 0, manager_run: str | None = "m-free") -> dict[str, tuple[str, str]]:
    """adapter name -> (base model, adapter dir) for every trained adapter found under root."""
    out: dict[str, tuple[str, str]] = {}
    for d in C.DOMAINS:
        p = Path(str(root) + C.PATHS["adapter"].format(seed=seed, adapter_name=ADAPTER[d])[len(C.VOL):])
        if (p / "adapter_config.json").exists():
            out[ADAPTER[d]] = (C.BASE_MODEL, str(p))
    if manager_run:
        p = Path(str(root) + C.PATHS["manager"].format(run=manager_run)[len(C.VOL):])
        if (p / "adapter_config.json").exists():
            out[MANAGER] = (C.MANAGER_BASE, str(p))
    return out


def torch_available() -> bool:
    try:
        import peft  # noqa: F401
        import torch  # noqa: F401
        import transformers  # noqa: F401
    except ImportError:
        return False
    return True


class LocalClient(LLMClient):
    def __init__(self, model: str, adapters: dict[str, tuple[str, str]], tracer: Tracer | None = None,
                 *, max_new_tokens: int = 1024, device: str | None = None):
        """model: an adapter name from `adapters`, or a base model name to run without a LoRA."""
        super().__init__(model, tracer)
        self.adapters = adapters
        self.max_new_tokens = max_new_tokens
        self.device = device

    def for_model(self, model: str) -> LocalClient:
        sibling = copy.copy(self)
        sibling.model = model
        return sibling

    def _resolve(self) -> tuple[str, str | None]:
        if self.model in self.adapters:
            base, path = self.adapters[self.model]
            return base, path
        return self.model, None

    def _load(self, base: str):
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer

        from slm.train.backprop import pick_device

        if base not in _BASES:
            device = pick_device(self.device)
            dtype = torch.bfloat16 if device == "cuda" and torch.cuda.is_bf16_supported() else (
                torch.float16 if device in ("cuda", "mps") else torch.float32)
            tok = AutoTokenizer.from_pretrained(base)
            tok.padding_side = "left"
            model = AutoModelForCausalLM.from_pretrained(base, torch_dtype=dtype).to(device).eval()
            _BASES[base] = [model, tok, set(), device]
        return _BASES[base]

    def _raw(self, system: str, user: str, json_schema: dict) -> RawResponse:
        import torch
        from peft import PeftModel

        base, path = self._resolve()
        with _LOCK:
            entry = self._load(base)
            model, tok, loaded, device = entry
            if path is not None and self.model not in loaded:
                if not loaded:
                    model = PeftModel.from_pretrained(model, path, adapter_name=self.model)
                else:
                    model.load_adapter(path, adapter_name=self.model)
                loaded.add(self.model)
                entry[0] = model
            text = tok.apply_chat_template(
                [{"role": "system", "content": system}, {"role": "user", "content": user}],
                tokenize=False, add_generation_prompt=True, enable_thinking=False)
            enc = tok(text, return_tensors="pt").to(device)
            if loaded:
                if path is None:
                    ctx = model.disable_adapter()
                else:
                    model.set_adapter(self.model)
                    ctx = nullcontext()
            else:
                ctx = nullcontext()
            with torch.no_grad(), ctx:
                out = model.generate(**enc, max_new_tokens=self.max_new_tokens, do_sample=False,
                                     pad_token_id=tok.pad_token_id)
            n_in = enc["input_ids"].shape[1]
            reply = tok.decode(out[0][n_in:], skip_special_tokens=True)
            return RawResponse(reply, int(n_in), int(out.shape[1] - n_in))

