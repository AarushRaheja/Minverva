"""The machine a run happened on, and whether it has room to start."""

from __future__ import annotations

import platform
import re
import shutil
import subprocess
from pathlib import Path


def hardware() -> dict:
    def sysctl(k):
        try:
            return subprocess.run(["sysctl", "-n", k], capture_output=True, text=True).stdout.strip()
        except OSError:
            return ""
    return {"machine": platform.machine(), "os": platform.platform(), "cpu": sysctl("machdep.cpu.brand_string"),
            "ncpu": sysctl("hw.ncpu"), "mem_bytes": sysctl("hw.memsize")}


def free_memory_pct() -> int | None:
    try:
        m = re.search(r"free percentage: (\d+)%", subprocess.run(["memory_pressure"], capture_output=True, text=True).stdout)
    except OSError:
        return None
    return int(m.group(1)) if m else None


def preflight(path: Path, min_disk_gb: float, min_free_memory_pct: int, needs_local_model: bool) -> list[str]:
    """Reasons not to start. Too little memory only blocks agents that load a local model."""
    problems = []
    free_gb = shutil.disk_usage(path).free / 1e9
    if free_gb < min_disk_gb:
        problems.append(f"only {free_gb:.1f} GB of disk free, need {min_disk_gb}")
    mem = free_memory_pct()
    if needs_local_model and mem is not None and mem < min_free_memory_pct:
        problems.append(f"only {mem}% of memory free, a local model needs {min_free_memory_pct}%")
    return problems
