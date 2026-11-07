import json
from pathlib import Path

import pytest

from design.contracts import DesignIntent, validate_intent_provenance


def test_explicitly_undefined_descriptor_cannot_silently_become_a_default():
    path = Path(__file__).resolve().parents[1] / 'artifacts/design-intents-v3/unknown_descriptor/intent.json'
    if not path.exists():
        pytest.skip('Private diagnostic artifact is not present in CI')
    row = json.loads(path.read_text())
    intent = DesignIntent.model_validate(row['intent'])
    source = "Make it zorbly. That word is our team's private design descriptor; no definition is provided yet."
    assert not intent.unresolved_descriptors  # The original observed regression.
    assert 'clarification is required' in ' '.join(validate_intent_provenance(intent, source))
    clarified = intent.model_copy(update={'unresolved_descriptors': ['zorbly'],
        'clarifying_questions': ['What concrete qualities does zorbly describe?']})
    assert not validate_intent_provenance(clarified, source)
