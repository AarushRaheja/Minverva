import json
from pathlib import Path

import pytest

from frontendslm.generation import component_manifest, split_thinking_tokens
from frontendslm.inference import architect_decoding_parameters
from frontendslm.repair import recover_repair_context


def test_token_boundary_separates_analysis_from_the_only_executable_answer():
    reasoning, answer = split_thinking_tokens([10, 11, 99, 20, 21], 99)
    assert reasoning == [10, 11] and answer == [20, 21]
    for malformed in ([10, 11], [10, 99], [10, 99, 20, 99, 21]):
        with pytest.raises(ValueError):
            split_thinking_tokens(malformed, 99)
    with pytest.raises(ValueError, match='incomplete source'):
        component_manifest('export default function App() { return null; }', truncated=True)


def test_thinking_profile_uses_bounded_sampling_and_rejects_incompatible_protocols():
    original = architect_decoding_parameters(repairing=True)
    assert original == {'max_new_tokens': 6144, 'do_sample': False, 'repetition_penalty': 1.05}
    parameters = architect_decoding_parameters(repairing=True, output_mode='thinking',
                                               repair_decoding='thinking-recommended')
    assert parameters == {'max_new_tokens': 16384, 'do_sample': True, 'temperature': 0.6,
                          'top_p': 0.95, 'top_k': 20, 'min_p': 0.0}
    for args in ({'output_mode': 'thinking'},
                 {'output_mode': 'thinking', 'patching': True, 'repair_decoding': 'thinking-recommended'},
                 {'repair_decoding': 'thinking-recommended'}, {'output_mode': 'unknown'}):
        with pytest.raises(ValueError):
            architect_decoding_parameters(**args)


def test_alternative_checkpoint_is_pinned_and_critic_is_unchanged():
    root = Path(__file__).resolve().parents[1]
    original = json.loads((root / 'configs/models.lock.json').read_text())
    alternate = json.loads((root / 'configs/models-thinking.lock.json').read_text())
    assert alternate['critic'] == original['critic']
    assert alternate['architect']['revision'] == '768f209d9ea81521153ed38c47d515654e938aea'
    assert alternate['architect']['model'] == 'Qwen/Qwen3-4B-Thinking-2507'
    assert alternate['architect']['trust_remote_code'] is False


def test_repair_never_treats_thinking_text_as_a_component():
    failed = {'manifest': None, 'output_protocol': 'thinking-component-v8', 'raw': 'Non-code analysis'}
    assert recover_repair_context(failed, {}, [])[0] == ''
    final = 'export default function App() { return <broken; }'
    assert recover_repair_context(failed | {'final_answer': final}, {}, [])[0] == final
    assert recover_repair_context(failed | {'repair_base_source': 'original source'}, {}, [])[0] == 'original source'
