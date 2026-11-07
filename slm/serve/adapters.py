"""Adapter directories on the Volume as the serve app sees them (pathlib only: runs in any image)."""

from __future__ import annotations

from pathlib import Path

TRAINED_MARKER = "registry_entry.json"  # the trainer writes it beside every adapter it publishes


def dummy_targets(root: Path, names: list[str]) -> tuple[list[str], list[str]]:
    """(names a dummy may be written to, names kept because a trained adapter lives there).

    Dummies share /vol/adapters/<seed>/<name> with the trainer's output, so a smoke run must never
    replace trained weights with random ones."""
    write, kept = [], []
    for n in names:
        (kept if (root / n / TRAINED_MARKER).exists() else write).append(n)
    return write, kept
