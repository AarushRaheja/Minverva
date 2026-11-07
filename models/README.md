# Trained models

LoRA adapters only. The base models download from Hugging Face.

| Folder | Role | Base model | Training |
|---|---|---|---|
| `manager-m-spec` | Brief to nested `ProjectSpec` | `Qwen/Qwen3-1.7B` | 1,000 examples, 2 epochs |
| `spec-database` | Postgres schemas | `Qwen/Qwen3-0.6B` | 200 examples, 2 epochs |
| `spec-auth` | Sessions and route guard | `Qwen/Qwen3-0.6B` | 200 examples, 2 epochs |
| `spec-network` | FastAPI routers and TypeScript clients | `Qwen/Qwen3-0.6B` | 200 examples, 2 epochs |
| `spec-frontend` | React pages and forms | `Qwen/Qwen3-0.6B` | 200 examples, 2 epochs |

Settings: LoRA rank 16, alpha 32, learning rate 2e-4. Turn thinking off. A model only behaves as measured with
the prompts it trained on:

- **Manager:** `SPEC_SYSTEM` and `user_prompt` in `slm/manager`, constrained to the `ProjectSpec` JSON schema,
  with up to 6,000 output tokens. Pass the output through `normalize_spec`.
- **Specialists:** `specialist_system(domain)` in `slm/contracts.py` and `spec_task_prompts(spec)` in
  `slm/manager/spec.py`, with up to 768 output tokens. Code writes `Shell.tsx`, so see `slm/pipeline/finish.py`.

The specialists were trained on one fixed template family with no styling. They copy that family well and don't
write other kinds of code. Results are in `results/2026-11-07/`.

```python
from peft import PeftModel
from transformers import AutoModelForCausalLM, AutoTokenizer

tokenizer = AutoTokenizer.from_pretrained("Qwen/Qwen3-0.6B")
base = AutoModelForCausalLM.from_pretrained("Qwen/Qwen3-0.6B", torch_dtype="auto")
model = PeftModel.from_pretrained(base, "models/spec-frontend")
```
