"""Original review candidates and measured counterexamples; never auto-accept for training."""
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import modal

import modal_app
from audit.scoring import audit_score
from frontendslm.evidence import measured_checks
from frontendslm.generation import component_manifest
from frontendslm.io import sha256, write_json


def main():
    source = (ROOT / 'pilot/notification-preferences.tsx').read_text()
    directory = ROOT / 'artifacts/original-review-pilot-v1'
    if directory.exists():
        raise ValueError('Preserve prior review candidates; use a versioned directory for changes')
    def step(action, test_id, value=''):
        return {'action': action, 'test_id': test_id, 'value': value}
    case = {'id': 'original-notification-preferences', 'tests': [
        {'id': 'save-and-restore', 'steps': [
            step('expect_text', 'saved-email', 'On'), step('expect_text', 'saved-desktop', 'Off'),
            step('click', 'email-setting'), step('click', 'desktop-setting'), step('select', 'digest-setting', 'Weekly'),
            step('expect_text', 'draft-status', 'unsaved'), step('click', 'save-preferences'),
            step('expect_text', 'saved-email', 'Off'), step('expect_text', 'saved-desktop', 'On'),
            step('expect_text', 'saved-digest', 'Weekly'), step('expect_text', 'save-status', 'Preferences saved'),
            step('click', 'restore-defaults'), step('click', 'save-preferences'),
            step('expect_text', 'saved-email', 'On'), step('expect_text', 'saved-desktop', 'Off'),
            step('expect_text', 'saved-digest', 'Daily'),
        ]}, {'id': 'keyboard-and-unsaved-isolation', 'steps': [
            step('press', 'email-setting', 'Enter'), step('expect_attribute', 'email-setting', json.dumps({'name': 'aria-checked', 'value': 'false'})),
            step('expect_text', 'saved-email', 'On'), step('select', 'digest-setting', 'Never'),
            step('press', 'save-preferences', 'Enter'), step('expect_text', 'saved-email', 'Off'),
            step('expect_text', 'saved-digest', 'Never'),
        ]},
    ]}
    variants = {
        'working': source,
        'missing-save': source.replace('event.preventDefault(); save();', 'event.preventDefault();'),
        'low-contrast': source.replace('text-slate-600', 'text-slate-300'),
        'mobile-overflow': source.replace('className="mx-auto max-w-6xl px-5 py-10', 'className="min-w-[900px] mx-auto max-w-6xl px-5 py-10'),
    }
    if len({sha256(s.encode()) for s in variants.values()}) != len(variants):
        raise ValueError('A controlled mutation did not change the source')
    write_json(directory / 'case.json', case)
    write_json(directory / 'provenance.json', {'author': 'Codex assistant', 'source': 'pilot/notification-preferences.tsx',
        'small_model_generated': False, 'external_source_or_assets': [], 'repository_license': 'MIT; see included LICENSE',
        'benchmark_case': False, 'human_reviewed': False, 'training_eligible': False,
        'intended_descriptors': ['clean', 'calm', 'precise'], 'descriptor_labels_origin': 'candidate author, pending human verification',
        'brief': 'A local notifications preferences screen. Toggle email and desktop updates, choose Daily/Weekly/Never digest, save preferences, restore defaults, and show saved versus unsaved state. Clean, calm, precise product UI. No real notifications or backend.'})
    (directory / 'LICENSE').write_text((ROOT / 'LICENSE').read_text())
    modal_app.render_image = modal_app.render_image.add_local_file(ROOT / 'audit/evaluate.mjs', '/work/evaluate.mjs', copy=True)
    with modal.enable_output(), modal_app.app.run():
        def render(item):
            name, code = item
            path = directory / name
            manifest = component_manifest(code)
            write_json(path / 'source.json', manifest.model_dump())
            evidence = modal_app.render_case(case, manifest.model_dump(), path / 'render')
            result = {'variant': name, 'source_sha256': sha256(code.encode()), 'audit': audit_score(evidence),
                'measured_checks': measured_checks(evidence, case['tests']),
                'human_review': {'status': 'pending', 'reviewer': None, 'ratings': None}, 'training_eligible': False}
            write_json(path / 'review-candidate.json', result)
            print(json.dumps({'variant': name, 'audit_pass': result['audit']['audit_pass'],
                              'failed_groups': [c['id'] for c in result['measured_checks'] if c['status'] == 'fail']}), flush=True)
            return result
        with ThreadPoolExecutor(max_workers=2) as pool:
            rows = list(pool.map(render, variants.items()))
        write_json(directory / 'summary.json', {'candidates': rows, 'training_eligible': 0, 'human_reviews': 0})
        with modal_app.results.batch_upload(force=True) as batch:
            batch.put_directory(directory, '/original-review-pilot-v1')


if __name__ == '__main__':
    main()
