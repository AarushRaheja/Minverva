"""Append-only record of what an agent observably did, with secrets redacted."""

from __future__ import annotations

import json
import re
import time
from pathlib import Path

SECRET = re.compile(r"(sk-[A-Za-z0-9_-]{16,}|gh[pousr]_[A-Za-z0-9]{20,}|hf_[A-Za-z0-9]{20,}|AKIA[0-9A-Z]{16}"
                    r"|(?i:(?:api[_-]?key|token|secret|password)[\"']?\s*[:=]\s*[\"']?)[A-Za-z0-9_\-./+]{12,})")
MAX_TEXT = 6000


def redact(value):
    if isinstance(value, str):
        return SECRET.sub("[REDACTED]", value)[:MAX_TEXT]
    if isinstance(value, dict):
        return {k: redact(v) for k, v in value.items()}
    if isinstance(value, list):
        return [redact(v) for v in value]
    return value


class TrajectoryLogger:
    """Event types: model, tool_call, tool_result, edit, test_run, message, error."""

    def __init__(self, path: Path):
        self.path = Path(path)
        self.t0 = time.time()
        self.path.write_text("")

    def log(self, type_: str, **fields) -> None:
        with self.path.open("a") as f:
            f.write(json.dumps({"t": round(time.time() - self.t0, 3), "type": type_, **redact(fields)}) + "\n")


def load(path: Path) -> list[dict]:
    path = Path(path)
    return [json.loads(x) for x in path.read_text().splitlines() if x.strip()] if path.exists() else []
