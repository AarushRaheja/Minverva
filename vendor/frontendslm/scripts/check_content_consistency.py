"""Replay frozen evidence to evaluate optional copy/behavior findings without label injection."""
import argparse
import json
import shutil
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import modal

import modal_app
from frontendslm.io import sha256, write_json
from frontendslm.thinking import critic_decoding_parameters


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--run-id', required=True)
    parser.add_argument('--explicit-content-review', action='store_true')
    parser.add_argument('--critic-profile', choices=['instruct', 'thinking'], default='instruct')
    parser.add_argument('--prepare-models', action='store_true')
    args = parser.parse_args()
    if not args.run_id.replace('-', '').replace('_', '').isalnum():
        raise ValueError('Use a direct run ID')
    output = ROOT / 'artifacts' / args.run_id
    lock_path = ROOT / 'configs' / ('models-dual-thinking.lock.json' if args.critic_profile == 'thinking' else 'models.lock.json')
    model_lock = json.loads(lock_path.read_text())
    model_lock['critic']['explicit_content_review'] = args.explicit_content_review
    if output.exists():
        raise ValueError('Preserve previous results; choose a new run ID')
    source = ROOT / 'artifacts/thinking-repair-development-v1'
    selections = [
        ('repaired', 'round-1/A0/operations_01', 'control'),
        ('repaired', 'round-1/A0/configuration_02', 'content_contradiction'),
        ('repaired', 'round-1/A1/learning_01', 'control'),
        ('control', 'round-0/A1/planning_02', 'control'),
        ('control', 'round-0/A1/forms_03', 'control'),
        ('original', 'round-0/A0/configuration_02', 'measured_interaction_failure'),
    ]
    cases, provenance = {}, []
    for baseline, relative, expectation in selections:
        path = source / relative
        case = json.loads((path / 'case.json').read_text())
        cases[case['id']] = case
        target = output / baseline / case['id']
        shutil.copytree(path / 'render', target / 'render')
        for name in ('case.json', 'generation.json'):
            shutil.copy2(path / name, target / name)
        provenance.append({'candidate': f'{baseline}/{case["id"]}', 'source_path': str(path.relative_to(ROOT)),
            'expected_role': expectation, 'expectation_author': 'assistant development review; not human labeling',
            'source_files_sha256': {str(p.relative_to(path)): sha256(p.read_bytes())
                                    for p in sorted(path.rglob('*')) if p.is_file()}})
    files = list(ROOT.glob('src/**/*.py')) + [Path(__file__), ROOT / 'modal_app.py', lock_path]
    parameters = critic_decoding_parameters(model_lock['critic'].get('output_mode', 'json'))
    run = {'run_id': args.run_id, 'declared_at': datetime.now(UTC).isoformat(),
        'protocol': 'explicit-content-review-v2' if args.explicit_content_review else 'readable-copy-and-assertions-v1',
        'source_run': source.name,
        'model_lock': model_lock, 'gpu': 'L40S', 'critic_profile': args.critic_profile,
        'generation_parameters': parameters,
        'source_sha256': {str(p.relative_to(ROOT)): sha256(p.read_bytes()) for p in files},
        'hypothesis': 'A reasoning-capable 4B Critic can detect contradictions missed by the 4B Instruct checkpoint.',
        'changed': ['Selected Critic checkpoint, template, decoding and total token budget'],
        'unchanged': ['All source, screenshots, measured tests, required workflows and critic prompt constructor'],
        'success_gate': 'Detect the stale-copy contradiction, retain four controls, and cover the original measured failure.',
        'label_separation': 'Provenance expectations are scoring metadata only; never passed to critic_batch.',
        'limitations': ['Six reused development cases; no independent accuracy or human grounding estimate',
                       'Reference validation does not verify semantic truth',
                       'expect_text records substring success, not exact observed text'],
        'training_performed': False, 'candidates': provenance}
    write_json(output / 'run.json', run)
    write_json(output / 'cases.json', list(cases.values()))
    with modal.enable_output(), modal_app.app.run():
        if args.prepare_models:
            write_json(output / 'download.json', modal_app.download_models.remote({'critic': model_lock['critic']}))
        with modal_app.results.batch_upload(force=True) as batch:
            batch.put_directory(output, f'/{args.run_id}')
        rows = modal_app.critic_batch.remote(list(cases.values()), ['repaired', 'control', 'original'],
                                           model_lock, args.run_id)
        scored = []
        for row in rows:
            candidate = f'{row["baseline"]}/{row["case_id"]}'
            write_json(output / candidate / 'critique.json', row)
            role = next(p['expected_role'] for p in provenance if p['candidate'] == candidate)
            valid = bool(row['schema_valid'] and (row.get('measurement_validation') or {}).get('valid'))
            issues = (row.get('critique') or {}).get('issues', [])
            category = {'content_contradiction': 'content_consistency',
                        'measured_interaction_failure': 'interaction'}.get(role)
            matched = valid and (row['effective_verdict'] == 'accept' if role == 'control' else
                                 row['effective_verdict'] == 'revise' and any(
                                     i['category'] == category and i['severity'] in {'major', 'blocker'} for i in issues))
            scored.append({'candidate': candidate, 'role': role, 'schema_and_measurement_valid': valid,
                           'effective_verdict': row['effective_verdict'], 'expected_role_match': matched,
                           'semantic_correctness': 'Requires separate inspection; role match is not proof'})
            print(json.dumps(scored[-1]), flush=True)
        summary = {'run_id': args.run_id, 'total': len(rows), 'expected_role_matches': sum(r['expected_role_match'] for r in scored),
                   'schema_and_measurement_valid': sum(r['schema_and_measurement_valid'] for r in scored),
                   'candidates': scored, 'human_grounding_verified': None}
        write_json(output / 'summary.json', summary)
        with modal_app.results.batch_upload(force=True) as batch:
            batch.put_directory(output, f'/{args.run_id}')
    print('Completed critic evidence replay', flush=True)


if __name__ == '__main__':
    main()
