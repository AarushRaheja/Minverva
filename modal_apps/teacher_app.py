"""App `slm-teacher`: Ollama on a Modal GPU rewords gold specs' prose (see slm/manager/enrich.py).

    uv run modal run modal_apps/teacher_app.py::pilot --model qwen3:14b --gpu L4 --n 20
    uv run modal run modal_apps/teacher_app.py::pilot --model llama3.3:70b --gpu L40S --n 20

Models are cached on the Volume, so each downloads once. `max_seconds` bounds GPU time for a run: the
job stops between projects when it is reached. Containers exit when the function returns.
"""

from __future__ import annotations

import json
import subprocess
import time
import urllib.request
from collections import Counter
from pathlib import Path

import modal

from slm.contracts import MODAL_VOLUME, PATHS, VOL

app = modal.App("slm-teacher")
vol = modal.Volume.from_name(MODAL_VOLUME, version=2)

SEED = 20261101
OLLAMA = "http://127.0.0.1:11434"
NUM_CTX = 4096  # one section at a time: small context keeps the KV cache from pushing layers off the GPU
NUM_PREDICT = 2500
USD_PER_HOUR = {"L4": 0.80, "L40S": 1.95}  # checked against modal.com/pricing before launch

image = (
    modal.Image.debian_slim(python_version="3.11")
    .apt_install("curl", "zstd", "pciutils")
    .run_commands("curl -fsSL https://ollama.com/install.sh | sh")
    .pip_install("pydantic>=2.7")
    .env({"OLLAMA_MODELS": f"{VOL}/ollama", "OLLAMA_KEEP_ALIVE": "-1", "OLLAMA_NUM_PARALLEL": "1",
          "OLLAMA_MAX_LOADED_MODELS": "1"})
    .add_local_python_source("slm")
)

def _post(path: str, payload: dict, timeout: float = 900.0) -> dict:
    req = urllib.request.Request(f"{OLLAMA}{path}", data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


def _get(path: str) -> dict:
    with urllib.request.urlopen(f"{OLLAMA}{path}", timeout=10) as r:
        return json.loads(r.read().decode())


def _start_ollama(model: str) -> dict:
    subprocess.Popen(["ollama", "serve"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(120):
        try:
            version = _get("/api/version")["version"]
            break
        except OSError:
            time.sleep(0.5)
    else:
        raise RuntimeError("ollama did not start")
    t0 = time.time()
    subprocess.run(["ollama", "pull", model], check=True, stdout=subprocess.DEVNULL)
    vol.commit()
    return {"ollama_version": version, "pull_seconds": round(time.time() - t0, 1)}


def _call(model: str, system: str, user: str, seed: int) -> dict:
    from slm.manager.enrich import SectionText

    payload = {
        "model": model,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        "format": SectionText.model_json_schema(),
        "options": {"temperature": 0.3, "num_ctx": NUM_CTX, "num_predict": NUM_PREDICT, "seed": seed},
        "stream": False,
    }
    if model.startswith("qwen3"):  # no thinking text: every token is billed GPU time
        payload["think"] = False
    return _post("/api/chat", payload)


def _gpu_placement(model: str) -> dict:
    """How much of the loaded model is really on the GPU: a split means CPU layers and slow output."""
    for m in _get("/api/ps").get("models", []):
        if m.get("name") == model or m.get("model") == model:
            return {"size_gb": round(m["size"] / 1e9, 1), "vram_gb": round(m["size_vram"] / 1e9, 1)}
    return {}


def _run(model: str, gpu: str, n: int, split: str, max_seconds: int) -> dict:
    from slm.bench.variety import generate_varied
    from slm.manager.enrich import (
        SECTIONS, TEACHER_SYSTEM, apply_texts, judge_section, section_items, section_prompt,
    )
    from slm.manager.spec import gold_spec, score_spec_json, summarize_specs, to_plan

    vol.reload()
    t_start = time.time()
    info = _start_ollama(model)
    gen_start = time.time()
    placement: dict = {}
    rows, specs, scores = [], [], []
    tokens, gen_seconds, retries = 0, 0.0, 0
    stopped_early = False
    projects = generate_varied(n, split, SEED)
    for pi, project in enumerate(projects):
        if time.time() - t_start > max_seconds:
            stopped_early = True
            break
        spec = gold_spec(project.plan)
        texts: dict[str, str] = {}
        entities = frozenset(t.target for t in project.plan.tasks)
        for section in SECTIONS:
            items = section_items(spec, section)
            prompt = section_prompt(project.description, section, items)
            result, reply, t_call = None, "", time.time()
            for attempt in range(2):  # one retry with a different seed
                retries += attempt
                try:
                    res = _call(model, TEACHER_SYSTEM, prompt, SEED + pi + attempt)
                except Exception as e:  # noqa: BLE001 - one failed call must not lose the run
                    result = judge_section(section, items, "")
                    result.problems = [f"call_error:{type(e).__name__}"]
                    continue
                reply = res["message"]["content"]
                tokens += res.get("eval_count", 0)
                gen_seconds += res.get("eval_duration", 0) / 1e9
                result = judge_section(section, items, reply, entities)
                if result.accepted:
                    break
            if not placement:
                placement = _gpu_placement(model)
            texts |= result.texts
            rows.append({"project_id": project.id, "brief": project.description, "section": section,
                         "accepted": result.accepted, "items": len(items), "changed": result.changed,
                         "problems": result.problems, "seconds": round(time.time() - t_call, 1),
                         "before": items, "after": result.texts,
                         "rejected_reply": "" if result.accepted else reply[:1500]})
        enriched = apply_texts(spec, texts)
        # The whole safety argument: rewording must never change what gets built or tested.
        assert to_plan(enriched) == project.plan, project.id
        specs.append(enriched.model_dump_json())
        scores.append(score_spec_json(specs[-1], project.plan))

    seconds = time.time() - t_start
    gen = time.time() - gen_start
    done = len(specs)
    accepted = sum(r["accepted"] for r in rows)
    problems = Counter(p.split(":", 2)[-2] if p.count(":") >= 2 else p.split(":")[0]
                       for r in rows for p in r["problems"])
    rate = USD_PER_HOUR[gpu]
    per_project = gen / done if done else 0.0
    summary = {
        "model": model, "gpu": gpu, "split": split, "requested": n, "projects_done": done,
        "stopped_early": stopped_early, **info, **placement,
        "total_seconds": round(seconds, 1), "generation_seconds": round(gen, 1),
        "seconds_per_project": round(per_project, 1),
        "tokens_per_second": round(tokens / gen_seconds, 1) if gen_seconds else 0.0,
        "output_tokens": tokens, "retries": retries,
        "sections": len(rows), "sections_accepted": accepted,
        "section_accept_rate": round(accepted / len(rows), 3) if rows else 0.0,
        "items_changed": sum(r["changed"] for r in rows),
        "items_total": sum(r["items"] for r in rows),
        "problem_counts": dict(problems.most_common(15)),
        "spec_scores": summarize_specs(scores),
        "usd_this_run": round(seconds / 3600 * rate, 2),
        "usd_per_1000_projects": round(per_project * 1000 / 3600 * rate, 2),
        "hours_per_1000_projects": round(per_project * 1000 / 3600, 1),
    }
    tag = f"{model.replace(':', '-').replace('.', '_')}-{gpu}-{split}"
    path = Path(PATHS["results"].format(name=f"teacher/{tag}"))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"summary": summary, "rows": rows, "specs": specs}))
    vol.commit()
    return {"summary": summary, "rows": rows, "specs": specs, "tag": tag}


_gpu_kw = {"image": image, "volumes": {VOL: vol}, "timeout": 3600, "min_containers": 0,
           "scaledown_window": 60}


@app.function(gpu="L4", **_gpu_kw)
def run_l4(model: str, n: int, split: str, max_seconds: int) -> dict:
    return _run(model, "L4", n, split, max_seconds)


@app.function(gpu="L40S", **_gpu_kw)
def run_l40s(model: str, n: int, split: str, max_seconds: int) -> dict:
    return _run(model, "L40S", n, split, max_seconds)


@app.local_entrypoint()
def pilot(model: str = "qwen3:14b", gpu: str = "L4", n: int = 20, split: str = "train",
          max_seconds: int = 1800):
    fn = {"L4": run_l4, "L40S": run_l40s}[gpu]
    out = fn.remote(model, n, split, max_seconds)
    local = Path("out/teacher")
    local.mkdir(parents=True, exist_ok=True)
    (local / f"{out['tag']}.json").write_text(json.dumps(out, indent=1))
    print(json.dumps(out["summary"], indent=1))
    print(f"saved {local / (out['tag'] + '.json')}")
