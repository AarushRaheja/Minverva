"""Controls and baselines. `null` and `oracle` test the harness itself. `tool-loop` is a conventional shell, read and
edit loop on the same local model as the custom agent, which is the Regime A comparison. `command` wraps a CLI agent."""

from __future__ import annotations

import json
import os
import re
import shlex
import shutil
import subprocess
import time
from pathlib import Path

from evaluation.adapters.model_interface import ModelUnavailable, OllamaChat
from evaluation.core import BUDGET_EXHAUSTED, COMPLETED, CRASHED, ENVIRONMENT_FAILURE, UNSUPPORTED, AgentResult, Budget, Task
from evaluation.runner import sandbox
from evaluation.runner.process import run_limited
from evaluation.runner.trajectory_logger import TrajectoryLogger

TEST_CMD = re.compile(r"\b(unittest|pytest)\b")
OUTPUT_LIMIT = 4000


def _finish(task: Task, status: str, metrics: dict, detail: str = "") -> AgentResult:
    art = Path(task.artifacts_path)
    (art / "metrics.json").write_text(json.dumps(metrics, indent=1))
    return AgentResult(task.task_id, None, status, str(art / "trajectory.jsonl"), str(art / "metrics.json"), detail)


class NullAgent:
    """Negative control: changes nothing, so every task must come back unresolved."""

    def __init__(self, manifest: dict):
        self.manifest = manifest

    def run(self, task: Task, budget: Budget) -> AgentResult:
        TrajectoryLogger(Path(task.artifacts_path) / "trajectory.jsonl")
        return _finish(task, COMPLETED, {"steps": 0, "model_calls": 0, "tool_calls": 0})


class OracleAgent:
    """Positive control: applies the reference, so every task with a reference must come back resolved."""

    def __init__(self, manifest: dict):
        self.manifest = manifest

    def run(self, task: Task, budget: Budget) -> AgentResult:
        TrajectoryLogger(Path(task.artifacts_path) / "trajectory.jsonl")
        if not task.reference_path or not Path(task.reference_path).is_dir():
            return _finish(task, UNSUPPORTED, {"steps": 0}, "no reference solution for this task")
        shutil.copytree(task.reference_path, task.workspace_path, dirs_exist_ok=True)
        return _finish(task, COMPLETED, {"steps": 1, "model_calls": 0, "tool_calls": 0})


# --- a conventional tool loop --------------------------------------------------------------------------------------

LOOP_SYSTEM = """You are a coding agent working in a repository. Reply with exactly one JSON object each turn, one of:
{"tool": "shell", "command": "..."}            run a command in the repository root
{"tool": "read_file", "path": "..."}           read a file
{"tool": "write_file", "path": "...", "content": "..."}   create or replace a file
{"tool": "edit_file", "path": "...", "old": "...", "new": "..."}   replace exact text once
{"tool": "finish"}                             stop when the task is done
Look at the code, make the change, run the tests, and fix what fails."""


class LocalExecutor:
    def __init__(self, workspace: Path, tmp: Path, network: bool = False):
        self.workspace, self.tmp, self.network = workspace, tmp, network

    def shell(self, command: str, timeout_s: float) -> tuple[bool, str]:
        profile = sandbox.agent_profile(self.workspace, self.tmp, network=self.network)
        argv = sandbox.wrap(profile, self.tmp / "agent.sb", ["/bin/sh", "-c", command])
        env = {**sandbox.agent_env(self.tmp, {"PATH": os.environ["PATH"]}), "HOME": str(self.tmp)}
        out: list[str] = []
        r = run_limited(argv, cwd=str(self.workspace), env=env, wall_s=timeout_s, output=out)
        return r.returncode == 0 and not r.timed_out, "".join(out) + (" [timed out]" if r.timed_out else "")

    def _path(self, rel: str) -> Path:
        p = (self.workspace / rel).resolve()
        if not p.is_relative_to(self.workspace.resolve()):
            raise ValueError(f"{rel} is outside the repository")
        return p

    def read(self, rel: str) -> str:
        return self._path(rel).read_text()

    def write(self, rel: str, content: str) -> None:
        p = self._path(rel)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content)


class ToolLoop:
    def __init__(self, chat, executor, log: TrajectoryLogger, *, command_timeout_s: float = 60.0):
        self.chat, self.ex, self.log, self.command_timeout_s = chat, executor, log, command_timeout_s
        self.m = {"steps": 0, "model_calls": 0, "tool_calls": 0, "tok_in": 0, "tok_out": 0, "invalid_actions": 0, "tool_errors": 0}

    def _act(self, a: dict) -> tuple[bool, str]:
        tool = a.get("tool")
        if tool == "shell":
            return self.ex.shell(str(a.get("command", "")), self.command_timeout_s)
        if tool == "read_file":
            return True, self.ex.read(str(a["path"]))
        if tool == "write_file":
            self.ex.write(str(a["path"]), str(a["content"]))
            return True, "written"
        if tool == "edit_file":
            text = self.ex.read(str(a["path"]))
            if str(a["old"]) not in text:
                return False, "old text not found"
            self.ex.write(str(a["path"]), text.replace(str(a["old"]), str(a["new"]), 1))
            return True, "edited"
        return False, f"unknown tool {tool!r}"

    def run(self, instruction: str, budget: Budget) -> str:
        msgs = [{"role": "system", "content": LOOP_SYSTEM}, {"role": "user", "content": instruction}]
        deadline = time.monotonic() + budget.wall_time_seconds
        while self.m["steps"] < budget.max_steps:
            if time.monotonic() > deadline:
                return BUDGET_EXHAUSTED
            self.m["steps"] += 1
            r = self.chat.chat(msgs)
            self.m["model_calls"] += 1
            self.m["tok_in"] += r["tok_in"]
            self.m["tok_out"] += r["tok_out"]
            self.log.log("model", tok_in=r["tok_in"], tok_out=r["tok_out"], text=r["text"])
            msgs.append({"role": "assistant", "content": r["text"]})
            try:
                a = json.loads(r["text"])
                if not isinstance(a, dict):
                    raise ValueError("not an object")
            except ValueError:
                self.m["invalid_actions"] += 1
                self.log.log("error", error="invalid action", text=r["text"][:300])
                msgs.append({"role": "user", "content": "That was not valid JSON. Reply with one JSON action."})
                continue
            if a.get("tool") == "finish":
                return COMPLETED
            command = str(a.get("command", ""))
            self.m["tool_calls"] += 1
            self.log.log("tool_call", tool=a.get("tool"), args=a, is_test=bool(TEST_CMD.search(command)),
                         signature=json.dumps(a, sort_keys=True)[:300])
            try:
                ok, out = self._act(a)
            except (KeyError, ValueError, OSError) as e:
                ok, out = False, f"{type(e).__name__}: {e}"
            self.m["tool_errors"] += not ok
            self.log.log("tool_result", ok=ok, output=out)
            msgs.append({"role": "user", "content": f"exit_ok={ok}\n{out[-OUTPUT_LIMIT:]}"})
        return BUDGET_EXHAUSTED


class ToolLoopAgent:
    def __init__(self, manifest: dict, chat=None):
        self.manifest = manifest
        inf = manifest.get("inference", {})
        self.chat = chat or OllamaChat(manifest["model_id"], temperature=inf.get("temperature", 0.0), seed=inf.get("seed", 0),
                                       max_output_tokens=inf.get("max_output_tokens", 2048), num_ctx=inf.get("num_ctx", 8192))

    def run(self, task: Task, budget: Budget) -> AgentResult:
        art = Path(task.artifacts_path)
        tmp = Path(task.workspace_path).parent / "tmp"
        tmp.mkdir(exist_ok=True)
        log = TrajectoryLogger(art / "trajectory.jsonl")
        loop = ToolLoop(self.chat, LocalExecutor(Path(task.workspace_path), tmp), log)
        try:
            status = loop.run(task.instruction, budget)
        except ModelUnavailable as e:
            log.log("error", error=str(e))
            return _finish(task, ENVIRONMENT_FAILURE, loop.m, str(e))
        return _finish(task, status, loop.m)


# --- a command-line agent ------------------------------------------------------------------------------------------


class CommandAgent:
    """A CLI agent under the agent sandbox. Its output is recorded line by line and `{prompt}` fills the template."""

    def __init__(self, manifest: dict):
        self.manifest = manifest

    def argv(self, task: Task, budget: Budget) -> list[str]:
        return [x.replace("{prompt}", task.instruction) for x in shlex.split(self.manifest["command"])]

    def available(self) -> bool:
        return shutil.which(shlex.split(self.manifest["command"])[0]) is not None

    def env(self, tmp: Path) -> dict:
        drop = ("CLAUDE_", "CLAUDECODE")
        return sandbox.agent_env(tmp, {k: v for k, v in os.environ.items() if not k.startswith(drop)})

    def sandbox_opts(self) -> dict:
        ex = self.manifest.get("execution", {})
        home = Path.home()
        return {"network": ex.get("network_access", False),
                "extra_write": [str(home / p) for p in ex.get("extra_write", [])],
                "extra_read": [str(home / p) for p in ex.get("extra_read", [])]}

    def handle_line(self, line: str, log: TrajectoryLogger, m: dict, budget: Budget) -> bool:
        log.log("message", text=line.rstrip())
        return True

    def run(self, task: Task, budget: Budget) -> AgentResult:
        art = Path(task.artifacts_path)
        workspace = Path(task.workspace_path)
        tmp = workspace.parent / "tmp"
        tmp.mkdir(exist_ok=True)
        log = TrajectoryLogger(art / "trajectory.jsonl")
        m = {"steps": 0, "model_calls": 0, "tool_calls": 0, "tok_in": 0, "tok_out": 0, "tool_errors": 0, "cost_usd": None}
        if not self.available():
            return _finish(task, ENVIRONMENT_FAILURE, m, f"{self.manifest['command'].split()[0]} isn't installed")
        profile = sandbox.agent_profile(workspace, tmp, **self.sandbox_opts())
        argv = sandbox.wrap(profile, tmp / "agent.sb", self.argv(task, budget))
        out: list[str] = []
        r = run_limited(argv, cwd=str(workspace), env=self.env(tmp), wall_s=budget.wall_time_seconds,
                        on_line=lambda line: self.handle_line(line, log, m, budget), output=out)
        m |= {"agent_cpu_s": r.cpu_s, "agent_peak_rss_mb": r.peak_rss_mb}
        if m.get("api_error"):
            return _finish(task, ENVIRONMENT_FAILURE, m, str(m["api_error"])[:300])
        wanted = self.manifest.get("model_id")
        if m.get("models_used") and wanted and not any(u.startswith(wanted) for u in m["models_used"]):
            return _finish(task, ENVIRONMENT_FAILURE, m, f"asked for {wanted}, but the CLI used {m['models_used']}")
        if r.timed_out or r.stopped or m.get("budget_hit"):
            return _finish(task, BUDGET_EXHAUSTED, m, "stopped at the budget")
        if r.returncode != 0:
            return _finish(task, CRASHED, m, "".join(out)[-400:])
        return _finish(task, COMPLETED, m)


class ClaudeCodeAgent(CommandAgent):
    """`claude -p` with user settings, MCP servers and skills off, so nothing from this machine leaks into the trial.
    This CLI has no max-turns flag, so the step budget is enforced here by counting tool calls and stopping the run."""

    def argv(self, task: Task, budget: Budget) -> list[str]:
        cost = ["--max-budget-usd", str(budget.max_cost_usd)] if budget.max_cost_usd else []
        return ["claude", "-p", task.instruction, "--model", self.manifest["model_id"], "--output-format", "stream-json",
                "--verbose", "--permission-mode", "bypassPermissions", "--no-session-persistence", "--strict-mcp-config",
                "--setting-sources", "", "--disable-slash-commands", *cost]

    def available(self) -> bool:
        return shutil.which("claude") is not None

    def env(self, tmp: Path) -> dict:
        # Otherwise its Bash tool writes to a shared temp folder outside the sandbox, and every command fails.
        return {**super().env(tmp), "CLAUDE_CODE_TMPDIR": str(tmp)}

    def handle_line(self, line: str, log: TrajectoryLogger, m: dict, budget: Budget) -> bool:
        try:
            d = json.loads(line)
        except ValueError:
            log.log("message", text=line.rstrip())
            return True
        kind = d.get("type")
        if kind == "assistant":
            m["model_calls"] += 1
            for b in (d.get("message") or {}).get("content") or []:
                if b.get("type") == "tool_use":
                    m["tool_calls"] += 1
                    m["steps"] += 1
                    command = str((b.get("input") or {}).get("command", ""))
                    log.log("tool_call", tool=b.get("name"), args=b.get("input"), is_test=bool(TEST_CMD.search(command)),
                            signature=json.dumps([b.get("name"), b.get("input")], sort_keys=True)[:300])
                elif b.get("type") == "text":
                    log.log("model", text=b.get("text", ""))
        elif kind == "user":
            content = (d.get("message") or {}).get("content")
            for b in content if isinstance(content, list) else []:
                if b.get("type") == "tool_result":
                    bad = bool(b.get("is_error"))
                    m["tool_errors"] += bad
                    log.log("tool_result", ok=not bad, output=str(b.get("content"))[:OUTPUT_LIMIT])
        elif kind == "result":
            u = d.get("usage") or {}
            m["tok_in"] = sum(int(u.get(k, 0)) for k in ("input_tokens", "cache_read_input_tokens", "cache_creation_input_tokens"))
            m["tok_out"] = int(u.get("output_tokens", 0))
            m["cost_usd"] = d.get("total_cost_usd")
            m["models_used"] = list(d.get("modelUsage") or {})
            log.log("message", result_subtype=d.get("subtype"), is_error=d.get("is_error"), text=str(d.get("result"))[:1000])
            if str(d.get("subtype", "")).startswith("error_max"):
                m["budget_hit"] = True
            elif d.get("is_error"):  # the service refused or failed, which says nothing about the agent
                m["api_error"] = str(d.get("result") or d.get("subtype"))
        return m["steps"] <= budget.max_steps


def tool_version(binary: str) -> str | None:
    try:
        return subprocess.run([binary, "--version"], capture_output=True, text=True, timeout=20).stdout.strip()[:80]
    except (OSError, subprocess.TimeoutExpired):
        return None
