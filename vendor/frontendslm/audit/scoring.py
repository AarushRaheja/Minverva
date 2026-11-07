"""Fail-closed functional audit score, separate from the frozen paired baseline."""
from frontendslm.report import score_evidence

STATE_CHANGES = {'click', 'click_if_enabled', 'fill', 'select', 'press'}


def audit_score(evidence):
    base = score_evidence(evidence)
    states = [s for v in evidence.get('views', {}).values() for s in v.get('interaction_states', [])]
    expected = {f"{test['id']}:step-{i}" for test in evidence.get('tests', [])
                for i, step in enumerate(test.get('steps', []))
                if step.get('passed') is True and step['action'] in STATE_CHANGES}
    complete = bool(expected) and expected == {s['ref'] for s in states} and all(
        isinstance(s.get('accessibility'), list) and isinstance(s.get('horizontal_overflow'), bool)
        and not s.get('harness_error') for s in states)
    state_a11y = complete and not any(a.get('impact') in {'serious', 'critical'}
                                     for s in states for a in s['accessibility'])
    state_overflow = complete and not any(s['horizontal_overflow'] for s in states)
    console = not evidence.get('console_errors')
    return base | {'intermediate_states': len(states), 'complete_state_measurements': complete,
                   'state_accessibility_pass': bool(state_a11y), 'state_overflow_pass': bool(state_overflow),
                   'no_console_errors': console,
                   'audit_pass': bool(base['release_eligible'] and complete and state_a11y and state_overflow and console)}
