"""Bounded batch compute. Run with `modal run modal_app.py --help`. No public endpoints."""
import json
from datetime import UTC
from pathlib import Path

import modal

ROOT = Path(__file__).resolve().parent
app = modal.App("frontendslm-baseline")
weights = modal.Volume.from_name("frontendslm-model-cache", create_if_missing=True)
results = modal.Volume.from_name("frontendslm-experiments", create_if_missing=True)
MODEL_LOCK = json.loads((ROOT / "configs/models.lock.json").read_text()) if modal.is_local() else {}

cpu_image = (modal.Image.debian_slim(python_version="3.12")
    .pip_install("huggingface-hub==0.36.2", "pydantic==2.14.3")
    .env({"HF_HOME": "/models", "HF_HUB_DISABLE_TELEMETRY": "1"})
    .add_local_python_source("frontendslm"))

gpu_image = (modal.Image.debian_slim(python_version="3.12")
    .pip_install("torch==2.8.0", "torchvision==0.23.0", "transformers==4.57.3", "accelerate==1.10.1", "pillow==11.3.0",
                 "huggingface-hub==0.36.2", "pydantic==2.14.3")
    .pip_install("xgrammar==0.2.8", "torch==2.8.0", "transformers==4.57.3")
    .env({"HF_HOME": "/models", "HF_HUB_DISABLE_TELEMETRY": "1", "TOKENIZERS_PARALLELISM": "false"})
    .add_local_python_source("frontendslm"))

# Dependencies are installed during trusted image construction, before egress is disabled.
render_image = (modal.Image.from_registry("node:22.14.0-bookworm-slim")
    .add_local_dir(ROOT / "sandbox", "/work", copy=True, ignore=["node_modules", "dist"])
    .workdir("/work")
    .run_commands("npm ci --ignore-scripts --no-audit --no-fund", "npx playwright install --with-deps chromium"))


@app.function(image=cpu_image, volumes={"/models": weights}, timeout=1800, retries=0, max_containers=1)
def download_models(lock: dict):
    import time

    from huggingface_hub import snapshot_download
    stats = {}
    for role, cfg in lock.items():
        begin = time.monotonic()
        path = snapshot_download(cfg["model"], revision=cfg["revision"],
            ignore_patterns=["*.bin", "*.pth", "*.onnx", "*.gguf"])
        weights.commit()
        stats[role] = {"path": path, "seconds": time.monotonic() - begin, **cfg}
        print(f"Cached {role}: {cfg['revision']}", flush=True)
    return stats


@app.function(image=gpu_image, gpu="L40S", cpu=2, memory=16384, volumes={"/models": weights, "/results": results},
              timeout=3600, retries=0, max_containers=1, scaledown_window=2)
def architect_batch(cases: list[dict], baselines: list[str], lock: dict, run_id: str):
    from frontendslm.inference import generate_architect
    weights.reload()
    results.reload()
    return generate_architect(cases, baselines, lock["architect"], Path("/results") / run_id, results.commit)


@app.function(image=gpu_image, gpu="L40S", cpu=2, memory=16384, volumes={"/models": weights, "/results": results},
              timeout=3600, retries=0, max_containers=1, scaledown_window=2)
def critic_batch(cases: list[dict], baselines: list[str], lock: dict, run_id: str):
    from frontendslm.inference import generate_critiques
    weights.reload()
    results.reload()
    return generate_critiques(cases, baselines, lock["critic"], Path("/results") / run_id, results.commit)


def render_case(case: dict, manifest: dict, directory: Path) -> dict:
    import time

    from frontendslm.io import write_json
    from frontendslm.schemas import SourceManifest
    source = SourceManifest.model_validate(manifest)
    directory.mkdir(parents=True, exist_ok=True)
    begin = time.monotonic()
    sb = modal.Sandbox.create("sleep", "300", app=app, image=render_image,
        workdir="/work", timeout=300, cpu=2, memory=4096, block_network=True)
    evidence = None
    try:
        for name, content in source.files.items():
            sb.filesystem.write_text(content, f"/work/{name}")
        sb.filesystem.write_text(json.dumps(case), "/work/task.json")
        process = sb.exec("node", "/work/evaluate.mjs", timeout=240)
        stdout = process.stdout.read()
        stderr = process.stderr.read()
        process.wait()
        (directory / "runner.log").write_text(stdout + "\n" + stderr)
        if process.returncode != 0:
            raise RuntimeError(f"Renderer exited {process.returncode}: {stderr[-2000:]}")
        evidence = json.loads(sb.filesystem.read_text("/work/result/evidence.json"))
        for name in evidence.get("screenshots", {}).values():
            if name not in {f"{v}.png" for v in ["desktop", "mobile", "tablet", "stress", "wide", "desktop-after", "mobile-after"]}:
                raise ValueError("Unexpected screenshot path")
            (directory / name).write_bytes(sb.filesystem.read_bytes(f"/work/result/{name}"))
    except Exception as error:  # noqa: BLE001 -- persist remote infrastructure failures as explicit missing evidence
        evidence = {"build": None, "harness_error": str(error), "views": {}, "tests": [], "references": [], "screenshots": {}}
    finally:
        sb.terminate()
    evidence["sandbox"] = {"id": sb.object_id, "block_network": True, "seconds": time.monotonic() - begin,
        "cpu": 2, "memory_mib": 4096, "timeout_seconds": 300}
    write_json(directory / "evidence.json", evidence)
    return evidence


def read_cases(count):
    from frontendslm.io import sha256
    from frontendslm.schemas import BenchmarkCase
    data = (ROOT / "benchmarks/pilot_v1.jsonl").read_bytes()
    manifest = json.loads((ROOT / "benchmarks/pilot_v1.manifest.json").read_text())
    if sha256(data) != manifest["sha256"]:
        raise ValueError("Frozen benchmark checksum mismatch")
    if not 1 <= count <= 50:
        raise ValueError("count must be 1–50")
    cases = [BenchmarkCase.model_validate_json(line).model_dump() for line in data.splitlines()]
    # Every ten selected cases span all ten categories and all five style briefs.
    # Selection is fixed before the baseline, independent of model outcomes.
    ordered = [cases[((wave + category) % 5) * 10 + category]
               for wave in range(5) for category in range(10)]
    return ordered[:count]


@app.local_entrypoint()
def main(mode: str = "smoke", count: int = 20, baselines: str = "A0,A1", run_id: str = "", max_render_workers: int = 2):
    import re
    import subprocess
    from concurrent.futures import ThreadPoolExecutor, as_completed
    from datetime import datetime

    from frontendslm.io import sha256, write_json
    from frontendslm.references import reference_manifest
    from frontendslm.report import build_report

    if mode not in {"smoke", "cache", "baseline", "critic", "render", "references"}:
        raise ValueError("Unsupported mode")
    baseline_list = baselines.split(",")
    if not set(baseline_list) <= {"A0", "A1"} or not baseline_list:
        raise ValueError("Expected A0,A1")
    if not 1 <= max_render_workers <= 4:
        raise ValueError("Limit renderer concurrency to 1–4")
    run_id = run_id or datetime.now(UTC).strftime("baseline-%Y%m%dT%H%M%SZ")
    if not re.fullmatch(r"[a-zA-Z0-9_-]{1,80}", run_id):
        raise ValueError("Invalid run ID")
    cases = read_cases(count)
    output = ROOT / "artifacts" / run_id
    output.mkdir(parents=True, exist_ok=True)
    if mode == "cache":
        write_json(output / "download.json", download_models.remote(MODEL_LOCK))
        return
    if mode in {"smoke", "references"}:
        if mode == "smoke":
            cases = cases[:1]
        for case in cases:
            evidence = render_case(case, reference_manifest(case), output / "references" / case["id"])
            passed = evidence.get("build", {}).get("passed") if evidence.get("build") else False
            passed = passed and all(t["passed"] for t in evidence.get("tests", [])) and len(evidence.get("tests", [])) == 2
            passed = passed and all(not v.get("harness_error") and not v.get("horizontal_overflow") for v in evidence.get("views", {}).values())
            print(f"Reference {case['id']}: {'PASS' if passed else 'FAIL'}", flush=True)
            if not passed:
                raise RuntimeError(f"Reference failed; inspect {output}")
        print(f"Validated {len(cases)} reference fixtures at {output}")
        return

    if mode == "baseline":
        if (output / "run.json").exists():
            raise ValueError("Run already exists. Use a new run ID; render/critic modes resume separate phases.")
        tracked = sorted([*ROOT.glob("src/**/*.py"), *ROOT.glob("sandbox/*.*"), *ROOT.glob("sandbox/src/*"), ROOT / "modal_app.py", ROOT / "uv.lock"])
        source_hashes = {str(p.relative_to(ROOT)): sha256(p.read_bytes()) for p in tracked if p.is_file()}
        write_json(output / "run.json", {"schema_version": "1.0", "run_id": run_id, "started_at": datetime.now(UTC).isoformat(),
            "git_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
            "git_dirty": bool(subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT, text=True).strip()),
            "source_sha256": source_hashes, "model_lock": MODEL_LOCK,
            "benchmark_manifest": json.loads((ROOT / "benchmarks/pilot_v1.manifest.json").read_text()),
            "case_ids": [c["id"] for c in cases], "baselines": baseline_list, "gpu": "L40S",
            "phase_timeout_seconds": 3600, "max_render_workers": max_render_workers,
            "pipeline_version": "6.0", "generation_protocol": "component-v2",
            "critic_protocol": "schema-constrained-measured-observations-v6",
            "comparison_run": None,
            "training_performed": False, "max_revisions": 0, "max_generation_attempts": 1,
            "notes": "First-attempt untouched-model baselines; no repair, fine-tuning, or human preference claims."})
        write_json(output / "download.json", download_models.remote(MODEL_LOCK))
        rows = architect_batch.remote(cases, baseline_list, MODEL_LOCK, run_id)
        for row in rows:
            case_dir = output / row["baseline"] / row["case_id"]
            write_json(case_dir / "generation.json", row)
            for name, content in (row.get("manifest") or {}).get("files", {}).items():
                path = case_dir / "source" / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(content)
    else:
        run = json.loads((output / "run.json").read_text())
        case_ids = set(run["case_ids"])
        cases = [c for c in read_cases(50) if c["id"] in case_ids]
        baseline_list = run["baselines"]
        rows = [json.loads(p.read_text()) for p in sorted(output.glob("A*/*/generation.json"))]

    if mode in {"baseline", "render"}:
        by_id = {c["id"]: c for c in cases}
        with ThreadPoolExecutor(max_workers=max_render_workers) as executor:
            pending = {}
            for row in rows:
                if row["manifest"] is not None:
                    target = output / row["baseline"] / row["case_id"] / "render"
                    if (target / "evidence.json").exists():
                        continue
                    pending[executor.submit(render_case, by_id[row["case_id"]], row["manifest"], target)] = row
            for future in as_completed(pending):
                row = pending[future]
                evidence = future.result()
                print(json.dumps({"stage": "render", "baseline": row["baseline"], "case": row["case_id"],
                    "build": evidence.get("build", {}).get("passed") if evidence.get("build") else None,
                    "tests_passed": sum(t["passed"] for t in evidence.get("tests", [])),
                    "harness_error": evidence.get("harness_error")}), flush=True)
        with results.batch_upload(force=True) as batch:
            batch.put_directory(output, f"/{run_id}")
        if mode == "render":
            build_report(output)
            return

    critiques = critic_batch.remote(cases, baseline_list, MODEL_LOCK, run_id)
    for critique in critiques:
        write_json(output / critique["baseline"] / critique["case_id"] / "critique.json", critique)
    build_report(output)
    print(f"Completed experiment: {output}", flush=True)
