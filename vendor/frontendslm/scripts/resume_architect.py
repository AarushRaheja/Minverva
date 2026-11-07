"""Resume a stopped Architect phase without regenerating saved cases or changing settings."""
import argparse
import json
from pathlib import Path

import modal

from frontendslm.io import sha256, write_json
from modal_app import app, architect_batch, read_cases

root = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser()
parser.add_argument("run_id")
args = parser.parse_args()
directory = root / "artifacts" / args.run_id
if directory.parent != root / "artifacts":
    raise ValueError("Expected a direct run directory")
run = json.loads((directory / "run.json").read_text())
for name, expected in run["source_sha256"].items():
    if sha256((root / name).read_bytes()) != expected:
        raise ValueError(f"Runtime source changed since experiment started: {name}")
all_cases = {case["id"]: case for case in read_cases(50)}
cases = [all_cases[identifier] for identifier in run["case_ids"]]
with modal.enable_output(), app.run():
    rows = architect_batch.remote(cases, run["baselines"], run["model_lock"], args.run_id)
for row in rows:
    case_dir = directory / row["baseline"] / row["case_id"]
    write_json(case_dir / "generation.json", row)
    for name, content in (row.get("manifest") or {}).get("files", {}).items():
        target = case_dir / "source" / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content)
print(f"Recovered {len(rows)} generations. Continue with modal_app.py --mode render, then --mode critic.")
