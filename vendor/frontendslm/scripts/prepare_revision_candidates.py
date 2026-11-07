"""Package original, measured repair examples for human review; never accept them for training."""
import difflib
import html
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from audit.scoring import audit_score
from frontendslm.evidence import measured_checks
from frontendslm.io import sha256, write_json

FAMILY = 'original-notification-preferences'


def read(path):
    return json.loads(path.read_text())


def main():
    source = ROOT / 'artifacts/original-review-pilot-v1'
    output = ROOT / 'artifacts/original-revision-candidates-v1'
    if output.exists():
        raise ValueError('Preserve the existing packet; use a new version for changes')
    original_manifest = read(source / 'artifact-manifest.json')['files']
    for name, entry in original_manifest.items():
        if sha256((source / name).read_bytes()) != entry['sha256']:
            raise ValueError(f'Original review artifact changed: {name}')
    case, provenance = read(source / 'case.json'), read(source / 'provenance.json')
    summary = {r['variant']: r for r in read(source / 'summary.json')['candidates']}
    reference = read(source / 'working/source.json')['files']['src/App.tsx']
    reference_evidence = read(source / 'working/render/evidence.json')
    if not audit_score(reference_evidence)['audit_pass']:
        raise ValueError('The proposed correction must pass its full saved audit')
    expected = {'missing-save': ['interaction'], 'low-contrast': ['accessibility'], 'mobile-overflow': ['overflow']}
    descriptions = {
        'missing-save': 'Restore the save handler so submitting draft preferences updates the saved state.',
        'low-contrast': 'Restore readable secondary text colors on the existing light surfaces.',
        'mobile-overflow': 'Remove the fixed 900px minimum width so the layout can fit narrow viewports.',
    }
    output.mkdir(parents=True)
    cards, candidates = [], []
    for variant, expected_failures in expected.items():
        before = read(source / variant / 'source.json')['files']['src/App.tsx']
        evidence = read(source / variant / 'render/evidence.json')
        checks = measured_checks(evidence, case['tests'])
        after_checks = measured_checks(reference_evidence, case['tests'])
        failed = [c['id'] for c in checks if c['status'] == 'fail']
        if failed != expected_failures or any(c['status'] == 'unknown' for c in checks):
            raise ValueError(f'Unexpected or incomplete measurements: {variant}')
        if before == reference or sha256(before.encode()) != summary[variant]['source_sha256']:
            raise ValueError(f'Source provenance does not match: {variant}')
        if sha256(reference.encode()) != summary['working']['source_sha256']:
            raise ValueError('Corrected source provenance does not match')
        references = [f'{variant}/source.json', f'{variant}/render/evidence.json',
                      f'{variant}/render/desktop.png', f'{variant}/render/mobile.png',
                      'working/source.json', 'working/render/evidence.json', 'working/render/desktop.png',
                      'working/render/mobile.png', 'case.json', 'provenance.json', 'LICENSE']
        bindings = {name: original_manifest[name]['sha256'] for name in references}
        delta = ''.join(difflib.unified_diff(before.splitlines(True), reference.splitlines(True),
                                            fromfile=f'{variant}/App.tsx', tofile='corrected/App.tsx', n=2))
        row = {'schema_version': '1.0', 'id': f'{FAMILY}/{variant}-repair', 'family_id': FAMILY,
               'task': 'REVISE', 'split': 'unassigned', 'status': 'candidate_pending_human_verification',
               'author': provenance['author'], 'model_generated': False, 'benchmark_derived': False,
               'input': {'brief': provenance['brief'], 'source': before, 'tests': case['tests'],
                         'measured_failures': [c for c in checks if c['status'] == 'fail'],
                         'proposed_repair': descriptions[variant]},
               'target': {'format': 'complete_corrected_App.tsx', 'source': reference, 'patch_for_review': delta},
               'verification': {'before_failed_groups': failed,
                                'after_group_statuses': {c['id']: c['status'] for c in after_checks},
                                'after_full_audit_pass': True,
                                'before_source_sha256': sha256(before.encode()),
                                'after_source_sha256': sha256(reference.encode()),
                                'evidence_origin': 'Saved isolated Modal browser audits; not a new model repair run'},
               'artifact_root': '../original-review-pilot-v1', 'artifact_sha256': bindings,
               'human_review': {'status': 'pending', 'reviewer': None, 'verified_claims': []},
               'training_eligible': False}
        candidates.append(row)
        write_json(output / f'{variant}.json', row)
        (output / f'{variant}.patch').write_text(delta)
        e = html.escape
        cards.append(f'''<section><h2>{e(variant.replace('-', ' ').title())}</h2>
<p>{e(descriptions[variant])}</p><p>Measured groups: <strong>{e(', '.join(failed))} failed → all passed</strong>.</p>
<div class="pair"><figure><a href="../original-review-pilot-v1/{variant}/render/mobile.png"><img src="../original-review-pilot-v1/{variant}/render/mobile.png" alt="Before repair, mobile"></a><figcaption>Before repair</figcaption></figure>
<figure><a href="../original-review-pilot-v1/working/render/mobile.png"><img src="../original-review-pilot-v1/working/render/mobile.png" alt="After repair, mobile"></a><figcaption>Original working reference</figcaption></figure></div>
<p><a href="{variant}.json">Complete candidate and exact evidence hashes</a> · <a href="../original-review-pilot-v1/{variant}/render/evidence.json">Before measurements</a> · <a href="../original-review-pilot-v1/working/render/evidence.json">After measurements</a></p>
<details><summary>Inspect the exact code change</summary><pre>{e(delta)}</pre></details></section>''')
    (output / 'candidates.jsonl').write_text(''.join(json.dumps(c) + '\n' for c in candidates))
    write_json(output / 'summary.json', {'candidate_count': len(candidates), 'independent_design_families': 1,
        'model_repairs': 0, 'human_reviews': 0, 'training_eligible': 0,
        'family_partition_rule': 'All variants and corrections must remain in the same future split.',
        'limitations': ['Controlled original mutations, not naturally occurring model errors.',
                        'Passing saved tests is not human verification or evidence of model learning.',
                        'The three candidates share one corrected source and are not independent designs.',
                        'Beauty and descriptor agreement remain unmeasured.']})
    (output / 'review.html').write_text('''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Original repair review candidates</title><style>
body{font:16px/1.6 system-ui;margin:0;background:#f6f7f9;color:#172033}main{max-width:1040px;margin:auto;padding:32px 20px}h1{line-height:1.15}section{padding:24px;margin:24px 0;background:white;border:1px solid #cbd5e1;border-radius:12px}.pair{display:flex;gap:20px;flex-wrap:wrap}figure{margin:0;max-width:230px}img{width:100%;border:1px solid #cbd5e1}pre{white-space:pre-wrap;overflow-wrap:anywhere;font-size:13px;background:#f1f5f9;padding:16px}a{color:#4338ca}summary{cursor:pointer}p{max-width:80ch}</style><main><h1>Three repairs, one original design family.</h1><p>Each controlled defect links to an original working reference and the saved Modal browser measurements. These are assistant-authored review candidates, not model-generated repairs or accepted training examples.</p><p><strong>Human verification is pending.</strong> Review the brief, source/render correspondence, measured behavior and proposed explanation before any dataset acceptance. Do not infer usability from screenshots alone. All variants must remain in one dataset split.</p><p><a href="../original-review-pilot-v1/review.html">Original design and preference review</a> · <a href="summary.json">Provenance and limits</a> · <a href="candidates.jsonl">Candidate records</a></p>''' + ''.join(cards) + '</main></html>')
    write_json(output / 'artifact-manifest.json', {'files': {str(p.relative_to(output)): {
        'sha256': sha256(p.read_bytes()), 'bytes': p.stat().st_size} for p in sorted(output.rglob('*'))
        if p.is_file() and p.name != 'artifact-manifest.json'}})
    print(f'Prepared {len(candidates)} unreviewed repair candidates, one family, zero training-eligible examples: {output}')


if __name__ == '__main__':
    main()
