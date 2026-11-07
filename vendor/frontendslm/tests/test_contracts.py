import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from frontendslm.io import parse_json_response, sha256
from frontendslm.prompts import architect_messages
from frontendslm.references import reference_manifest
from frontendslm.report import score_evidence
from frontendslm.schemas import (
    BenchmarkCase,
    Critique,
    EvidenceReference,
    SourceManifest,
    validate_critique_references,
)

ROOT = Path(__file__).resolve().parents[1]


def cases():
    return [json.loads(line) for line in (ROOT / "benchmarks/pilot_v1.jsonl").read_text().splitlines()]


def test_frozen_benchmark_and_diversity():
    data = (ROOT / "benchmarks/pilot_v1.jsonl").read_bytes()
    manifest = json.loads((ROOT / "benchmarks/pilot_v1.manifest.json").read_text())
    assert sha256(data) == manifest["sha256"]
    validated = [BenchmarkCase.model_validate(case) for case in cases()]
    assert len(validated) == 50
    assert len({case.id for case in validated}) == 50
    assert len({case.category for case in validated[:20]}) == 10
    assert all(case.split == "evaluation" for case in validated)
    assert not manifest["training_use"]


@pytest.mark.parametrize("path", ["../secret", "/etc/passwd", "package.json", "src/../../run.js", "vite.config.js"])
def test_model_cannot_change_executable_configuration_or_paths(path):
    manifest = reference_manifest(cases()[0])
    manifest["files"][path] = "malicious"
    with pytest.raises(ValidationError):
        SourceManifest.model_validate(manifest)


def test_reference_fixtures_are_valid_contracts():
    for case in cases()[:20]:
        SourceManifest.model_validate(reference_manifest(case))


def test_json_parser_does_not_repair_or_hide_model_errors():
    assert parse_json_response('```json\n{"a":1}\n```') == {"a": 1}
    for text in ['Here is JSON: {"a":1}', '{"a":1} trailing', '{"a":1,}', '{"a":']:
        with pytest.raises(ValueError):
            parse_json_response(text)
    with pytest.raises(TypeError):
        parse_json_response("[]")


@pytest.mark.parametrize("region", [[0.8, 0, 0.2, 1], [0, 0, 1.1, 1], [0, 0, 1], None])
def test_visual_evidence_requires_valid_normalized_box(region):
    with pytest.raises(ValidationError):
        EvidenceReference(type="screenshot", ref="desktop", region=region)


def test_interaction_critique_cannot_rely_on_pixels_alone():
    critique = Critique.model_validate({"schema_version": "1.0", "verdict": "revise", "uncertainties": [], "summary": "Check control",
        "issues": [{"id": "i1", "category": "interaction", "severity": "major", "confidence": 0.9,
            "evidence": [{"type": "screenshot", "ref": "desktop", "region": [0, 0, 1, 1]}],
            "observation": "Button does not work", "recommendation": "Repair handler", "acceptance_test": "Click succeeds"}]})
    checks = validate_critique_references(critique, {"references": [{"type": "screenshot", "ref": "desktop"}]})
    assert not checks[0]["reference_valid"]
    assert checks[0]["human_grounding_verified"] is None
    critique.issues[0].category = "visual_hierarchy"
    assert validate_critique_references(critique, {"references": []})[0]["reference_valid"] is False


def test_missing_evidence_is_never_a_pass():
    for evidence in [None, {}, {"build": {"passed": True}, "views": {}, "tests": []}]:
        score = score_evidence(evidence)
        assert not score["release_eligible"]
        assert not score["complete_render"]
        assert not score["interaction_pass"]


def test_harness_errors_and_serious_violations_block_acceptance():
    evidence = {"build": {"passed": True}, "tests": [{"passed": True}, {"passed": True}],
        "views": {view: {"text_length": 100, "horizontal_overflow": False, "accessibility": []}
                  for view in ["desktop", "mobile", "tablet", "stress", "wide"]}}
    assert score_evidence(evidence)["release_eligible"]
    evidence["views"]["mobile"]["after_accessibility"] = [{"impact": "serious"}]
    assert not score_evidence(evidence)["release_eligible"]
    evidence["views"]["mobile"].pop("after_accessibility")
    evidence["views"]["stress"]["harness_error"] = "Timed out"
    assert not score_evidence(evidence)["complete_render"]


def test_baselines_share_requirements_and_output_contract():
    case = cases()[0]
    a0 = architect_messages(case, "A0")
    a1 = architect_messages(case, "A1")
    assert a0[1] == a1[1]
    assert a1[0]["content"].startswith(a0[0]["content"])
    with pytest.raises(ValueError):
        architect_messages(case, "A3")
