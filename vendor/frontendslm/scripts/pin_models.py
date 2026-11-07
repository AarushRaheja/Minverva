"""Resolve named official checkpoints once. Never silently advance an existing lock."""
from pathlib import Path

from huggingface_hub import HfApi

from frontendslm.io import write_json

path = Path(__file__).resolve().parents[1] / "configs/models.lock.json"
if path.exists():
    raise SystemExit("Model revisions already pinned; review changes explicitly to repin")
api = HfApi()
models = {}
for role, name in [("architect", "Qwen/Qwen3-4B-Instruct-2507"), ("critic", "Qwen/Qwen3-VL-4B-Instruct")]:
    info = api.model_info(name)
    models[role] = {"model": name, "revision": info.sha, "license": info.card_data.get("license"), "trust_remote_code": False}
write_json(path, models)
print(path.read_text())
