import pytest

from frontendslm.inference import architect_decoding_parameters
from frontendslm.repair import SourcePatch, apply_source_patch


def test_line_patch_preserves_other_source_and_rejects_out_of_bounds_or_overlapping_edits():
    source = 'export default function App() {\n  return <button disabled={true}>Add</button>;\n}'
    edit = {'start_line': 2, 'end_line': 2, 'replacement': '  return <button disabled={false}>Add</button>;', 'reason': 'Enable Add'}
    manifest = apply_source_patch(source, SourcePatch(edits=[edit]))
    assert manifest.files['src/App.tsx'] == source.replace('disabled={true}', 'disabled={false}') + '\n'
    for edits in [
        [edit | {'start_line': 4, 'end_line': 4}],
        [edit | {'start_line': 3, 'end_line': 2}],
        [edit | {'replacement': source.splitlines()[1]}],
        [edit, edit | {'replacement': ''}],
    ]:
        with pytest.raises(ValueError):
            apply_source_patch(source, SourcePatch(edits=edits))


def test_repair_sampling_does_not_change_initial_generation_or_structured_patch_defaults():
    initial = architect_decoding_parameters()
    assert architect_decoding_parameters(repair_decoding='qwen-recommended') == initial
    greedy = architect_decoding_parameters(repairing=True)
    sampled = architect_decoding_parameters(repairing=True, repair_decoding='qwen-recommended')
    assert not greedy['do_sample']
    assert sampled['do_sample'] and sampled['temperature'] == 0.7 and sampled['top_k'] == 20
    assert sampled['max_new_tokens'] == greedy['max_new_tokens'] == initial['max_new_tokens']
    assert sampled['repetition_penalty'] == greedy['repetition_penalty']
    with pytest.raises(ValueError):
        architect_decoding_parameters(repairing=True, patching=True, repair_decoding='qwen-recommended')
    with pytest.raises(ValueError):
        architect_decoding_parameters(repair_decoding='typo')
