"""Confirm the audit accepts a valid disabled boundary and rejects an inert control."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import modal

import modal_app
from audit.cases import audit_case
from audit.scoring import audit_score
from frontendslm.io import write_json
from frontendslm.references import reference_manifest

output = ROOT / 'artifacts/audit-boundaries-v2'
if (output / 'summary.json').exists():
    raise ValueError('Preserve completed boundary evidence')
case = audit_case(next(c for c in modal_app.read_cases(10) if c['category'] == 'configuration'))
modal_app.render_image = modal_app.render_image.add_local_file(ROOT / 'audit/evaluate.mjs', '/work/evaluate.mjs', copy=True)
rows = []
with modal.enable_output(), modal_app.app.run():
    for name, disabled, expected in [('valid_minimum', 'quantity===1', True), ('broken_decrement', 'true', False)]:
        manifest = reference_manifest(case)
        manifest['files']['src/App.tsx'] = manifest['files']['src/App.tsx'].replace('<button aria-label="Decrease quantity"', f'<button disabled={{{disabled}}} aria-label="Decrease quantity"')
        write_json(output / name / 'fixture.json', manifest)
        write_json(output / name / 'case.json', case)
        evidence = modal_app.render_case(case, manifest, output / name / 'render')
        row = {'fixture': name, 'expected_accept': expected, **audit_score(evidence)}
        rows.append(row)
        print(json.dumps(row), flush=True)
    write_json(output / 'summary.json', {'rows': rows})
    with modal_app.results.batch_upload(force=True) as batch:
        batch.put_directory(output, '/audit-boundaries-v2')
assert all(r['audit_pass'] == r['expected_accept'] and r['build_pass'] and r['complete_render'] for r in rows)
print('Boundary checks passed: valid disabled control accepted; inert decrement rejected')
