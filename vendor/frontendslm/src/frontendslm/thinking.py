"""Single-sequence token-boundary routing for reasoning followed by constrained JSON."""


class AfterThinkingLogitsProcessor:
    """Leave reasoning unrestricted, then activate a fresh XGrammar processor.

    XGrammar 0.2.8 skips accepting the previous token on its first call. This
    prevents the thinking delimiter from being fed into the JSON grammar.
    Never reuse the wrapper or its delegate between model.generate calls.
    """

    def __init__(self, delegate, *, prompt_length: int, end_thinking_id: int):
        self.delegate = delegate
        self.prompt_length = prompt_length
        self.end_thinking_id = end_thinking_id
        self.active = False

    def __call__(self, input_ids, scores):
        if input_ids.shape[0] != 1:
            raise ValueError('Thinking grammar routing supports one sequence only')
        if not self.active and input_ids.shape[1] > self.prompt_length:
            self.active = input_ids[0, -1].item() == self.end_thinking_id
        return self.delegate(input_ids, scores) if self.active else scores


def critic_decoding_parameters(output_mode: str = 'json') -> dict:
    if output_mode == 'json':
        return {'max_new_tokens': 2500, 'do_sample': False}
    if output_mode != 'thinking':
        raise ValueError('Unknown Critic output mode')
    # Bounded development budget including reasoning and answer; below the
    # vendor VL recommendation of 40,960. Exhaustion remains an invalid output.
    return {'max_new_tokens': 16384, 'do_sample': True, 'temperature': 1.0,
            'top_p': 0.95, 'top_k': 20, 'repetition_penalty': 1.0}
