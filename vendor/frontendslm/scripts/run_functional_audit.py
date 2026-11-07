"""Render existing generated candidates under extended requirement-derived tests."""
import argparse
import json
import shutil
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
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
    parser.add_argument('source_run')
    parser.add_argument('--run-id', required=True)
    parser.add_argument('--references', action='store_true')
    args = parser.parse_args()
    source = ROOT / 'artifacts' / args.source_run
    target = ROOT / 'artifacts' / args.run_id
    if source.parent != ROOT / 'artifacts' or target.parent != source.parent or target == source:
        raise ValueError('Use distinct direct run directories')
    if (target / 'summary.json').exists():
        raise ValueError('Audit already finished; choose a unique run ID')
    original_run = json.loads((source / 'run.json').read_text())
    all_cases = {c['id']: c for c in modal_app.read_cases(50)}
    cases = {i: audit_case(all_cases[i]) for i in original_run['case_ids']}
    image = modal_app.render_image.add_local_file(ROOT / 'audit/evaluate.mjs', '/work/evaluate.mjs', copy=True)
    modal_app.render_image = image
    write_json(target / 'run.json', {'run_id': args.run_id, 'source_run': args.source_run,
        'case_ids': list(cases), 'references_only': args.references, 'training_performed': False,
        'audit_harness_sha256': sha256((ROOT / 'audit/evaluate.mjs').read_bytes()),
        'audit_cases_sha256': sha256((ROOT / 'audit/cases.py').read_bytes()),
        'audit_scoring_sha256': sha256((ROOT / 'audit/scoring.py').read_bytes()),
        'source_run_sha256': sha256((source / 'run.json').read_bytes())})
    write_json(target / 'cases.json', list(cases.values()))
    for name in ['evaluate.mjs', 'cases.py', 'scoring.py']:
        shutil.copy2(ROOT / 'audit' / name, target / ('audit-' + name))
    rows = []
    with modal.enable_output(), modal_app.app.run():
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = {}
            for baseline in ['reference'] if args.references else original_run['baselines']:
                for case_id, case in cases.items():
                    directory = target / baseline / case_id
                    if args.references:
                        manifest = reference_manifest(case)
                    else:
                        generation = json.loads((source / baseline / case_id / 'generation.json').read_text())
                        manifest = generation.get('manifest')
                        write_json(directory / 'generation.json', generation)
                    if not manifest:
                        rows.append({'baseline': baseline, 'case_id': case_id, 'audit_pass': False, 'reason': 'invalid source'})
                        continue
                    write_json(directory / 'case.json', case)
                    futures[pool.submit(modal_app.render_case, case, manifest, directory / 'render')] = (baseline, case_id)
            for future in as_completed(futures):
                baseline, case_id = futures[future]
                evidence = future.result()
                row = {'baseline': baseline, 'case_id': case_id, **audit_score(evidence)}
                rows.append(row)
                print(json.dumps(row), flush=True)
        write_json(target / 'summary.json', {'run_id': args.run_id, 'passed': sum(r['audit_pass'] for r in rows),
            'total': len(rows), 'rows': sorted(rows, key=lambda r: (r['baseline'], r['case_id']))})
        with modal_app.results.batch_upload(force=True) as batch:
            batch.put_directory(target, f'/{args.run_id}')
    print(f"Functional audit: {sum(r['audit_pass'] for r in rows)}/{len(rows)}")
    if args.references and not all(r['audit_pass'] for r in rows):
        raise RuntimeError('Reference audit failed; inspect harness or fixtures before trusting candidate audit')


if __name__ == '__main__':
    main()
