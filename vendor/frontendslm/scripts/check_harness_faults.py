"""Verify that controlled defects fail the correct measured gates on Modal."""
import copy
import json
from pathlib import Path

import modal

from frontendslm.references import reference_manifest
from frontendslm.report import score_evidence
from modal_app import app, read_cases, render_case

case = read_cases(1)[0]
source = reference_manifest(case)
mutations = {}
overflow = copy.deepcopy(source)
overflow["files"]["src/index.css"] += "\nbody { min-width: 1600px; }\n"
mutations["overflow"] = (overflow, "no_overflow")
broken_filter = copy.deepcopy(source)
broken_filter["files"]["src/App.tsx"] = broken_filter["files"]["src/App.tsx"].replace(
    "onChange={e=>setQuery(e.target.value)}", "onChange={()=>{}}")
mutations["interaction"] = (broken_filter, "interaction_pass")
invalid = copy.deepcopy(source)
invalid["files"]["src/App.tsx"] += "\nconst impossible: number = 'not a number';\n"
mutations["compile"] = (invalid, "build_pass")

with modal.enable_output(), app.run():
    for name, (manifest, gate) in mutations.items():
        evidence = render_case(case, manifest, Path("artifacts/harness-negative-v1") / name)
        if evidence.get("harness_error"):
            raise RuntimeError(evidence["harness_error"])
        score = score_evidence(evidence)
        assert not score[gate], f"Harness missed intentional {name} defect"
        print(json.dumps({"mutation": name, "expected_failure": gate, "observed": score[gate]}), flush=True)
