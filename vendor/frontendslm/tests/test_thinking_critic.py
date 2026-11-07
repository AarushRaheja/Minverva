import json
from pathlib import Path

import pytest

from frontendslm.thinking import AfterThinkingLogitsProcessor, critic_decoding_parameters


class Token:
    def __init__(self, value):
        self.value = value

    def item(self):
        return self.value


class Sequence:
    def __init__(self, tokens, batch=1):
        self.tokens = tokens
        self.shape = (batch, len(tokens))

    def __getitem__(self, position):
        return Token(self.tokens[position[1]])


def test_schema_waits_for_generated_boundary_not_one_in_prompt_and_stays_active():
    calls = []

    def delegate(ids, scores):
        calls.append(ids.tokens[-1])
        return 'masked'

    route = AfterThinkingLogitsProcessor(delegate, prompt_length=2, end_thinking_id=99)
    assert route(Sequence([1, 99]), 'unmasked') == 'unmasked'
    assert route(Sequence([1, 99, 3]), 'unmasked') == 'unmasked'
    assert not calls
    assert route(Sequence([1, 99, 3, 99]), 'unmasked') == 'masked'
    assert route(Sequence([1, 99, 3, 99, 4]), 'unmasked') == 'masked'
    assert calls == [99, 4]
    with pytest.raises(ValueError, match='one sequence'):
        route(Sequence([1, 2], batch=2), 'unmasked')


def test_critic_profile_preserves_default_and_pins_alternative():
    assert critic_decoding_parameters() == {'max_new_tokens': 2500, 'do_sample': False}
    assert critic_decoding_parameters('thinking') == {
        'max_new_tokens': 16384, 'do_sample': True, 'temperature': 1.0,
        'top_p': .95, 'top_k': 20, 'repetition_penalty': 1.0}
    with pytest.raises(ValueError):
        critic_decoding_parameters('unknown')
    root = Path(__file__).resolve().parents[1]
    lock = json.loads((root / 'configs/models-dual-thinking.lock.json').read_text())
    previous = json.loads((root / 'configs/models-thinking.lock.json').read_text())
    assert lock['architect'] == previous['architect']
    assert lock['critic']['model'] == 'Qwen/Qwen3-VL-4B-Thinking'
    assert lock['critic']['revision'] == '1de27d8c51f12e819435303b9e84c4e25ba8401e'
    assert lock['critic']['trust_remote_code'] is False
