"""Traceable design intent and blinded screenshot evaluation on Modal."""
import argparse
import json
import re
import shutil
import sys
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import modal

import modal_app
from design.modal_app import app, intent_batch, visual_batch
from frontendslm.io import sha256, write_json


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--mode', choices=['intent', 'visual'], required=True)
    parser.add_argument('--input', type=Path, required=True)
    parser.add_argument('--run-id', required=True)
    args = parser.parse_args()
    if not re.fullmatch(r'[a-zA-Z0-9_-]{1,80}', args.run_id):
        raise ValueError('Invalid run ID')
    jobs = json.loads(args.input.read_text())
    if not 1 <= len(jobs) <= 20:
        raise ValueError('Keep batches bounded to 1–20 jobs')
    ids = [j['id' if args.mode == 'intent' else 'blind_id'] for j in jobs]
    if len(set(ids)) != len(ids) or any(not re.fullmatch(r'[a-zA-Z0-9_-]{1,80}', i) for i in ids):
        raise ValueError('Unique safe job IDs required')
    if args.mode == 'visual':
        for job in jobs:
            if not 1 <= len(job['images']) <= 2:
                raise ValueError('Supply one or two screenshots per review')
            for name in job['images'].values():
                path = PurePosixPath(name)
                if path.is_absolute() or '..' in path.parts or path.suffix != '.png':
                    raise ValueError('Screenshot must be a relative PNG path in the results volume')
                if not (ROOT / 'artifacts' / name).is_file():
                    raise ValueError(f'Missing local provenance for screenshot: {name}')
    directory = ROOT / 'artifacts' / args.run_id
    if directory.exists():
        raise ValueError('Use a new run ID; preserve previous attempts')
    preferences = json.loads((ROOT / 'design/preferences.json').read_text())
    rubric = json.loads((ROOT / 'design/rubric.json').read_text())
    hashes = {str(p.relative_to(ROOT)): sha256(p.read_bytes()) for p in
              [*ROOT.glob('design/*.*'), *ROOT.glob('src/**/*.py'), ROOT / 'modal_app.py', Path(__file__)] if p.is_file()}
    write_json(directory / 'run.json', {'mode': args.mode, 'jobs': ids, 'source_sha256': hashes,
        'model_lock': modal_app.MODEL_LOCK, 'input_sha256': sha256(args.input.read_bytes()),
        'training_performed': False, 'human_preference_measured': False})
    write_json(directory / 'jobs.json', jobs)
    for name in hashes:
        target = directory / 'pipeline-source' / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / name, target)
    with modal.enable_output(), app.run():
        if args.mode == 'intent':
            rows = intent_batch.remote(jobs, preferences, modal_app.MODEL_LOCK['architect'], args.run_id)
        else:
            rows = visual_batch.remote(jobs, rubric, preferences, modal_app.MODEL_LOCK['critic'], args.run_id)
        for row in rows:
            write_json(directory / row.get('id', row.get('blind_id')) / f'{args.mode}.json', row)
        write_json(directory / 'summary.json', {'mode': args.mode, 'total': len(rows),
            'schema_valid': sum(r['schema_valid'] for r in rows), 'rows': rows})
        with modal_app.results.batch_upload(force=True) as batch:
            batch.put_directory(directory, f'/{args.run_id}')


if __name__ == '__main__':
    main()
