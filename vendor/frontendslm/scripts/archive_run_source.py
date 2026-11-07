"""Archive the exact working sources whose hashes were captured before inference."""
import argparse
import json
import zipfile
from pathlib import Path

from frontendslm.io import sha256

root = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser()
parser.add_argument("run_id")
args = parser.parse_args()
directory = root / "artifacts" / args.run_id
if directory.parent != root / "artifacts":
    raise ValueError("Expected a direct run directory")
run = json.loads((directory / "run.json").read_text())
paths = set(run["source_sha256"])
for name, checksum in run["source_sha256"].items():
    if sha256((root / name).read_bytes()) != checksum:
        raise ValueError(f"Source changed after run began: {name}")
paths.update(["pyproject.toml", ".python-version", "configs/models.lock.json", "benchmarks/pilot_v1.jsonl", "benchmarks/pilot_v1.manifest.json"])
with zipfile.ZipFile(directory / "source_snapshot.zip", "w", zipfile.ZIP_DEFLATED) as archive:
    for name in sorted(paths):
        archive.write(root / name, name)
    archive.writestr("run.json", json.dumps(run, indent=2))
print(f"Archived {len(paths)} verified source and configuration files")
