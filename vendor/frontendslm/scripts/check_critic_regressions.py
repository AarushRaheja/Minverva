"""Replay immutable v1 evidence through the v2 critic, without regenerating or modifying v1."""
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from frontendslm.evidence import compact_evidence, validate_measured_critique
from frontendslm.io import write_json
from frontendslm.schemas import Critique
from modal_app import MODEL_LOCK, app, critic_batch, read_cases, results

run_id = "critic-regression-v2"
output = ROOT / "artifacts" / run_id
selected = {"catalog_05", "collaboration_05", "forms_03", "operations_01"}
cases = [c for c in read_cases(10) if c["id"] in selected]
for case in cases:
    target = output / "A1" / case["id"] / "render"
    shutil.copytree(ROOT / "artifacts/pilot-baseline-v1/A1" / case["id"] / "render", target, dirs_exist_ok=True)
write_json(output / "provenance.json", {"source_run": "pilot-baseline-v1", "case_ids": sorted(selected),
    "purpose": "Regression replay of two previously missed contrast failures, a build failure and a passing case"})
with app.run():
    with results.batch_upload(force=True) as batch:
        batch.put_directory(output, f"/{run_id}")
    rows = critic_batch.remote(cases, ["A1"], MODEL_LOCK, run_id)
for row in rows:
    write_json(output / "A1" / row["case_id"] / "critique.json", row)
    evidence = json.loads((output / "A1" / row["case_id"] / "render/evidence.json").read_text())
    case = next(c for c in cases if c["id"] == row["case_id"])
    validation = validate_measured_critique(Critique.model_validate(row["critique"]), compact_evidence(evidence, case["tests"]))
    write_json(output / "A1" / row["case_id"] / "revalidation.json", validation)
    print(json.dumps({"case_id": row["case_id"], "schema_valid": row["schema_valid"], "current_validation": validation}))
    if not row["schema_valid"] or not validation["valid"]:
        raise RuntimeError(f"Critic regression failed: {row['case_id']}")
print("All four critic regressions passed")
