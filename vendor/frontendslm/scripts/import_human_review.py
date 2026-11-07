"""Import user-submitted feedback without rewriting historical experiment artifacts."""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from design.reviews import validate_submission
from frontendslm.io import sha256, write_json


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('submission', type=Path)
    parser.add_argument('--packet', type=Path, default=ROOT / 'artifacts/original-review-pilot-v1')
    args = parser.parse_args()
    raw = args.submission.read_bytes()
    record = validate_submission(raw, args.packet)
    target = ROOT / 'artifacts/human-reviews' / record['review_id']
    if target.exists():
        if (target / 'submitted.json').read_bytes() != raw or json.loads((target / 'validation.json').read_text()) != record:
            raise ValueError('Existing review differs; preserve its original record')
    else:
        target.mkdir(parents=True)
        (target / 'submitted.json').write_bytes(raw)
        write_json(target / 'validation.json', record)
        write_json(target / 'artifact-manifest.json', {'files': {p.name: {
            'sha256': sha256(p.read_bytes()), 'bytes': p.stat().st_size} for p in target.iterdir() if p.is_file()}})
    path = ROOT / 'design/preferences.json'
    preferences = json.loads(path.read_text())
    reviews = preferences.setdefault('human_visual_ratings', [])
    if not any(r.get('review_id') == record['review_id'] for r in reviews):
        review = record['review']
        reviews.append({k: review[k] for k in ('candidate_id', 'source_sha256', 'submitted_at',
            'perceived_descriptors', 'visual_quality', 'primary_action_clarity', 'manual_functionality', 'notes')} | {
            'review_id': record['review_id'], 'record': str((target / 'validation.json').relative_to(ROOT)),
            'scope': 'User perception of this original reference candidate only; no general model-quality claim.',
            'training_eligible': False})
        write_json(path, preferences)
    records = [json.loads(p.read_text()) for p in sorted(target.parent.glob('*/validation.json'))]
    write_json(target.parent / 'index.json', {
        'visual_review_records': len(records),
        'reviewed_source_versions': len({(r['review']['candidate_id'], r['review']['source_sha256']) for r in records}),
        'manual_functionality_review_records': sum(r['manual_functionality'] != 'not_tested' for r in records),
        'training_eligible': 0,
        'records': [{'review_id': r['review_id'], 'candidate_id': r['review']['candidate_id'],
                     'source_sha256': r['review']['source_sha256'], 'visual_quality': r['review']['visual_quality'],
                     'record': f"{r['review_id']}/validation.json"} for r in records]})
    print(f'Validated visual submission: {target}; training eligibility remains false.')


if __name__ == '__main__':
    main()
