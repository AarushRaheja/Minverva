"""A static, local human-review packet. It never runs the candidate application."""
import html
import json
import zipfile
from pathlib import Path

from frontendslm.io import sha256, write_json

ROOT = Path(__file__).resolve().parents[1]


def main():
    directory = ROOT / 'artifacts/original-review-pilot-v1'
    summary = json.loads((directory / 'summary.json').read_text())
    provenance = json.loads((directory / 'provenance.json').read_text())
    cards = []
    annotations = []
    for candidate in summary['candidates']:
        name = candidate['variant']
        manifest = json.loads((directory / name / 'source.json').read_text())
        with zipfile.ZipFile(directory / f'{name}-source.zip', 'w', zipfile.ZIP_DEFLATED) as archive:
            for path in (ROOT / 'sandbox').rglob('*'):
                rel = path.relative_to(ROOT / 'sandbox')
                if path.is_file() and not set(rel.parts) & {'node_modules', 'dist'} and str(rel) not in manifest['files'] and str(rel) != 'evaluate.mjs':
                    archive.write(path, str(rel))
            for path, content in manifest['files'].items():
                archive.writestr(path, content)
            archive.write(directory / 'LICENSE', 'LICENSE')
            archive.writestr('REVIEW.txt', 'Original assistant-authored candidate. Human verification pending; not training eligible.\nThe interface is a local-state demonstration with no external notification service.\nInspect source before running. In an isolated environment: npm ci --ignore-scripts, npm run build, npm run preview.\n')
        failed = [c['id'] for c in candidate['measured_checks'] if c['status'] == 'fail']
        expected = {'working': [], 'missing-save': ['interaction'], 'low-contrast': ['accessibility'],
                    'mobile-overflow': ['overflow']}[name]
        annotations.append({'variant': name, 'intended_failure_groups': expected, 'observed_failure_groups': failed,
            'controlled_mutation_verified': set(expected) == set(failed),
            'candidate_role': 'architect-positive-candidate' if name == 'working' else 'critic-negative-candidate',
            'human_verified': False, 'training_eligible': False})
        status = 'All measured checks pass' if candidate['audit']['audit_pass'] else 'Measured failure: ' + ', '.join(failed)
        cards.append(f'<section class="variant"><h3>{html.escape(name.replace("-", " ").title())}</h3><p>{html.escape(status)}</p><a href="{name}/render/desktop.png">Desktop screenshot</a> · <a href="{name}/render/mobile.png">Mobile screenshot</a> · <a href="{name}/render/mobile-after.png">Mobile after interaction</a> · <a href="{name}/render/evidence.json">Raw measurements</a> · <a href="{name}-source.zip">Source ZIP</a></section>')
    page = '''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Original UI review pilot</title><style>
*{box-sizing:border-box}body{margin:0;background:#f6f7f9;color:#172033;font:16px/1.6 system-ui,sans-serif}main{max-width:1160px;margin:auto;padding:36px 24px}h1{font-size:38px;letter-spacing:-.035em;line-height:1.15}h2{font-size:23px;margin-top:32px}p{max-width:78ch;color:#42516a}a{color:#4338ca}header{margin-bottom:28px}.tag{font-size:12px;letter-spacing:.12em;text-transform:uppercase;color:#4338ca;font-weight:650}.previews{display:grid;grid-template-columns:minmax(0,1fr) 230px;gap:18px;align-items:start}.previews img{width:100%;border:1px solid #d7dfeb;border-radius:10px;background:white}.panel,.variant{padding:24px;border:1px solid #d7dfeb;border-radius:12px;background:white;margin-top:18px}.notice{padding:14px 18px;background:#eef2ff;border-radius:8px;color:#312e81}.formgrid{display:grid;grid-template-columns:1fr 1fr;gap:18px}label{display:block;font-size:14px;font-weight:600;margin-bottom:6px}input,textarea,select{width:100%;padding:12px;border:1px solid #aab8cc;border-radius:7px;background:white;color:#172033;font:inherit}textarea{min-height:105px}.wide{grid-column:1/-1}button{background:#4338ca;color:white;border:0;padding:13px 20px;border-radius:8px;font:600 14px system-ui;cursor:pointer}button:hover{background:#3730a3}:focus-visible{outline:3px solid #6366f1;outline-offset:3px}small{font-size:13px;color:#53627b}details{margin:24px 0}summary{cursor:pointer;font-weight:600}#export-status{color:#166534}.variants{display:grid;grid-template-columns:1fr 1fr;gap:16px}.variant p{font-size:14px}.variant a{font-size:13px}@media(max-width:700px){main{padding:24px 16px}.previews,.formgrid,.variants{grid-template-columns:1fr}.previews a:last-child{max-width:260px}.wide{grid-column:auto}h1{font-size:30px}}
</style></head><body><main><header><p class="tag">FrontEndSLM · original review pilot</p><h1>Notifications, with room for focus.</h1><p>One original assistant-authored interface and three controlled defects. The working version passed its Modal browser audit. Human design preference and manual usability remain unreviewed.</p><p class="notice">This page shows screenshots and measurements. It does not run the candidate UI. Every candidate is excluded from training pending independent verification.</p></header>
<div class="previews"><a href="working/render/desktop.png"><img src="working/render/desktop.png" alt="Desktop view of the original notification preferences interface"></a><a href="working/render/mobile.png"><img src="working/render/mobile.png" alt="Mobile view of the original notification preferences interface"></a></div>
<section class="panel"><h2 style="margin-top:0">Your first impression</h2><p>Describe what you see in your own words before opening the intended design direction below. Rate only what you have actually inspected.</p><form id="review-form"><div class="formgrid">
<div class="wide"><label for="descriptors">Which three words best describe this design?</label><input id="descriptors" name="descriptors" required placeholder="Your own words, separated by commas"></div>
<div><label for="visual">Visual quality</label><select id="visual" name="visual" required><option value="">Choose a rating</option><option value="1">1 — difficult to follow</option><option value="2">2 — rough or inconsistent</option><option value="3">3 — clear, but ordinary</option><option value="4">4 — coherent and polished</option><option value="5">5 — exceptional and well fitted</option></select></div>
<div><label for="clarity">Is the main action clear?</label><select id="clarity" name="clarity" required><option value="">Choose a response</option><option value="clear">Clear</option><option value="partly">Partly clear</option><option value="unclear">Unclear</option></select></div>
<div class="wide"><label for="action">What would you do first on this screen?</label><input id="action" name="action" required></div>
<div><label for="functionality">Have you personally tried the interactions?</label><select id="functionality" name="functionality"><option value="not_tested">Not personally tested</option><option value="passed">Tried them; they worked as expected</option><option value="needs_correction">Tried them; corrections are needed</option></select></div>
<div><label for="reviewer">Reviewer name or alias</label><input id="reviewer" name="reviewer" required autocomplete="off"></div>
<div class="wide"><label for="notes">What should change?</label><textarea id="notes" name="notes"></textarea></div>
</div><p><button type="submit">Download review JSON</button></p><small>Your answers stay in this page until you download them. Downloading a review does not approve training or send anything to a server.</small><p id="export-status" role="status"></p></form></section>
<details><summary>Intended task, design direction, and verification</summary><p>__BRIEF__</p><p>The measured workflow toggles both settings, changes the digest, verifies that unsaved changes do not alter saved values, saves, restores defaults, and exercises keyboard controls on desktop and mobile. Screenshots and overflow scans cover five viewport sizes; accessibility is also scanned during interaction states.</p><p><a href="working-source.zip">Inspect or download the working source</a> · <a href="working/render/evidence.json">Read exact browser evidence</a> · <a href="provenance.json">Provenance</a> · <a href="LICENSE">Repository license</a></p><p>To try the UI yourself, inspect the source ZIP and follow REVIEW.txt in an isolated environment. The automatic browser results do not replace your own usability assessment.</p></details>
<h2>Controlled variants</h2><p>The defects below are deliberate and separately verified. They are candidate material for reviewing grounded critiques, not acceptable Architect targets.</p><div class="variants">__CARDS__</div>
<script>
document.getElementById('review-form').addEventListener('submit', event => {
  event.preventDefault(); const data = Object.fromEntries(new FormData(event.target).entries());
  const review = {schema_version:'1.0',candidate_id:'original-notification-preferences/working',source_sha256:'__HASH__',reviewer_declared_by_user:data.reviewer,submitted_at:new Date().toISOString(),perceived_descriptors:data.descriptors.split(',').map(s=>s.trim()).filter(Boolean),visual_quality:Number(data.visual),primary_action_clarity:data.clarity,first_action:data.action,manual_functionality:data.functionality,notes:data.notes,status:'submitted_for_validation',training_eligible:false};
  const blob = new Blob([JSON.stringify(review,null,2)],{type:'application/json'}); const url=URL.createObjectURL(blob); const a=document.createElement('a'); a.href=url; a.download='frontendslm-original-ui-review.json'; a.click(); setTimeout(()=>URL.revokeObjectURL(url),1000);
  document.getElementById('export-status').textContent='Review exported. Training eligibility remains pending independent verification.';
});
</script></main></body></html>'''
    working = next(c for c in summary['candidates'] if c['variant'] == 'working')
    page = page.replace('__BRIEF__', html.escape(provenance['brief'])).replace('__CARDS__', ''.join(cards)).replace('__HASH__', working['source_sha256'])
    (directory / 'review.html').write_text(page)
    write_json(directory / 'candidate-annotations.json', annotations)
    write_json(directory / 'artifact-manifest.json', {'files': {str(p.relative_to(directory)): {
        'sha256': sha256(p.read_bytes()), 'bytes': p.stat().st_size} for p in sorted(directory.rglob('*'))
        if p.is_file() and p.name != 'artifact-manifest.json'}})
    print(directory / 'review.html')


if __name__ == '__main__':
    main()
