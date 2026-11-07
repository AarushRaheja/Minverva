"""App `slm-specialist-eval`: the manager's real plans go to the trained specialists, one task per call.

    uv run modal run modal_apps/specialist_eval_app.py --plans out/h100/nested-dev-raw.jsonl \
        --out out/specialist-test/team.json --seed 901 --n 10

--plans holds saved manager output. Omit it to use gold plans, which isolates the specialists. Score the
result with `python -m slm.bench.specialist_eval`.
"""

from __future__ import annotations

import json
import subprocess
import threading
import time
from pathlib import Path

import modal

from slm import contracts as C

SEED = 20261101
USD_PER_HOUR = 1.10
BATCH = 16
app = modal.App("slm-specialist-eval")
vol = modal.Volume.from_name(C.MODAL_VOLUME, version=2)
image = (
    modal.Image.debian_slim(python_version="3.11")
    .pip_install("torch==2.8.0", "transformers==4.57.1", "peft==0.17.1", "accelerate==1.10.1", "pydantic>=2.7")
    .env({"HF_HOME": f"{C.VOL}/hf", "TOKENIZERS_PARALLELISM": "false"})
    .add_local_python_source("slm")
)


class PowerLog:
    """Measured GPU power from nvidia-smi, once a second. It covers the GPU only, not CPU or memory."""

    def __init__(self):
        self.samples: list[float] = []
        self.done = threading.Event()
        self.thread = threading.Thread(target=self._run, daemon=True)

    def _run(self) -> None:
        while not self.done.wait(1.0):
            try:
                out = subprocess.run(["nvidia-smi", "--query-gpu=power.draw", "--format=csv,noheader,nounits"],
                                     capture_output=True, text=True, timeout=5).stdout.strip()
                self.samples.append(float(out.splitlines()[0]))
            except (OSError, ValueError, IndexError, subprocess.SubprocessError):
                pass

    def start(self) -> None:
        self.thread.start()

    def stop(self) -> dict:
        self.done.set()
        self.thread.join(timeout=5)
        n = len(self.samples)
        if not n:
            return {"samples": 0}
        return {"samples": n, "mean_watts": round(sum(self.samples) / n, 1), "peak_watts": max(self.samples),
                "watt_hours": round(sum(self.samples) / 3600, 2)}


@app.function(image=image, gpu="A10", volumes={C.VOL: vol}, timeout=3600, min_containers=0, scaledown_window=10)
def write_code(seed: int, projects: list[dict], skip_kinds: tuple[str, ...] = (), measure_latency: bool = True) -> dict:
    """Each project: {project_id, brief, spec}. Every task goes to its own category's adapter.

    `skip_kinds` are written by something else (Minerva's frontend agent and integrator). `measure_latency` re-runs up
    to three briefs one at a time to time them, so a production run turns it off."""
    import torch
    from peft import PeftModel
    from transformers import AutoModelForCausalLM, AutoTokenizer

    from slm.domains import ADAPTER
    from slm.llm.base import _strip_fences
    from slm.manager.spec import ProjectSpec, normalize_spec, spec_task_prompts, to_plan
    from slm.pipeline.finish import MAX_REPAIRS, code_artifact, finish_artifact, repair_prompt, written_by_code

    vol.reload()
    t0 = time.time()
    tok = AutoTokenizer.from_pretrained(C.BASE_MODEL)
    tok.padding_side = "left"
    base = AutoModelForCausalLM.from_pretrained(C.BASE_MODEL, torch_dtype=torch.bfloat16).to("cuda")
    model = None
    for d in C.DOMAINS:
        path = C.PATHS["adapter"].format(seed=seed, adapter_name=ADAPTER[d])
        if model is None:
            model = PeftModel.from_pretrained(base, path, adapter_name=d)
        else:
            model.load_adapter(path, adapter_name=d)
    model.eval()

    results, records = [], []
    for project in projects:
        row = {"project_id": project["project_id"], "brief": project["brief"], "spec": project["spec"], "tasks": []}
        results.append(row)
        try:
            spec = normalize_spec(ProjectSpec.model_validate_json(project["spec"]))
            row["spec"] = spec.model_dump_json()
            row["plan_repaired"] = spec != ProjectSpec.model_validate_json(project["spec"])
            plan = to_plan(spec)
            prompts = spec_task_prompts(spec)
        except ValueError as e:
            row["plan_error"] = str(e)[:300]
            continue
        row["plan"] = plan.model_dump_json()
        for t in plan.tasks:
            if t.kind in skip_kinds:
                continue
            record = {"id": t.id, "domain": t.domain, "kind": t.kind, "target": t.target, "prompt": prompts[t.id],
                      "attempts": 0, "by_code": written_by_code(t), "_plan": plan, "_task": t}
            if record["by_code"]:
                record["text"] = code_artifact(plan, t).model_dump_json()
            else:
                records.append(record)
            row["tasks"].append(record)

    tokens = {"n": 0}

    def generate(todo: list[dict], prompts_of) -> None:
        for domain in C.DOMAINS:
            mine = [r for r in todo if r["domain"] == domain]
            model.set_adapter(domain)
            for i in range(0, len(mine), BATCH):
                batch = mine[i:i + BATCH]
                texts = [tok.apply_chat_template(
                    [{"role": "system", "content": C.specialist_system(domain)},
                     {"role": "user", "content": prompts_of(r)}],
                    tokenize=False, add_generation_prompt=True, enable_thinking=False) for r in batch]
                enc = tok(texts, return_tensors="pt", padding=True).to("cuda")
                with torch.no_grad():
                    out = model.generate(**enc, max_new_tokens=768, do_sample=False, pad_token_id=tok.pad_token_id)
                for r, ids in zip(batch, out):
                    new = ids[enc["input_ids"].shape[1]:]
                    r["text"] = tok.decode(new, skip_special_tokens=True)
                    r["attempts"] += 1
                    tokens["n"] += int((new != tok.pad_token_id).sum())

    def settle(r: dict) -> str | None:
        """Apply the code fixes. Returns why the task still fails, or None."""
        try:
            artifact = finish_artifact(r["_task"], C.Artifact.model_validate_json(_strip_fences(r["text"])))
        except ValueError as e:
            return f"invalid JSON: {str(e)[:150]}"
        r["text"] = artifact.model_dump_json()
        ok, why = C.task_ok(r["_plan"], r["_task"], artifact)
        return None if ok else why

    power = PowerLog()
    power.start()
    t_gen = time.time()
    generate(records, lambda r: r["prompt"])
    failing = {id(r): why for r in records if (why := settle(r))}
    first_failures = len(failing)
    for _ in range(MAX_REPAIRS):
        todo = [r for r in records if id(r) in failing]
        if not todo:
            break
        generate(todo, lambda r: repair_prompt(r["prompt"], r["text"], failing[id(r)]))
        failing = {id(r): why for r in todo if (why := settle(r))}
    generation_seconds = time.time() - t_gen

    # Latency: one brief at a time with no batching, as a user would see it (specialists only).
    serial = []
    for row in results[:3] if measure_latency else []:
        todo = [r for r in row["tasks"] if not r["by_code"]]
        t1 = time.time()
        for r in todo:
            saved = (r["text"], r["attempts"])
            generate([r], lambda x: x["prompt"])
            r["text"], r["attempts"] = saved
        serial.append(round(time.time() - t1, 1))
    energy = power.stop()
    for r in records:
        r.pop("_plan"), r.pop("_task")
    for row in results:
        for r in row["tasks"]:
            r.pop("_plan", None), r.pop("_task", None)
    seconds = time.time() - t0
    return {"seed": seed, "seconds": round(seconds, 1), "usd_estimate": round(seconds / 3600 * USD_PER_HOUR, 3),
            "generation_seconds": round(generation_seconds, 1), "output_tokens": tokens["n"],
            "tasks_by_model": len(records), "tasks_failing_first_try": first_failures, "tasks_failing_after_repair": len(failing),
            "serial_seconds_per_brief": serial, "gpu_energy": energy, "projects": results}


@app.local_entrypoint()
def main(out: str, seed: int = 901, n: int = 10, plans: str = ""):
    from slm.bench.variety import generate_varied
    from slm.manager.spec import gold_spec

    gold = generate_varied(100, "dev", SEED)
    if plans:
        rows = [json.loads(line) for line in Path(plans).read_text().splitlines() if line.strip()][:n]
        projects = [{"project_id": r["project_id"], "brief": r["brief"], "spec": r["output"]} for r in rows]
    else:
        projects = [{"project_id": p.id, "brief": p.description, "spec": gold_spec(p.plan).model_dump_json()}
                    for p in gold[:n]]
    result = write_code.remote(seed, projects)
    path = Path(out)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result))
    print({k: v for k, v in result.items() if k != "projects"}, f"saved {path}")
