import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from test_contracts import cases
from test_evidence import measured_fixture

from audit.cases import audit_case
from audit.scoring import audit_score


def test_audit_adds_requirement_checks_without_changing_original_cases():
    original = cases()
    for case in original[:10]:
        extended = audit_case(case)
        assert len(extended['tests']) == len(case['tests']) + 1
        if case['spec']['interactions'][0]['id'] not in {'stepper', 'cart'}:
            assert extended['tests'][:-1] == case['tests']
        elif case['spec']['interactions'][0]['id'] == 'stepper':
            assert any(s['action'] == 'click_if_enabled' for s in extended['tests'][0]['steps'])
            assert all(s['action'] != 'click_if_enabled' for s in case['tests'][0]['steps'])
        assert extended['spec'] == case['spec']
    kinds = {c['spec']['interactions'][0]['id']: audit_case(c)['tests'][-1]['steps'] for c in original[:10]}
    assert any(s['value'] == 'Escape' for s in kinds['dialog'])
    assert any(s['action'] == 'expect_focused' for s in kinds['dialog'])
    assert any(s['action'] == 'expect_palette_changed' for s in kinds['theme'])
    for kind, target in [('stepper', 'quantity'), ('cart', 'cart-count')]:
        assert all(s['action'] == 'expect_text_exact' for s in kinds[kind] if s['test_id'] == target)


def test_missing_state_scan_and_intermediate_failure_block_audit():
    evidence = measured_fixture()
    for test in evidence['tests']:
        test['steps'] = [{'action': 'click', 'test_id': 'toggle', 'passed': True}]
    assert not audit_score(evidence)['audit_pass']
    for view in ['desktop', 'mobile']:
        evidence['views'][view]['interaction_states'] = [
            {'ref': f'click:{view}:step-0', 'accessibility': [], 'horizontal_overflow': False}]
    assert audit_score(evidence)['audit_pass']
    evidence['views']['mobile']['interaction_states'][0]['accessibility'] = [{'impact': 'serious'}]
    assert not audit_score(evidence)['audit_pass']
    evidence['views']['mobile']['interaction_states'][0]['accessibility'] = []
    evidence['console_errors'] = [{'message': 'Uncaught error'}]
    assert not audit_score(evidence)['audit_pass']
