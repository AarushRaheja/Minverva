import copy
import json
from pathlib import Path

import pytest

from frontendslm.evidence import compact_evidence, effective_verdict, validate_measured_critique
from frontendslm.generation import FIXED_CSS, component_manifest
from frontendslm.schemas import Critique


def measured_fixture():
    views = {v: {"text_length": 100, "horizontal_overflow": False, "accessibility": [], "broken_images": []}
             for v in ["desktop", "mobile", "tablet", "stress", "wide"]}
    for v in ("desktop", "mobile"):
        views[v].update(after_accessibility=[], after_overflow=False)
    return {"build": {"passed": True}, "views": views,
            "tests": [{"id": f"click:{v}", "passed": True} for v in ("desktop", "mobile")],
            "runtime_errors": [], "failed_requests": [],
            "references": [{"type": "accessibility", "ref": "mobile"}, {"type": "test", "ref": "click:mobile"}]}


def accept():
    return Critique(schema_version="1.0", verdict="accept", issues=[], uncertainties=[], summary="Checks pass")


def accessibility_issue():
    return {"id": "contrast", "category": "accessibility", "severity": "major", "confidence": 1,
            "evidence": [{"type": "accessibility", "ref": "mobile"}], "observation": "Measured contrast failure",
            "recommendation": "Increase contrast", "acceptance_test": "Axe contrast check passes after interaction"}


def test_post_interaction_failure_cannot_be_lost_or_accepted():
    evidence = measured_fixture()
    evidence["views"]["mobile"]["after_accessibility"] = [{"id": "color-contrast", "impact": "serious", "nodes": []}]
    compact = compact_evidence(evidence)
    assert compact["views"]["mobile"]["after_accessibility"]
    result = validate_measured_critique(accept(), compact)
    assert not result["valid"]
    assert result["required_failure_groups"] == ["accessibility"]
    assert not result["covered_failure_groups"]
    assert effective_verdict(accept(), compact["measured_checks"], result) == "revise"
    critique = accept().model_copy(update={"verdict": "revise"})
    critique = Critique.model_validate(critique.model_dump() | {"issues": [accessibility_issue()]})
    assert validate_measured_critique(critique, compact)["valid"]


def test_passing_test_cannot_be_cited_as_broken_behavior():
    compact = compact_evidence(measured_fixture())
    issue = accessibility_issue() | {"category": "interaction", "evidence": [{"type": "test", "ref": "click:mobile"}]}
    critique = Critique.model_validate(accept().model_dump() | {"verdict": "revise", "issues": [issue]})
    assert not validate_measured_critique(critique, compact)["valid"]


def test_missing_after_measurement_or_expected_test_is_unknown():
    evidence = measured_fixture()
    assert all(c["status"] == "pass" for c in compact_evidence(evidence)["measured_checks"])
    del evidence["views"]["mobile"]["after_accessibility"]
    compact = compact_evidence(evidence, [{"id": "different"}])
    checks = {c["id"]: c for c in compact["measured_checks"]}
    assert checks["accessibility"]["status"] == "unknown"
    assert checks["interaction"]["status"] == "unknown"
    assert not validate_measured_critique(accept(), compact)["valid"]
    assert effective_verdict(accept(), compact["measured_checks"], {"valid": True}) == "uncertain"


def test_incomplete_axe_is_not_a_confirmed_failure():
    evidence = measured_fixture()
    evidence["views"]["mobile"]["accessibility_incomplete"] = [{"id": "color-contrast", "impact": "serious"}]
    compact = compact_evidence(evidence)
    assert all(c["status"] == "pass" for c in compact["measured_checks"])
    assert validate_measured_critique(accept(), compact)["valid"]
    assert 'accessibility_incomplete' not in compact['views']['mobile']
    assert compact['manual_review_not_confirmed']['mobile'] == ['color-contrast']
    false_positive = Critique.model_validate(accept().model_dump() | {
        'verdict': 'revise', 'issues': [accessibility_issue()]})
    assert not validate_measured_critique(false_positive, compact)['valid']
    assert not validate_measured_critique(accept().model_copy(update={'verdict': 'revise'}), compact)['valid']


def test_failed_test_must_be_reported_with_failed_reference():
    evidence = measured_fixture()
    evidence["tests"][1]["passed"] = False
    compact = compact_evidence(evidence)
    issue = accessibility_issue() | {"category": "interaction", "evidence": [{"type": "test", "ref": "click:mobile"}]}
    critique = Critique.model_validate(accept().model_dump() | {"verdict": "revise", "issues": [issue]})
    assert validate_measured_critique(critique, compact)["valid"]
    changed = copy.deepcopy(critique.model_dump())
    changed["issues"][0]["evidence"][0]["ref"] = "click:desktop"
    assert not validate_measured_critique(Critique.model_validate(changed), compact)["valid"]


@pytest.mark.parametrize("raw", ['{"files":{}}', 'Here is code: export default () => null',
                                '```tsx\nexport default () => null\n```\nextra',
                                '```tsx\nexport default () => null\n```\n```css\nbody{}\n```'])
def test_component_contract_rejects_multiple_files_or_wrappers(raw):
    with pytest.raises(ValueError):
        component_manifest(raw)


def test_truncated_code_is_never_salvaged():
    source = 'export default function App() { return <main>Hello</main>; }'
    with pytest.raises(ValueError):
        component_manifest(source, truncated=True)
    manifest = component_manifest(f'```tsx\n{source}\n```')
    assert manifest.files["src/index.css"] == FIXED_CSS
    assert "@apply" not in FIXED_CSS
    assert manifest.files["src/App.tsx"].strip() == source


def test_original_missed_failures_are_exposed_if_artifacts_available():
    root = Path(__file__).resolve().parents[1] / 'artifacts/pilot-baseline-v1/A1'
    for case in ('catalog_05', 'collaboration_05'):
        path = root / case / 'render/evidence.json'
        if not path.exists():
            pytest.skip('Original private run artifacts not present in CI')
        compact = compact_evidence(json.loads(path.read_text()))
        result = validate_measured_critique(accept(), compact)
        assert result["required_failure_groups"] == ['accessibility']
        assert not result["valid"]


def test_intermediate_failures_reach_critic_with_exact_state_references():
    evidence = measured_fixture()
    evidence['audit_version'] = '2.0'
    evidence['tests'][1]['steps'] = [{'action': 'click', 'test_id': 'toggle', 'passed': True}]
    evidence['views']['mobile']['interaction_states'] = [
        {'ref': 'click:mobile:step-0', 'horizontal_overflow': True,
         'accessibility': [{'id': 'color-contrast', 'impact': 'serious', 'nodes': []}]}]
    evidence['references'] += [{'type': t, 'ref': 'click:mobile:step-0'} for t in ('accessibility', 'overflow')]
    compact = compact_evidence(evidence)
    failed = {c['id']: c for c in compact['measured_checks'] if c['status'] == 'fail'}
    assert set(failed) == {'accessibility', 'overflow'}
    assert failed['accessibility']['references'] == [{'type': 'accessibility', 'ref': 'click:mobile:step-0'}]
    assert not validate_measured_critique(accept(), compact)['valid']
    del evidence['views']['mobile']['interaction_states']
    compact = compact_evidence(evidence)
    assert {c['id'] for c in compact['measured_checks'] if c['status'] == 'unknown'} == {'accessibility', 'overflow'}


def test_decode_schema_requires_known_measured_findings_without_forcing_visual_acceptance():
    from frontendslm.evidence import critic_output_schema
    evidence = measured_fixture()
    schema = critic_output_schema(compact_evidence(evidence))
    assert set(schema['properties']['verdict']['enum']) == {'accept', 'revise', 'uncertain'}
    evidence['views']['mobile']['after_accessibility'] = [{'id': 'color-contrast', 'impact': 'serious'}]
    schema = critic_output_schema(compact_evidence(evidence))
    assert schema['properties']['verdict']['enum'] == ['revise']
    assert schema['properties']['issues']['minItems'] == 1
    issue = schema['properties']['issues']['prefixItems'][0]
    assert issue['properties']['id']['const'] == 'measured-accessibility'
    assert issue['properties']['evidence']['items']['properties']['ref']['enum'] == ['mobile']
    assert issue['properties']['category']['enum'] == ['accessibility', 'color']
