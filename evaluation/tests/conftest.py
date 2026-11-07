import json
import sys

import pytest

from evaluation.benchmarks.task_registry import repo_tasks
from evaluation.core import Budget

BUDGET = Budget("t", 10, 30)
needs_sandbox = pytest.mark.skipif(sys.platform != "darwin", reason="uses sandbox-exec")


@pytest.fixture
def spec():
    return next(t for t in repo_tasks() if t.id == "adversarial-readme-injection")


class ScriptedChat:
    """A model that replays fixed replies."""

    def __init__(self, replies):
        self.replies = list(replies)

    def chat(self, messages, json_mode=True):
        return {"text": self.replies.pop(0) if self.replies else '{"tool": "finish"}', "tok_in": 10, "tok_out": 5}


def action(**kw):
    return json.dumps(kw)
