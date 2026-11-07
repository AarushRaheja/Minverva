"""App `slm-data` (claude-1): generate project + specialist data inside Modal and write it to slm-vol.

    uv run modal run modal_apps/data_app.py                # full build
    uv run modal run modal_apps/data_app.py --scale 0.05   # tiny smoke build
CPU only. No container stays up (min_containers=0).
"""

import subprocess

import modal

app = modal.App("slm-data")
vol = modal.Volume.from_name("slm-vol", version=2)
image = (
    modal.Image.debian_slim(python_version="3.11")
    .pip_install("pydantic>=2.7", "typer>=0.12")
    .add_local_python_source("slm")
)


@app.function(image=image, volumes={"/vol": vol}, timeout=1800, min_containers=0, scaledown_window=60)
def build(git_sha: str = "unknown", scale: float = 1.0) -> dict:
    from slm.bench.build import build_all

    man = build_all(root="/vol", git_sha=git_sha, scale=scale)
    vol.commit()
    return {k: man[k] for k in ("data_version", "seed", "git_sha", "projects", "domains", "manager")}


@app.local_entrypoint()
def main(scale: float = 1.0):
    import json

    sha = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    print(json.dumps(build.remote(sha, scale), indent=1))
