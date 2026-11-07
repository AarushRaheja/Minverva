import copy

from test_evidence import measured_fixture

from frontendslm.evidence import compact_evidence, critic_output_schema, validate_measured_critique
from frontendslm.schemas import Critique


def fixture():
    evidence = measured_fixture()
    evidence['views']['mobile']['dom_snapshot'] = '- paragraph: Quantity ranges from 1 to 2.'
    evidence['tests'][1]['steps'] = [
        {'action': 'click', 'test_id': 'plus', 'passed': True},
        {'action': 'expect_text', 'test_id': 'quantity', 'value': '3', 'passed': True},
        {'action': 'expect_text', 'test_id': 'quantity', 'value': '4', 'passed': False},
        {'action': 'expect_text', 'test_id': 'quantity', 'value': '5'},
    ]
    evidence['references'].append({'type': 'screenshot', 'ref': 'mobile'})
    return compact_evidence(evidence, explicit_content_review=True)


def contradiction():
    return {'schema_version': '1.0', 'verdict': 'revise', 'uncertainties': [],
            'content_reviews': [{'test_ref': 'click:mobile', 'screen_quote': 'Quantity ranges from 1 to 2.',
                                 'comparison': 'The passed quantity assertion contains 3, above the stated upper bound.',
                                 'status': 'contradicted'}],
            'summary': 'Correct the stale quantity instructions.', 'issues': [{
                'id': 'quantity-copy', 'category': 'content_consistency', 'severity': 'major', 'confidence': .9,
                'evidence': [{'type': 'screenshot', 'ref': 'mobile', 'region': [.1, .2, .8, .4]},
                             {'type': 'test', 'ref': 'click:mobile'}],
                'observation': 'Copy says 1 to 2; the quantity assertion containing 3 passed.',
                'recommendation': 'Remove the unsupported upper bound in helper copy.',
                'acceptance_test': 'Copy matches requirements; the full quantity workflow still passes.'}]}


def test_copy_comparison_has_literal_initial_text_and_only_executed_assertions():
    evidence = fixture()
    assert evidence['initial_screen_text']['mobile']['text'].endswith('1 to 2.')
    assert evidence['initial_screen_text']['mobile']['state'] == 'initial'
    assert len(evidence['passed_assertions']) == 1
    assertion = evidence['passed_assertions'][0]
    assert assertion['expected'] == '3'
    assert 'not an exact' in assertion['semantics']
    assert assertion['step_index'] == 1


def test_passing_assertion_can_support_stale_copy_but_not_broken_interaction():
    evidence = fixture()
    assert validate_measured_critique(Critique.model_validate(contradiction()), evidence)['valid']
    for category in ('interaction', 'accessibility', 'runtime', 'prompt_adherence'):
        data = contradiction()
        data['issues'][0]['category'] = category
        assert not validate_measured_critique(Critique.model_validate(data), evidence)['valid']
    data = contradiction()
    data['verdict'] = 'accept'
    assert not validate_measured_critique(Critique.model_validate(data), evidence)['valid']


def test_copy_claim_needs_both_visual_and_executed_assertion_references():
    evidence = fixture()
    for refs in ([contradiction()['issues'][0]['evidence'][0]],
                 [contradiction()['issues'][0]['evidence'][1]],
                 [contradiction()['issues'][0]['evidence'][0], {'type': 'test', 'ref': 'unexecuted'}]):
        data = contradiction()
        data['issues'][0]['evidence'] = refs
        assert not validate_measured_critique(Critique.model_validate(data), evidence)['valid']
    missing = copy.deepcopy(evidence)
    missing['passed_assertions'] = []
    assert not validate_measured_critique(Critique.model_validate(contradiction()), missing)['valid']
    schema = critic_output_schema(evidence)
    refs = schema['$defs']['Issue']['properties']['evidence']['items']['anyOf']
    assert any(r['properties']['ref'].get('const') == 'click:mobile' for r in refs)


def test_explicit_review_cannot_drop_a_workflow_invent_quotes_or_accept_a_contradiction():
    evidence = fixture()
    for change in ('missing', 'invented_quote', 'accept', 'missing_issue', 'unknown'):
        data = contradiction()
        if change == 'missing':
            data['content_reviews'] = []
        elif change == 'invented_quote':
            data['content_reviews'][0]['screen_quote'] = 'Maximum is ten'
        elif change == 'accept':
            data['verdict'] = 'accept'
        elif change == 'missing_issue':
            data['issues'] = []
        else:
            data['content_reviews'][0]['status'] = 'unknown'
        assert not validate_measured_critique(Critique.model_validate(data), evidence)['valid']
    schema = critic_output_schema(evidence)
    assert schema['properties']['content_reviews']['minItems'] == 1
    assert schema['properties']['content_reviews']['prefixItems'][0]['properties']['test_ref']['const'] == 'click:mobile'


def test_explicit_review_stays_opt_in_after_failed_model_regression():
    evidence = fixture()
    ordinary = Critique(schema_version='1.0', verdict='accept', issues=[], uncertainties=[], summary='No finding')
    assert not validate_measured_critique(ordinary, evidence)['valid']
    evidence['evidence_protocol'] = 'readable-copy-and-assertions-v1'
    assert validate_measured_critique(ordinary, evidence)['valid']
    assert 'content_reviews' not in critic_output_schema(evidence)['required']


def test_exact_assertion_keeps_observed_text_separate_from_expected_text():
    evidence = measured_fixture()
    evidence['tests'][1]['steps'] = [
        {'action': 'expect_text_exact', 'test_id': 'quantity', 'value': '3', 'passed': True,
         'observation': {'kind': 'text_content_after_assertion', 'values': ['3'], 'truncated': False}},
        {'action': 'expect_text_exact', 'test_id': 'quantity', 'value': '1', 'passed': False,
         'observation': {'kind': 'text_content_after_assertion', 'values': ['11'], 'truncated': False}},
    ]
    evidence['tests'][1]['passed'] = False
    compact = compact_evidence(evidence)
    assert len(compact['passed_assertions']) == 1
    assert compact['passed_assertions'][0]['observation']['values'] == ['3']
    assert 'equals' in compact['passed_assertions'][0]['semantics']
    interaction = next(c for c in compact['measured_checks'] if c['id'] == 'interaction')
    assert interaction['status'] == 'fail'
    assert interaction['details']['tests'][1]['steps'][1]['observation']['values'] == ['11']
