"""Measured results, explicit denominators, and no invented human labels."""
import json
from pathlib import Path

from frontendslm.io import write_json


def read(path):
    return json.loads(path.read_text()) if path.exists() else None


def score_evidence(evidence):
    if not evidence:
        return {"build_pass": False, "complete_render": False, "interaction_pass": False, "no_overflow": False, "no_serious_a11y": False, "release_eligible": False}
    views = evidence.get("views", {})
    complete = set(views) == {"desktop", "mobile", "tablet", "stress", "wide"} and not evidence.get("harness_error") and all(not v.get("harness_error") for v in views.values())
    build = bool((evidence.get("build") or {}).get("passed"))
    tests = evidence.get("tests", [])
    interactions = len(tests) >= 2 and all(t["passed"] for t in tests)
    overflow = complete and all(not v.get("horizontal_overflow") and not v.get("after_overflow", False) for v in views.values())
    violations = [a for v in views.values() for a in v.get("accessibility", []) + v.get("after_accessibility", [])]
    a11y = complete and not any(a.get("impact") in {"serious", "critical"} for a in violations)
    runtime = not evidence.get("runtime_errors") and not evidence.get("failed_requests") and all(not v.get("broken_images") for v in views.values())
    nonempty = complete and all(v.get("text_length", 0) > 20 for v in views.values())
    return {"build_pass": build, "complete_render": bool(complete), "interaction_pass": interactions,
        "no_overflow": bool(overflow), "no_serious_a11y": bool(a11y), "no_runtime_failures": runtime,
        "nonempty": bool(nonempty), "release_eligible": bool(build and complete and interactions and overflow and a11y and runtime and nonempty)}


def build_report(directory: Path):
    run = read(directory / "run.json")
    rows = []
    for baseline in run["baselines"]:
        for case_id in run["case_ids"]:
            path = directory / baseline / case_id
            generation = read(path / "generation.json")
            evidence = read(path / "render/evidence.json")
            critique = read(path / "critique.json")
            rows.append({"baseline": baseline, "case_id": case_id,
                "source_valid": bool(generation and generation.get("manifest")),
                **score_evidence(evidence), "critic_attempted": critique is not None,
                "critic_schema_valid": bool(critique and critique.get("schema_valid")),
                "critic_reference_valid": bool(critique and critique.get("schema_valid") and all(c["reference_valid"] for c in critique.get("reference_checks", []))),
                "critic_measured_valid": bool(critique and (critique.get("measurement_validation") or {}).get("valid")),
                "critic_effective_verdict": critique.get("effective_verdict") if critique else None,
                "generation_seconds": generation["seconds"] if generation else None,
                "critic_seconds": critique["seconds"] if critique else None,
                "generation_error": generation.get("error") if generation else "Missing generation",
                "build_error": (evidence.get("build") or {}).get("log") if evidence and not (evidence.get("build") or {}).get("passed") else None,
                "harness_error": evidence.get("harness_error") if evidence else None,
                "human_preference": None, "grounded_critique_precision": None, "grounded_critique_recall": None})
    summary = {}
    metrics = ["source_valid", "build_pass", "complete_render", "interaction_pass", "no_overflow", "no_serious_a11y", "release_eligible", "critic_attempted", "critic_schema_valid", "critic_reference_valid", "critic_measured_valid"]
    for baseline in run["baselines"]:
        group = [r for r in rows if r["baseline"] == baseline]
        summary[baseline] = {"attempts": len(group), **{metric: {"passed": sum(r[metric] for r in group), "total": len(group)} for metric in metrics}}
    payload = {"run_id": run["run_id"], "summary": summary, "rows": rows,
        "interpretation": "First-attempt engineering baseline. Reference-valid critiques are not human-verified grounded critiques.",
        "human_evaluation": "pending", "training_performed": False}
    write_json(directory / "summary.json", payload)
    lines = [f"# FrontEndSLM baseline: {run['run_id']}", "", "Untouched Qwen3-4B Architect and Qwen3-VL-4B Critic on Modal. No fine-tuning or revisions.", "",
        "All rates below use every requested generation as the denominator; missing outputs do not count as passes.", "",
        "| Metric | " + " | ".join(run["baselines"]) + " |", "|---|" + "---|" * len(run["baselines"])]
    for metric in metrics:
        lines.append("| " + metric.replace("_", " ") + " | " + " | ".join(f"{summary[b][metric]['passed']}/{summary[b][metric]['total']}" for b in run["baselines"]) + " |")
    lines += ["", "A0 uses a basic instruction plus the same output contract and tests. A1 adds detailed design guidance. Both use the same checkpoint, token budget, seed, tools, and requirements.", "",
        "Screenshots cover desktop (1440), tablet (768), mobile (390), stress (320), and wide (1920). Interaction assertions run at desktop and mobile. Accessibility is scanned in initial and final tested states.", "",
        "`release eligible` means the measured engineering checks passed. It does not establish aesthetic quality, full WCAG conformance, or readiness for a real external service.", "",
        "## Candidate results", "", "| Candidate | Build | Interactions | Overflow-free | Critic JSON |", "|---|---|---|---|---|"]
    for row in rows:
        lines.append(f"| {row['baseline']}/{row['case_id']} | {row['build_pass']} | {row['interaction_pass']} | {row['no_overflow']} | {row['critic_schema_valid']} |")
    lines += ["", "## Limits and next gate", "", "Human visual preference, critique precision/recall, severity agreement, and confidence calibration are unmeasured. No training data has been accepted. The 50 prompts and their outputs are evaluation-only and must never enter training.", "",
        "Review failed builds and observed defects. Independently annotate critiques, including correct abstentions, before enabling automatic revisions. Curate a separate licensed 300–500-example Architect pilot and 500–1,000-example Critic pilot before SFT.", "",
        "The current set is a small single-page benchmark with template-based workflows. It does not support claims about complex applications or the final 300-prompt research benchmark.", "",
        "Runtime configurations and frozen dependency/model/source hashes are stored alongside raw generations, evidence and critiques. GPU inference durations exclude image build, model loading, and idle time; the Modal billing dashboard is the source of actual charges."]
    (directory / "report.md").write_text("\n".join(lines) + "\n")
    print(json.dumps(summary, indent=2), flush=True)
    return payload
