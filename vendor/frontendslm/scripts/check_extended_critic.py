"""Require the critic to cover measured intermediate-state and interaction failures."""
import argparse
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import modal

import modal_app
from frontendslm.io import sha256, write_json

source = ROOT / 'artifacts/audit-faults-v1'
parser = argparse.ArgumentParser()
parser.add_argument('--run-id', required=True)
args = parser.parse_args()
run_id = args.run_id
if not run_id.replace('-', '').replace('_', '').isalnum():
    raise ValueError('Invalid direct run ID')
output = ROOT / 'artifacts' / run_id
if (output / 'summary.json').exists():
    raise ValueError('Preserve prior regression; use a unique run ID')
cases = []
for path in sorted(source.glob('A1/*/case.json')):
    case = json.loads(path.read_text())
    cases.append(case)
    shutil.copytree(path.parent / 'render', output / 'A1' / case['id'] / 'render', dirs_exist_ok=True)
write_json(output / 'run.json', {'source_run': source.name, 'case_ids': [c['id'] for c in cases],
    'purpose': 'Measured failures after intermediate interactions and failed requirements',
    'source_sha256': {str(p.relative_to(ROOT)): sha256(p.read_bytes()) for p in ROOT.glob('src/**/*.py')}})
with modal.enable_output(), modal_app.app.run():
    with modal_app.results.batch_upload(force=True) as batch:
        batch.put_directory(output, f'/{run_id}')
    rows = modal_app.critic_batch.remote(cases, ['A1'], modal_app.MODEL_LOCK, run_id)
for row in rows:
    write_json(output / 'A1' / row['case_id'] / 'critique.json', row)
    print(json.dumps({k: row[k] for k in ('case_id', 'schema_valid', 'measurement_validation', 'effective_verdict')}))
write_json(output / 'summary.json', {'passed': sum(r['schema_valid'] and r['measurement_validation']['valid'] for r in rows),
    'total': len(rows), 'raw_verdicts': {r['case_id']: r['critique']['verdict'] if r['critique'] else None for r in rows}})
assert all(r['schema_valid'] and r['measurement_validation']['valid'] and r['critique']['verdict'] == 'revise' for r in rows)
print('All 4 critic state/interaction regressions passed')
