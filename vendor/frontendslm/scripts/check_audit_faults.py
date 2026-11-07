"""Verify that expanded checks detect requirement violations missed by final-state-only tests."""
import json
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

output = ROOT / 'artifacts/audit-faults-v1'
if (output / 'summary.json').exists():
    raise ValueError('Fault test already finished; preserve existing observations')
modal_app.render_image = modal_app.render_image.add_local_file(ROOT / 'audit/evaluate.mjs', '/work/evaluate.mjs', copy=True)
cases = {c['category']: audit_case(c) for c in modal_app.read_cases(10)}
jobs = []
for name, category, replacements, failure_metric in [
    ('dialog_escape', 'collaboration', [('<dialog ref={dialog}', '<dialog onCancel={e=>e.preventDefault()} ref={dialog}')], 'interaction_pass'),
    ('theme_palette', 'editorial', [("active?'#101f31':'#fff'", "'#fff'"), ("active?'#fff':'#172538'", "'#172538'")], 'interaction_pass'),
    ('theme_contrast', 'editorial', [("active?'#101f31':'#fff'", "'#fff'"), ("active?'#fff':'#172538'", "active?'#f3f4f6':'#172538'")], 'state_accessibility_pass'),
    ('theme_overflow', 'editorial', [('padding:24}', "padding:24,width:active?'2500px':'auto'}")], 'state_overflow_pass'),
]:
    case = cases[category] | {'id': name}
    manifest = reference_manifest(case)
    for before, after in replacements:
        if before not in manifest['files']['src/App.tsx']:
            raise ValueError(f'Fault injection target missing: {before}')
        manifest['files']['src/App.tsx'] = manifest['files']['src/App.tsx'].replace(before, after)
    write_json(output / 'A1' / name / 'case.json', case)
    write_json(output / 'A1' / name / 'fixture.json', manifest)
    jobs.append((name, case, manifest, failure_metric))
write_json(output / 'run.json', {'kind': 'deliberately broken reference fixtures',
    'audit_harness_sha256': sha256((ROOT / 'audit/evaluate.mjs').read_bytes()),
    'cases': [j[0] for j in jobs], 'training_performed': False})
rows = []
with modal.enable_output(), modal_app.app.run():
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = {pool.submit(modal_app.render_case, case, manifest, output / 'A1' / name / 'render'): (name, failure)
                   for name, case, manifest, failure in jobs}
        for future in as_completed(futures):
            name, failure = futures[future]
            evidence = future.result()
            score = audit_score(evidence)
            row = {'fixture': name, 'expected_failed_metric': failure, 'detected': not score[failure], **score}
            rows.append(row)
            print(json.dumps(row), flush=True)
    write_json(output / 'summary.json', {'rows': rows})
    with modal_app.results.batch_upload(force=True) as batch:
        batch.put_directory(output, '/audit-faults-v1')
assert all(r['detected'] and not r['audit_pass'] and r['build_pass'] and r['complete_render'] for r in rows)
print('All 4 injected functional/state faults detected')
