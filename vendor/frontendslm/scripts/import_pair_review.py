"""Import an actual submitted pair review without changing either frozen candidate."""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from design.pair_reviews import validate_pair_submission
from frontendslm.io import sha256, write_json


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('submission', type=Path)
    parser.add_argument('--packet', type=Path, default=ROOT / 'artifacts/model-visual-pair-v1')
    args = parser.parse_args()
    raw = args.submission.read_bytes()
    record = validate_pair_submission(raw, args.packet)
    target = ROOT / 'artifacts/human-pair-reviews' / record['review_id']
    if target.exists():
        if (target / 'submitted.json').read_bytes() != raw or json.loads((target / 'validation.json').read_text()) != record:
            raise ValueError('Existing review differs; preserve the original')
    else:
        target.mkdir(parents=True)
        (target / 'submitted.json').write_bytes(raw)
        write_json(target / 'validation.json', record)
        write_json(target / 'artifact-manifest.json', {'files': {p.name: {
            'sha256': sha256(p.read_bytes()), 'bytes': p.stat().st_size} for p in target.iterdir() if p.is_file()}})
    records = [json.loads(p.read_text()) for p in sorted(target.parent.glob('*/validation.json'))]
    write_json(target.parent / 'index.json', {'pair_review_records': len(records), 'training_eligible': 0,
        'records': [{'review_id': r['review_id'], 'pair_id': r['review']['pair_id'],
                     'preferred': r['review']['preferred'], 'record': f"{r['review_id']}/validation.json"} for r in records]})
    print(f'Validated screenshot preference: {target}; no training eligibility or manual task-completion claim.')


if __name__ == '__main__':
    main()
