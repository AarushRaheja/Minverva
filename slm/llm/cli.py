"""Hosted coding models through their own CLIs, using the login already on this machine (no API key).

Each call runs from an empty temp directory with tools off, so a model answers from the brief alone and
can't read this repo (which holds the gold templates). A failure of the service (login, rate limit,
timeout, a silent model fallback) raises BackendUnavailable: it says nothing about the model, so
it must not be scored as a loss. Text that fails validation is the model's own miss and stays in LLMClient.

Decoding can't be set to greedy from these CLIs, so unlike OllamaClient a repeat run may differ.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from slm.llm.base import LLMClient, RawResponse
from slm.llm.hosted import _system_with_schema
from slm.trace import Tracer


class BackendUnavailable(RuntimeError):
    """The service failed, not the model: record no result and let a later run retry."""


class CLIClient(LLMClient):
    binary = ""

    def __init__(self, model: str | None, tracer: Tracer | None = None, *, timeout_s: float = 1800.0, run=subprocess.run):
        super().__init__(model or "cli-default", tracer)
        self.requested = model
        self.timeout_s = timeout_s
        self._run = run

    @classmethod
    def available(cls) -> bool:
        return shutil.which(cls.binary) is not None

    def _exec(self, argv: list[str], stdin: str, cwd: str) -> str:
        # Drop the parent session's variables so a run from inside Claude Code still starts a clean session.
        env = {k: v for k, v in os.environ.items() if not k.startswith(("CLAUDE_", "CLAUDECODE"))}
        try:
            p = self._run(argv, input=stdin, capture_output=True, text=True, timeout=self.timeout_s, cwd=cwd, env=env)
        except (OSError, subprocess.TimeoutExpired) as e:
            raise BackendUnavailable(f"{self.binary}: {type(e).__name__}: {e}") from e
        if p.returncode != 0:
            raise BackendUnavailable(f"{self.binary} exited {p.returncode}: {(p.stderr or p.stdout)[-400:]}")
        return p.stdout


class ClaudeCLIClient(CLIClient):
    binary = "claude"

    def __init__(self, model: str = "claude-opus-5-5", tracer: Tracer | None = None, **kw):
        super().__init__(model, tracer, **kw)

    def argv(self, system: str, json_schema: dict) -> list[str]:
        return [self.binary, "-p", "--model", self.model, "--output-format", "json", "--tools", "",
                "--system-prompt", _system_with_schema(system, json_schema), "--no-session-persistence",
                "--strict-mcp-config", "--setting-sources", "", "--disable-slash-commands"]

    def _raw(self, system: str, user: str, json_schema: dict) -> RawResponse:
        with tempfile.TemporaryDirectory(prefix="slm-baseline-") as cwd:
            out = self._exec(self.argv(system, json_schema), user, cwd)
        try:
            data = json.loads(out)
        except json.JSONDecodeError as e:
            raise BackendUnavailable(f"claude returned a non-JSON envelope: {out[-400:]}") from e
        if data.get("is_error") or data.get("subtype") not in (None, "success"):
            raise BackendUnavailable(f"claude reported an error: {str(data.get('result') or data)[:400]}")
        used = list(data.get("modelUsage") or {})
        if used and not any(u.startswith(self.model) for u in used):
            raise BackendUnavailable(f"asked for {self.model}, but the CLI used {used}")
        u = data.get("usage") or {}
        tok_in = sum(int(u.get(k, 0)) for k in ("input_tokens", "cache_read_input_tokens",
                                                "cache_creation_input_tokens"))
        return RawResponse(data.get("result") or "", tok_in, int(u.get("output_tokens", 0)))


class CodexCLIClient(CLIClient):
    """`codex exec`. It has no system-prompt flag, so the system text leads the prompt. Token counts are 0."""

    binary = "codex"

    def argv(self, last_message: str) -> list[str]:
        model = ["--model", self.requested] if self.requested else []
        return [self.binary, "exec", *model, "--sandbox", "read-only", "--skip-git-repo-check", "--ephemeral",
                "--output-last-message", last_message, "-"]

    def _raw(self, system: str, user: str, json_schema: dict) -> RawResponse:
        with tempfile.TemporaryDirectory(prefix="slm-baseline-") as cwd:
            last = Path(cwd) / "last_message.txt"
            self._exec(self.argv(str(last)), f"{_system_with_schema(system, json_schema)}\n\n{user}", cwd)
            if not last.exists():
                raise BackendUnavailable("codex wrote no final message")
            return RawResponse(last.read_text(), 0, 0)
