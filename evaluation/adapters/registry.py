"""Build an agent from its manifest."""

from __future__ import annotations

import tomllib
from pathlib import Path

CONFIGS = Path(__file__).resolve().parents[1] / "configs"


def load_manifest(agent_id: str) -> dict:
    path = CONFIGS / "agents" / f"{agent_id}.toml"
    if not path.exists():
        raise FileNotFoundError(f"no manifest for agent {agent_id!r} at {path}")
    return tomllib.loads(path.read_text())


def build_agent(manifest: dict):
    from evaluation.adapters import baseline_agent as b

    kind = manifest["adapter"]
    if kind == "slm":
        from evaluation.adapters.custom_agent import SlmAgent

        return SlmAgent(manifest)
    return {"null": b.NullAgent, "oracle": b.OracleAgent, "tool_loop": b.ToolLoopAgent,
            "command": b.CommandAgent, "claude_code": b.ClaudeCodeAgent}[kind](manifest)
