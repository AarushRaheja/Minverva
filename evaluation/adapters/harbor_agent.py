"""The tool loop as a Harbor agent, so a local model can attempt Harbor tasks, including Terminal-Bench, in Docker.
The loop stays on the host and each tool call runs through environment.exec. Use it with:

    harbor run -p <tasks> --agent-import-path evaluation.adapters.harbor_agent:ToolLoopHarborAgent -m qwen3.5:4b

Harbor is imported only here, and needs Python 3.12 or newer plus Docker. This class has been loaded and driven with a
fake environment, but not yet against real Docker."""

from __future__ import annotations

import asyncio
import base64
import shlex
from pathlib import Path

from harbor.agents.base import BaseAgent
from harbor.environments.base import BaseEnvironment
from harbor.models.agent.context import AgentContext

from evaluation.adapters.baseline_agent import ToolLoop
from evaluation.adapters.model_interface import OllamaChat
from evaluation.core import Budget
from evaluation.runner.trajectory_logger import TrajectoryLogger


class HarborExecutor:
    """Blocking tool calls for the loop's thread, each run on Harbor's event loop."""

    def __init__(self, environment: BaseEnvironment, loop: asyncio.AbstractEventLoop):
        self.environment, self.loop = environment, loop

    def _exec(self, command: str, timeout_s: float | None = None):
        return asyncio.run_coroutine_threadsafe(self.environment.exec(command, timeout_sec=int(timeout_s) if timeout_s else None), self.loop).result()

    def shell(self, command: str, timeout_s: float) -> tuple[bool, str]:
        r = self._exec(command, timeout_s)
        return r.return_code == 0, (r.stdout or "") + (r.stderr or "")

    def read(self, rel: str) -> str:
        ok, out = self.shell(f"cat -- {shlex.quote(rel)}", 30)
        if not ok:
            raise OSError(out[:300])
        return out

    def write(self, rel: str, content: str) -> None:
        b = base64.b64encode(content.encode()).decode()
        q = shlex.quote(rel)
        ok, out = self.shell(f'mkdir -p "$(dirname -- {q})" && printf %s {b} | base64 -d > {q}', 30)
        if not ok:
            raise OSError(out[:300])


class ToolLoopHarborAgent(BaseAgent):
    @staticmethod
    def name() -> str:
        return "tool-loop"

    def version(self) -> str | None:
        return "1"

    async def setup(self, environment: BaseEnvironment) -> None:
        return None

    async def run(self, instruction: str, environment: BaseEnvironment, context: AgentContext) -> None:
        name = (self.model_name or "qwen3.5:4b").split("/", 1)[-1]
        log = TrajectoryLogger(Path(self.logs_dir) / "trajectory.jsonl")
        loop = ToolLoop(OllamaChat(name), HarborExecutor(environment, asyncio.get_running_loop()), log)
        try:
            await asyncio.to_thread(loop.run, instruction, Budget("harbor", 50, 900))
        finally:
            context.n_input_tokens = loop.m["tok_in"]
            context.n_output_tokens = loop.m["tok_out"]
            context.metadata = {k: v for k, v in loop.m.items() if k not in ("tok_in", "tok_out")}
