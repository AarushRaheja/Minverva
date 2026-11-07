import json

import pytest

from design.reviews import validate_submission, visual_preferences
from frontendslm.io import sha256, write_json


@pytest.fixture
def review_packet(tmp_path):
    source = 'export default function App() { return null; }\n'
    write_json(tmp_path / 'case.json', {'id': 'synthetic-test-fixture'})
    write_json(tmp_path / 'summary.json', {'candidates': [{'variant': 'working'}]})
    write_json(tmp_path / 'working/source.json', {'files': {'src/App.tsx': source}})
    write_json(tmp_path / 'working/render/evidence.json', {'fixture_only': True})
    (tmp_path / 'review.html').write_text('Synthetic fixture, not a real review')
    for view in ('desktop', 'mobile'):
        (tmp_path / f'working/render/{view}.png').write_bytes(b'synthetic image bytes for hash verification')
    write_json(tmp_path / 'artifact-manifest.json', {'files': {
        str(p.relative_to(tmp_path)): {'sha256': sha256(p.read_bytes())}
        for p in tmp_path.rglob('*') if p.is_file()}})
    review = {'schema_version': '1.0', 'candidate_id': 'synthetic-test-fixture/working',
        'source_sha256': sha256(source.encode()), 'reviewer_declared_by_user': 'Synthetic test fixture',
        'submitted_at': '2026-11-07T14:28:58.674Z',
        'perceived_descriptors': ['Clean', 'Functional', 'Minimal', 'Plain'], 'visual_quality': 4,
        'primary_action_clarity': 'clear', 'first_action': 'Use the controls',
        'manual_functionality': 'not_tested', 'notes': 'Test-only text',
        'status': 'submitted_for_validation', 'training_eligible': False}
    return tmp_path, review


def test_import_preserves_four_descriptors_and_does_not_infer_functionality_or_training(review_packet):
    packet, review = review_packet
    result = validate_submission(json.dumps(review).encode(), packet)
    assert result['review']['perceived_descriptors'] == review['perceived_descriptors']
    assert result['manual_functionality'] == 'not_tested'
    assert result['review']['visual_quality'] == 4
    assert result['training_eligible'] is False
    assert result['source_implementation_human_verified'] is False


def test_stale_source_and_modified_screenshot_cannot_be_imported(review_packet):
    packet, review = review_packet
    with pytest.raises(ValueError, match='source checksum'):
        validate_submission(json.dumps(review | {'source_sha256': '0' * 64}).encode(), packet)
    (packet / 'working/render/mobile.png').write_bytes(b'Changed image')
    with pytest.raises(ValueError, match='artifact changed'):
        validate_submission(json.dumps(review).encode(), packet)


def test_wrong_candidate_and_invalid_review_claims_are_rejected(review_packet):
    packet, review = review_packet
    for change in ({'candidate_id': 'wrong/working'}, {'candidate_id': 'synthetic-test-fixture/../working'},
                   {'training_eligible': True}, {'visual_quality': True}, {'perceived_descriptors': [' ']}):
        with pytest.raises(ValueError):
            validate_submission(json.dumps(review | change).encode(), packet)
    write_json(packet / 'artifact-manifest.json', {'files': {}})
    with pytest.raises(ValueError, match='omits required'):
        validate_submission(json.dumps(review).encode(), packet)


def test_visual_judge_does_not_receive_human_labels_or_candidate_feedback():
    preferences = {'schema_version': '1.0', 'user_statement': 'Clean product UI',
        'functionality_required': True, 'human_visual_ratings': [{'visual_quality': 4, 'notes': 'Reviewer answer'}],
        'candidate_specific_feedback': 'A separate answer that should not leak'}
    assert visual_preferences(preferences) == {
        'schema_version': '1.0', 'user_statement': 'Clean product UI', 'functionality_required': True}
