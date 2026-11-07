"""The real models and the sandbox, behind the Engine interface in minerva/pipeline.py.

Reuses the two batch functions that were measured for real (manager_app.plan_briefs, specialist_eval_app.write_code)
and FrontEndSLM's inference code, with their pinned images, so the earlier measurements still describe them.
Generated code only ever runs in a network-blocked Modal Sandbox with no secrets.
"""

from __future__ import annotations

import json
import shlex
import sys
import time
from pathlib import Path

import modal

ROOT = Path(__file__).resolve().parent.parent

# Containers import this module too, but only `frontendslm` and `design` are mounted there. The rest is local-only.
if modal.is_local():
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    from minerva import vendored
    from minerva.integrator.assemble import HOST_KINDS
    from minerva.integrator.host_files import REQUIREMENTS
    from minerva.engines import MODAL_ARCHITECT_USD, MODAL_STAGE_USD
    from modal_apps import manager_app, specialist_eval_app

    FRONTEND = vendored.FRONTEND

ADAPTER_SEED = 901
MANAGER_RUN = "m-spec"
L40S_USD_PER_SECOND = 0.00060  # GPU, 2 cores and 16 GiB at Modal's listed rates; an estimate, see docs/consolidation
SCREENSHOTS = {f"{v}.png" for v in ("desktop", "mobile", "tablet", "stress", "wide", "desktop-after", "mobile-after")}
# Stage cost estimates live in minerva/engines.py (MODAL_STAGE_USD), so UIs and the budget check agree.

app = modal.App("minerva-frontend")
weights = modal.Volume.from_name("frontendslm-model-cache", create_if_missing=True)
results = modal.Volume.from_name("frontendslm-experiments", create_if_missing=True)

cpu_image = (modal.Image.debian_slim(python_version="3.12")
             .pip_install("huggingface-hub==0.36.2", "pydantic==2.14.3")
             .env({"HF_HOME": "/models", "HF_HUB_DISABLE_TELEMETRY": "1"}))

gpu_image = (modal.Image.debian_slim(python_version="3.12")
             .pip_install("torch==2.8.0", "torchvision==0.23.0", "transformers==4.57.3", "accelerate==1.10.1",
                          "pillow==11.3.0", "huggingface-hub==0.36.2", "pydantic==2.14.3", "xgrammar==0.2.8")
             .env({"HF_HOME": "/models", "HF_HUB_DISABLE_TELEMETRY": "1", "TOKENIZERS_PARALLELISM": "false"})
             .add_local_python_source("frontendslm", "design"))

if modal.is_local():
    # Everything is installed while the image builds, before the sandbox's network is blocked.
    stack_image = (modal.Image.from_registry("node:22.14.0-bookworm-slim")
                   .apt_install("postgresql", "python3", "python3-venv")
                   .add_local_file(ROOT / "harness" / "package.json", "/harness/package.json", copy=True)
                   .add_local_file(ROOT / "harness" / "package-lock.json", "/harness/package-lock.json", copy=True)
                   .add_local_dir(ROOT / "templates" / "frontend", "/template", copy=True, ignore=["node_modules", "dist"])
                   .run_commands(
                       "cd /harness && npm ci --ignore-scripts --no-audit --no-fund",
                       "cd /harness && npx playwright install --with-deps chromium",
                       "cd /template && npm ci --ignore-scripts --no-audit --no-fund",
                       "python3 -m venv /stack-venv",
                       # The sandbox always has DATABASE_URL, so it never needs the embedded preview database.
                       f"/stack-venv/bin/pip install {' '.join(r for r in REQUIREMENTS.split(chr(10)) if r and ';' not in r)}",
                   )
                   .add_local_file(ROOT / "harness" / "evaluate.mjs", "/harness/evaluate.mjs", copy=True))

_gpu = dict(image=gpu_image, gpu="L40S", cpu=2, memory=16384, volumes={"/models": weights, "/results": results},
            timeout=3600, retries=0, max_containers=1, scaledown_window=2)


@app.function(image=cpu_image, volumes={"/models": weights}, timeout=1800, retries=0, max_containers=1)
def download_models(lock: dict) -> list[str]:
    from huggingface_hub import snapshot_download

    done = []
    for cfg in lock.values():
        snapshot_download(cfg["model"], revision=cfg["revision"], ignore_patterns=["*.bin", "*.pth", "*.onnx", "*.gguf"])
        weights.commit()
        done.append(cfg["model"])
    return done


def _billed(row: dict, started: float) -> dict:
    seconds = time.monotonic() - started
    return {**row, "wall_seconds": round(seconds, 1), "usd": round(seconds * L40S_USD_PER_SECOND, 3)}


@app.function(**_gpu)
def architect_fn(job: dict, config: dict, key: str) -> dict:
    from frontendslm.inference import generate_architect

    started = time.monotonic()
    weights.reload()
    results.reload()
    rows = generate_architect([job], ["A1"], config, Path("/results") / "minerva" / key, results.commit)
    return _billed(json.loads(json.dumps(rows[0], default=str)), started)


@app.function(**_gpu)
def critic_fn(case: dict, config: dict, key: str) -> dict | None:
    from frontendslm.inference import generate_critiques

    started = time.monotonic()
    weights.reload()
    results.reload()
    rows = generate_critiques([case], ["A1"], config, Path("/results") / "minerva" / key, results.commit)
    return _billed(rows[0], started) if rows else None


@app.function(**_gpu)
def intent_fn(brief: dict, config: dict, preferences: dict, key: str) -> dict:
    from design.inference import interpret_intents

    started = time.monotonic()
    weights.reload()
    results.reload()
    rows = interpret_intents([{"id": "brief", "brief": brief}], preferences, config, Path("/results") / "minerva" / key,
                             results.commit)
    return _billed(json.loads(json.dumps(rows[0], default=str)), started)


class ModalEngine:
    name = "modal"

    def __init__(self, architect: str = "thinking"):
        if architect not in ("thinking", "instruct"):
            raise ValueError("architect must be thinking or instruct")
        self.architect_profile = architect
        self.instruct_lock = json.loads((FRONTEND / "configs" / "models.lock.json").read_text())
        self.lock = json.loads((FRONTEND / "configs" / (
            "models-thinking.lock.json" if architect == "thinking" else "models.lock.json")).read_text())
        self.models_ready = False

    def cost_estimate(self, stage: str) -> float:
        if stage == "architect":
            return MODAL_ARCHITECT_USD[self.architect_profile]
        return MODAL_STAGE_USD[stage]

    def _prepare_models(self) -> None:
        if not self.models_ready:
            with modal.enable_output(), app.run():
                download_models.remote({**self.lock, "instruct": self.instruct_lock["architect"]})
            self.models_ready = True

    def plan(self, brief: str) -> dict:
        with modal.enable_output(), manager_app.app.run():
            out = manager_app.plan_briefs.remote(MANAGER_RUN, [brief])
        row = out["rows"][0]
        return {"spec": row["output"], "finish_reason": row["finish_reason"], "compile_error": row["compile_error"],
                "output_tokens": row["output_tokens"], "seconds": out["seconds"], "usd": out["usd_estimate"]}

    def backend(self, spec_json: str, brief: str) -> dict:
        from slm.contracts import Artifact
        from slm.llm.base import _strip_fences

        with modal.enable_output(), specialist_eval_app.app.run():
            out = specialist_eval_app.write_code.remote(
                ADAPTER_SEED, [{"project_id": "minerva", "brief": brief, "spec": spec_json}],
                skip_kinds=tuple(sorted(HOST_KINDS)), measure_latency=False)
        row = out["projects"][0]
        artifacts, invalid = {}, []
        for task in row.get("tasks", []):
            try:
                artifacts[task["id"]] = Artifact.model_validate_json(_strip_fences(task["text"])).model_dump_json()
            except ValueError as error:
                invalid.append({"task": task["id"], "error": str(error)[:200]})
        return {"artifacts": artifacts, "invalid": invalid, "plan_error": row.get("plan_error"), "seconds": out["seconds"],
                "usd": out["usd_estimate"], "tasks_failing_after_repair": out["tasks_failing_after_repair"]}

    def intent(self, brief: str, look: str) -> dict:
        self._prepare_models()
        preferences = json.loads((FRONTEND / "design" / "preferences.json").read_text())
        key = f"intent-{int(time.time())}"
        with modal.enable_output(), app.run():
            # A dict is what FrontEndSLM's intent stage expects for a structured brief: each value can be quoted verbatim.
            job = {"what": brief, **({"how_it_should_look": look} if look else {})}
            row = intent_fn.remote(job, self.instruct_lock["architect"], preferences, key)
        usable = row.get("schema_valid") and not row.get("provenance_errors") and row.get("ready_for_generation")
        return {"intent": row["intent"] if usable else None, "questions": row.get("clarifying_questions") or [],
                "error": row.get("error") or (row.get("provenance_errors") or None), "seconds": row.get("seconds"),
                "usd": row["usd"]}

    def architect(self, job: dict, run_key: str) -> dict:
        self._prepare_models()
        decoding = "thinking-recommended" if self.architect_profile == "thinking" else "greedy"
        with modal.enable_output(), app.run():
            return architect_fn.remote({**job, "repair_decoding": decoding}, self.lock["architect"], run_key)

    def critic(self, case: dict, evidence_dir: Path, run_key: str) -> dict | None:
        with results.batch_upload(force=True) as batch:
            batch.put_directory(str(evidence_dir), f"/minerva/{run_key}/A1/{case['id']}/render")
        with modal.enable_output(), app.run():
            return critic_fn.remote(case, self.lock["critic"], run_key)

    def audit(self, files: dict[str, str], task: dict, out_dir: Path) -> dict:
        """Run the harness in an isolated, network-blocked sandbox with no secrets."""
        out_dir.mkdir(parents=True, exist_ok=True)
        sandbox_app = modal.App.lookup("minerva-sandbox", create_if_missing=True)
        began = time.monotonic()
        sb = modal.Sandbox.create("sleep", "900", app=sandbox_app, image=stack_image, workdir="/harness", timeout=900,
                                  cpu=4, memory=8192, block_network=True)
        try:
            dirs = sorted({str(Path("/project", name).parent) for name in files})
            sb.exec("mkdir", "-p", "/out", *dirs, timeout=30).wait()
            for name, content in files.items():
                target = Path("/project", name)
                if ".." in Path(name).parts:
                    raise ValueError(f"unsafe path from generated artifact: {name!r}")
                sb.filesystem.write_text(content, str(target))
            sb.filesystem.write_text(json.dumps(task), "/task.json")
            sb.exec("ln", "-s", "/template/node_modules", "/project/frontend/node_modules", timeout=30).wait()
            environment = {"AUDIT_PROJECT": "/project", "AUDIT_TASK": "/task.json", "AUDIT_OUT": "/out",
                           "AUDIT_PYTHON": "/stack-venv/bin/python", "AUDIT_PORT": "4173",
                           "AUDIT_PG_BIN": "/usr/lib/postgresql/15/bin"}
            command = "env " + " ".join(f"{k}={shlex.quote(v)}" for k, v in environment.items()) + " node /harness/evaluate.mjs"
            process = sb.exec("bash", "-c", command, timeout=840)
            stdout, stderr = process.stdout.read(), process.stderr.read()
            process.wait()
            (out_dir / "runner.log").write_text(stdout + "\n" + stderr)
            evidence = json.loads(sb.filesystem.read_text("/out/evidence.json"))
            for name in evidence.get("screenshots", {}).values():
                if name not in SCREENSHOTS:
                    raise ValueError("unexpected screenshot path")
                (out_dir / name).write_bytes(sb.filesystem.read_bytes(f"/out/{name}"))
        except Exception as error:  # noqa: BLE001 - infrastructure failures become explicit missing evidence
            evidence = {"build": None, "harness_error": f"sandbox: {error}", "views": {}, "tests": [], "references": [],
                        "screenshots": {}, "api_checks": [], "stack": {}}
        finally:
            sb.terminate()
        evidence["sandbox"] = {"id": sb.object_id, "block_network": True, "seconds": round(time.monotonic() - began, 1),
                               "cpu": 4, "memory_mib": 8192, "timeout_seconds": 900}
        (out_dir / "evidence.json").write_text(json.dumps(evidence))
        return evidence
