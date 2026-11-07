import json

import pytest

from frontendslm.lineage import read_verified_generation, source_generation


def save(path, content, case_id='case'):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({'baseline': 'A1', 'case_id': case_id,
                               'manifest': {'files': {'src/App.tsx': content}}}))


def test_explicit_round_never_substitutes_a_later_success(tmp_path):
    save(tmp_path / 'A1/case/generation.json', 'baseline')
    save(tmp_path / 'round-0/A1/case/generation.json', 'initial failure')
    save(tmp_path / 'round-1/A1/case/generation.json', 'later repair')
    assert read_verified_generation(tmp_path, source_generation(tmp_path, 'A1', 'case'))['manifest']['files']['src/App.tsx'] == 'baseline'
    provenance = source_generation(tmp_path, 'A1', 'case', 0)
    assert read_verified_generation(tmp_path, provenance)['manifest']['files']['src/App.tsx'] == 'initial failure'
    save(tmp_path / provenance['path'], 'changed source')
    with pytest.raises(ValueError, match='changed after preflight'):
        read_verified_generation(tmp_path, provenance)


def test_source_identity_missing_round_and_path_escape_fail_preflight(tmp_path):
    save(tmp_path / 'A1/case/generation.json', 'source', case_id='other')
    with pytest.raises(ValueError, match='identity'):
        source_generation(tmp_path, 'A1', 'case')
    with pytest.raises(FileNotFoundError):
        source_generation(tmp_path, 'A1', 'case', 0)
    with pytest.raises(ValueError):
        source_generation(tmp_path, '../A1', 'case')
    with pytest.raises(ValueError):
        read_verified_generation(tmp_path, {'path': '../outside.json', 'generation_sha256': 'wrong'})
