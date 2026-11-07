"""Demonstrate that exact readout assertions reject a known substring false pass."""
import argparse
import json
import sys
from copy import deepcopy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import modal

import modal_app
from audit.cases import audit_case
from audit.scoring import audit_score
from frontendslm.io import sha256, write_json
from frontendslm.references import reference_manifest


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--run-id', required=True)
    args = parser.parse_args()
    if not args.run_id.replace('-', '').replace('_', '').isalnum():
        raise ValueError('Expected a direct run ID')
    output = ROOT / 'artifacts' / args.run_id
    if output.exists():
        raise ValueError('Preserve prior artifacts; choose a new run ID')
    strict = audit_case(next(c for c in modal_app.read_cases(10) if c['category'] == 'configuration'))
    legacy = deepcopy(strict)
    for test in legacy['tests']:
        for step in test['steps']:
            if step['action'] == 'expect_text_exact':
                step['action'] = 'expect_text'
    source = reference_manifest(strict)
    wrong = deepcopy(source)
    original = 'data-testid="quantity" role="status">{quantity}'
    assert original in wrong['files']['src/App.tsx']
    wrong['files']['src/App.tsx'] = wrong['files']['src/App.tsx'].replace(original,
        'data-testid="quantity" role="status">1{quantity}', 1)
    variants = [('valid-contains', legacy, source, True), ('valid-exact', strict, source, True),
                ('wrong-contains', legacy, wrong, True), ('wrong-exact', strict, wrong, False)]
    tracked = [Path(__file__), ROOT / 'audit/evaluate.mjs', ROOT / 'audit/cases.py', ROOT / 'audit/scoring.py',
               ROOT / 'modal_app.py', ROOT / 'src/frontendslm/references.py']
    write_json(output / 'run.json', {'run_id': args.run_id, 'audit_version': '2.1',
        'purpose': 'Show and close a substring-assertion false pass without changing historical runs.',
        'expected': {name: expected for name, _, _, expected in variants},
        'controlled_mutation': 'Prefix the displayed quantity with 1, producing 11, 12, 13 instead of 1, 2, 3.',
        'source_sha256': {str(p.relative_to(ROOT)): sha256(p.read_bytes()) for p in tracked},
        'candidate_authorship': 'Original assistant-authored harness reference and controlled mutation',
        'training_eligible': False})
    modal_app.render_image = modal_app.render_image.add_local_file(ROOT / 'audit/evaluate.mjs', '/work/evaluate.mjs', copy=True)
    rows = []
    with modal.enable_output(), modal_app.app.run():
        for name, case, manifest, expected in variants:
            write_json(output / name / 'case.json', case)
            write_json(output / name / 'fixture.json', manifest)
            evidence = modal_app.render_case(case, manifest, output / name / 'render')
            observations = [s['observation'] for t in evidence['tests'] for s in t['steps'] if 'observation' in s]
            row = {'variant': name, 'expected_audit_pass': expected, **audit_score(evidence),
                   'recorded_text_observations': len(observations), 'observations': observations}
            rows.append(row)
            print(json.dumps({k: v for k, v in row.items() if k != 'observations'}), flush=True)
        write_json(output / 'summary.json', {'rows': rows,
            'all_expectations_match': all(r['audit_pass'] == r['expected_audit_pass'] for r in rows)})
        with modal_app.results.batch_upload(force=True) as batch:
            batch.put_directory(output, f'/{args.run_id}')
    assert all(r['audit_pass'] == r['expected_audit_pass'] and r['recorded_text_observations'] for r in rows)
    print('Exact numeric audit regression completed', flush=True)


if __name__ == '__main__':
    main()
