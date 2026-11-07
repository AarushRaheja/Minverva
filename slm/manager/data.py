"""Manager SFT data rows: gold plan JSON for a project brief."""

from __future__ import annotations

import json
from pathlib import Path

from slm.contracts import Project
from slm.manager.manager import format_example


def sft_rows(projects: list[Project]) -> list[dict]:
    """{system, prompt, completion} rows from projects with gold plans (others are skipped)."""
    rows = []
    for p in projects:
        if p.plan is None:
            continue
        system, prompt, completion = format_example(p)
        rows.append({"system": system, "prompt": prompt, "completion": completion})
    return rows


def write_jsonl(rows: list[dict], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r) + "\n" for r in rows))
