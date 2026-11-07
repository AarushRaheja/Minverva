"""Deterministic offline client for tests and dry runs. No network.

Responses are keyed by the requested schema's title (the Pydantic class name). Each
key maps to a list of replies consumed in order, and the last reply repeats. A reply
is a dict (dumped to JSON) or a raw string (to simulate malformed output).
"""

from __future__ import annotations

import json
import threading

from slm.llm.base import LLMClient, RawResponse
from slm.trace import Tracer

Reply = dict | str


class FakeClient(LLMClient):
    def __init__(
        self,
        responses: dict[str, list[Reply]] | None = None,
        tracer: Tracer | None = None,
        model: str = "fake",
    ):
        super().__init__(model, tracer)
        self.responses = {**DEFAULT_RESPONSES, **(responses or {})}
        self._cursor: dict[str, int] = {}
        self._lock = threading.Lock()  # acomplete runs _raw in worker threads
        self.calls: list[tuple[str, str, str]] = []  # (schema title, system, user)

    def _raw(self, system: str, user: str, json_schema: dict) -> RawResponse:
        title = json_schema.get("title", "")
        if title not in self.responses:
            raise KeyError(f"FakeClient has no response for schema {title!r}")
        with self._lock:
            self.calls.append((title, system, user))
            replies = self.responses[title]
            i = self._cursor.get(title, 0)
            self._cursor[title] = i + 1
        reply = replies[min(i, len(replies) - 1)]
        text = reply if isinstance(reply, str) else json.dumps(reply)
        return RawResponse(text, _tokens(system + user), _tokens(text))


def _tokens(text: str) -> int:
    return max(1, len(text) // 4)  # rough chars-per-token estimate


DEFAULT_RESPONSES: dict[str, list[Reply]] = {
    # A minimal but valid split: every one of the four specialists gets work.
    "ProjectPlan": [{
        "name": "notes app",
        "stack": "fastapi+react+postgres",
        "tasks": [
            {"id": "t1", "domain": "database", "kind": "schema", "target": "users",
             "detail": "users table for accounts", "deps": []},
            {"id": "t2", "domain": "database", "kind": "schema", "target": "note",
             "detail": "notes table", "deps": []},
            {"id": "t3", "domain": "auth", "kind": "session", "target": "session",
             "detail": "cookie sessions over the users table", "deps": ["t1"]},
            {"id": "t4", "domain": "network", "kind": "rest", "target": "note",
             "detail": "notes REST endpoints behind sessions", "deps": ["t2", "t3"]},
            {"id": "t5", "domain": "frontend", "kind": "page", "target": "note",
             "detail": "notes page fetching the collection", "deps": ["t4"]},
        ],
    }],
    "Artifact": [{
        "files": [{"path": "src/database/users.sql",
                   "content": "CREATE TABLE users (\n  id BIGSERIAL PRIMARY KEY\n);\n"}],
        "summary": "fake artifact",
    }],
    "MonolithProject": [{
        "files": [{"path": "src/database/users.sql",
                   "content": "CREATE TABLE users (\n  id BIGSERIAL PRIMARY KEY\n);\n"}],
        "summary": "fake monolith",
    }],
}
