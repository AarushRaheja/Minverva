"""Create a static two-design preference packet; never execute candidate code."""
import html
import json
import random
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from audit.scoring import audit_score
from frontendslm.io import sha256, write_json


def main():
    output = ROOT / 'artifacts/model-visual-pair-v1'
    if output.exists():
        raise ValueError('Preserve a published review packet')
    sources = [ROOT / 'artifacts/thinking-repair-development-v1/round-0/A1/forms_03',
               ROOT / 'artifacts/design-development-v6/round-2/A1/forms_03']
    random.Random(137).shuffle(sources)
    pair = {'pair_id': 'forms03-model-pair-v1', 'assignment_seed': 137,
            'review_mode': 'Initial screenshot preference; task completion is not observed.',
            'training_eligible': False, 'candidates': {}}
    cards, source_hashes, specs = [], {}, []
    for label, directory in zip(('A', 'B'), sources, strict=True):
        generation = json.loads((directory / 'generation.json').read_text())
        evidence = json.loads((directory / 'render/evidence.json').read_text())
        case = json.loads((directory / 'case.json').read_text())
        assert audit_score(evidence)['audit_pass']
        specs.append(case['spec'])
        target = output / label
        target.mkdir(parents=True)
        write_json(target / 'source.json', generation['manifest'])
        shutil.copy2(directory / 'render/evidence.json', target / 'evidence.json')
        for view in ('desktop', 'mobile'):
            shutil.copy2(directory / f'render/{view}.png', target / f'{view}.png')
        source_hashes[label] = sha256(generation['manifest']['files']['src/App.tsx'].encode())
        pair['candidates'][label] = {'source_path': str(directory.relative_to(ROOT)),
            'model': generation['model'], 'source_sha256': source_hashes[label],
            'evidence_sha256': sha256((target / 'evidence.json').read_bytes()),
            'historical_audit_version': evidence.get('audit_version'), 'historical_audit_pass': True,
            'candidate_authorship': '4B model-generated; no assistant source edits for this packet'}
        cards.append(f'''<section><h2>Design {label}</h2><div class="screens"><a href="{label}/desktop.png"><img src="{label}/desktop.png" alt="Design {label}, desktop"></a><a href="{label}/mobile.png"><img src="{label}/mobile.png" alt="Design {label}, mobile"></a></div>
<label for="words-{label}">What words describe design {label}?</label><input id="words-{label}" name="words-{label}" required placeholder="Your words, separated by commas">
<label for="rating-{label}">Visual quality (optional)</label><select id="rating-{label}" name="rating-{label}"><option value="">Skip</option>{''.join(f'<option value="{n}">{n} / 5</option>' for n in range(1, 6))}</select></section>''')
    assert specs[0] == specs[1], 'Preference comparison requires identical briefs'
    pair['brief'] = specs[0]
    write_json(output / 'pair.json', pair)
    page = '''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Volunteer signup — design comparison</title><style>
*{box-sizing:border-box}body{margin:0;background:#f6f7f9;color:#202736;font:16px/1.55 system-ui,sans-serif}main{max-width:1440px;margin:auto;padding:36px 24px}h1{font-size:36px;letter-spacing:-.035em;line-height:1.2}h2{font-size:22px}p{max-width:80ch;color:#526073}.pair{display:grid;grid-template-columns:1fr 1fr;gap:24px}section,.response{background:white;border:1px solid #d9dfe8;border-radius:12px;padding:22px;margin:20px 0}.screens{display:flex;gap:8px;align-items:flex-start;min-height:280px}.screens a:first-child{width:76%}.screens a:last-child{width:23%}.screens img{width:100%;border:1px solid #dce2ea;border-radius:4px}a{color:#304cc4}label{display:block;margin:18px 0 7px;font-size:14px;font-weight:600}input,select,textarea{width:100%;padding:12px;border:1px solid #9ba8bc;border-radius:7px;background:#fff;color:#202736;font:inherit}textarea{min-height:100px}.response{max-width:780px}button{background:#304cc4;color:white;border:0;padding:13px 18px;border-radius:8px;font:600 15px system-ui;cursor:pointer}:focus-visible{outline:3px solid #697de2;outline-offset:3px}small{color:#526073}details{margin-top:24px}#status{color:#155735}@media(max-width:800px){main{padding:24px 16px}.pair{grid-template-columns:1fr;gap:0}.screens{min-height:0}h1{font-size:29px}}
</style><main><h1>Two designs for volunteer signup</h1><p>Imagine you want to sign up as a volunteer using your name and email. Compare the desktop and mobile views below. Which design would you prefer to use, and why?</p><p>These are screenshots, so the form controls shown inside them do not run. Click an image to inspect it at full size. Record your first impressions before opening the technical details.</p>
<form id="review"><div class="pair">__CARDS__</div><div class="response"><h2>Your preference</h2><label for="preferred">Which design do you prefer?</label><select id="preferred" name="preferred" required><option value="">Choose</option><option value="A">Design A</option><option value="B">Design B</option><option value="no_preference">No preference / neither</option></select>
<label for="reason">What influenced your choice?</label><textarea id="reason" name="reason" required></textarea><label for="reviewer">Your name or alias</label><input id="reviewer" name="reviewer" required autocomplete="off"><p><button type="submit">Download my feedback</button></p><small>Nothing is sent to a server. This records screenshot impressions, not manual interaction testing.</small><p id="status" role="status"></p></div></form>
<details><summary>Task and technical details</summary><p>__BRIEF__</p><p>Both saved candidates passed their historical automated audits. This is a small visual preference pilot, not proof of general design quality. These evaluation examples remain excluded from training.</p><p><a href="pair.json">Source provenance</a> · <a href="A/evidence.json">Design A measurements</a> · <a href="B/evidence.json">Design B measurements</a></p></details></main><script>
const hashes=__HASHES__;
document.getElementById('review').addEventListener('submit',event=>{event.preventDefault();const data=Object.fromEntries(new FormData(event.target).entries());
const review={schema_version:'pair-1.0',pair_id:'forms03-model-pair-v1',reviewer_declared_by_user:data.reviewer,submitted_at:new Date().toISOString(),preferred:data.preferred,reason:data.reason,
impressions:['A','B'].map(label=>({label,source_sha256:hashes[label],perceived_descriptors:data['words-'+label].split(',').map(s=>s.trim()).filter(Boolean),visual_quality:data['rating-'+label]?Number(data['rating-'+label]):null})),manual_functionality:'not_tested',training_eligible:false};
const url=URL.createObjectURL(new Blob([JSON.stringify(review,null,2)],{type:'application/json'}));const a=document.createElement('a');a.href=url;a.download='frontendslm-model-visual-preference.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);document.getElementById('status').textContent='Feedback downloaded. It has not been sent or used for training.';});
</script></html>'''
    page = page.replace('__CARDS__', ''.join(cards)).replace('__BRIEF__', html.escape(specs[0]['user_goal']))
    page = page.replace('__HASHES__', json.dumps(source_hashes))
    (output / 'review.html').write_text(page)
    write_json(output / 'artifact-manifest.json', {'files': {str(p.relative_to(output)): {
        'sha256': sha256(p.read_bytes()), 'bytes': p.stat().st_size} for p in sorted(output.rglob('*')) if p.is_file()}})
    print(output / 'review.html')


if __name__ == '__main__':
    main()
