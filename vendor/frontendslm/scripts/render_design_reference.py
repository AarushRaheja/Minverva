"""Render an original, assistant-authored craft reference; never count it as model output."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import modal

import modal_app
from audit.scoring import audit_score
from frontendslm.generation import component_manifest
from frontendslm.io import sha256, write_json


def main():
    source = (ROOT / 'design/composition-example.tsx').read_text()
    source = source.replace('<button onClick={() => setReviewed', '<button data-testid="review-toggle" onClick={() => setReviewed')
    source = source.replace("<span className={'rounded-full", "<span data-testid=\"review-state\" className={'rounded-full")
    source = source.replace('<button aria-expanded={expanded}', '<button data-testid="question-toggle" aria-expanded={expanded}')
    source = source.replace('<p id="open-question"', '<p data-testid="open-question" id="open-question"')
    case = {'id': 'composition-reference', 'tests': [{'id': 'reference-interactions', 'steps': [
        {'action': 'expect_text', 'test_id': 'review-state', 'value': 'Awaiting review'},
        {'action': 'click', 'test_id': 'review-toggle'},
        {'action': 'expect_text', 'test_id': 'review-state', 'value': 'Reviewed'},
        {'action': 'click', 'test_id': 'review-toggle'},
        {'action': 'expect_text', 'test_id': 'review-state', 'value': 'Awaiting review'},
        {'action': 'expect_hidden', 'test_id': 'open-question'},
        {'action': 'click', 'test_id': 'question-toggle'},
        {'action': 'expect_visible', 'test_id': 'open-question'},
        {'action': 'press', 'test_id': 'question-toggle', 'value': 'Enter'},
        {'action': 'expect_hidden', 'test_id': 'open-question'},
    ]}]}
    directory = ROOT / 'artifacts/design-composition-reference'
    if directory.exists():
        raise ValueError('Reference already rendered; preserve prior output')
    manifest = component_manifest(source)
    write_json(directory / 'provenance.json', {'author': 'Codex assistant', 'small_model_generated': False,
        'training_data': False, 'human_reviewed': False, 'purpose': 'Original prompt composition example',
        'source_sha256': sha256(source.encode()), 'case': case, 'manifest': manifest.model_dump()})
    modal_app.render_image = modal_app.render_image.add_local_file(ROOT / 'audit/evaluate.mjs', '/work/evaluate.mjs', copy=True)
    with modal.enable_output(), modal_app.app.run():
        evidence = modal_app.render_case(case, manifest.model_dump(), directory / 'render')
        write_json(directory / 'summary.json', audit_score(evidence))
        with modal_app.results.batch_upload(force=True) as batch:
            batch.put_directory(directory, '/design-composition-reference')


if __name__ == '__main__':
    main()
