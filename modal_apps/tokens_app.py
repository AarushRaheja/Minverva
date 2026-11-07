"""App `slm-tokens`: exact manager token counts for flat and nested rows. CPU only, so no GPU quota.

    uv run modal run modal_apps/tokens_app.py
"""

from __future__ import annotations

import json

import modal

from slm.contracts import MANAGER_BASE, MODAL_VOLUME, VOL

app = modal.App("slm-tokens")
vol = modal.Volume.from_name(MODAL_VOLUME, version=2)

SEED = 20261101
token_image = (
    modal.Image.debian_slim(python_version="3.11")
    .pip_install("transformers==4.56.1", "jinja2", "pydantic>=2.7")
    .env({"HF_HOME": f"{VOL}/hf", "TOKENIZERS_PARALLELISM": "false"})
    .add_local_python_source("slm")
)


@app.function(image=token_image, volumes={VOL: vol}, timeout=900, min_containers=0, scaledown_window=60)
def count_tokens() -> dict:
    """Exact prompt + completion token counts for flat and nested rows, with the manager's tokenizer."""
    from transformers import AutoTokenizer

    from slm.bench.variety import generate_varied
    from slm.manager.manager import MANAGER_SYSTEM, format_example
    from slm.manager.spec import SPEC_SYSTEM, format_spec_example

    tok = AutoTokenizer.from_pretrained(MANAGER_BASE)
    vol.commit()

    def size(system: str, user: str, completion: str) -> tuple[int, int]:
        prompt = tok.apply_chat_template(
            [{"role": "system", "content": system}, {"role": "user", "content": user}],
            add_generation_prompt=True, enable_thinking=False, tokenize=True)
        return len(prompt), len(tok(completion, add_special_tokens=False)["input_ids"])

    flat, nested = [], []
    for p in generate_varied(1000, "train", SEED):
        _, user, completion = format_example(p)
        flat.append(size(MANAGER_SYSTEM, user, completion))
        user, completion = format_spec_example(p.description, p.plan)
        nested.append(size(SPEC_SYSTEM, user, completion))

    def stats(pairs: list[tuple[int, int]]) -> dict:
        out = sorted(c for _, c in pairs)
        total = sorted(a + b for a, b in pairs)
        return {"completion_p50": out[len(out) // 2], "completion_max": out[-1],
                "total_p50": total[len(total) // 2], "total_max": total[-1]}

    return {"flat": stats(flat), "nested": stats(nested)}


@app.local_entrypoint()
def main():
    print(json.dumps(count_tokens.remote(), indent=1))
