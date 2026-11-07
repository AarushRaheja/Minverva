"""Resolve immutable generation inputs without substituting later repair outcomes."""
import json
from pathlib import Path

from frontendslm.io import sha256


def source_generation(source: Path, baseline: str, case_id: str, round_number: int | None = None) -> dict:
    if any(not part or Path(part).name != part or part in {'.', '..'} for part in (baseline, case_id)):
        raise ValueError('Expected direct baseline and case identifiers')
    if round_number is not None and round_number not in range(4):
        raise ValueError('Expected source round 0 through 3')
    root = source if round_number is None else source / f'round-{round_number}'
    path = root / baseline / case_id / 'generation.json'
    if not path.resolve().is_relative_to(source.resolve()):
        raise ValueError('Source generation escapes its run')
    raw = path.read_bytes()
    row = json.loads(raw)
    if row.get('baseline') != baseline or row.get('case_id') != case_id:
        raise ValueError('Source generation identity does not match the selected candidate')
    content = ((row.get('manifest') or {}).get('files') or {}).get('src/App.tsx')
    return {'path': str(path.relative_to(source)), 'generation_sha256': sha256(raw),
            'source_sha256': sha256(content.encode()) if content is not None else None}


def read_verified_generation(source: Path, provenance: dict) -> dict:
    path = source / provenance['path']
    if not path.resolve().is_relative_to(source.resolve()):
        raise ValueError('Source generation escapes its run')
    raw = path.read_bytes()
    if sha256(raw) != provenance['generation_sha256']:
        raise ValueError('Source generation changed after preflight')
    return json.loads(raw)
