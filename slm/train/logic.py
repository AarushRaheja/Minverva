"""Pure-Python training-factory logic (no GPU deps, tested offline)."""

from __future__ import annotations

import random
from collections import defaultdict
from pathlib import Path

from slm import contracts as C
from slm.train.jobs import Job

EVAL_CAP = 400
RETRY_THRESHOLD = 0.90
ESCALATED_EXAMPLES = 1200


def load_examples(
    job: Job, data_path: str, allow_missing: bool = False
) -> tuple[list[C.TrainExample], list[C.TrainExample]]:
    """Read one domain file, keeping only this domain's rows and splitting train/eval."""
    p = Path(data_path.format(name=job.domain))
    if not p.exists():
        if allow_missing:
            return [], []
        raise FileNotFoundError(f"missing domain data for {job.adapter_name}: {p}")
    train, ev = [], []
    for line in p.read_text().splitlines():
        if not line.strip():
            continue
        ex = C.TrainExample.model_validate_json(line)
        if ex.domain != job.domain:
            continue
        (train if ex.split == "train" else ev).append(ex)
    return train, ev


def expected_train_count(job: Job, manifest: dict) -> int:
    if job.domain not in manifest["domains"]:
        raise KeyError(f"{job.adapter_name}: domain {job.domain!r} absent from manifest")
    return manifest["domains"][job.domain]["train"]


def check_counts(job: Job, n_train: int, manifest: dict) -> int:
    """Fixed-budget guard: loaded examples must equal the manifest's count for this domain."""
    exp = expected_train_count(job, manifest)
    if n_train != exp:
        raise AssertionError(f"{job.adapter_name}: loaded {n_train} train examples, manifest says {exp}")
    return exp


def stratified_eval(ev: list[C.TrainExample], cap: int = EVAL_CAP, seed: int = 0) -> list[C.TrainExample]:
    """Cap the eval set at `cap`, with (near-)equal share per task kind."""
    if len(ev) <= cap:
        return ev
    by_kind: dict[str, list[C.TrainExample]] = defaultdict(list)
    for e in ev:
        by_kind[e.kind].append(e)
    rng = random.Random(seed)
    for v in by_kind.values():
        rng.shuffle(v)
    out: list[C.TrainExample] = []
    pools = sorted(by_kind)
    i = 0
    while len(out) < cap:
        progressed = False
        for k in pools:
            if i < len(by_kind[k]) and len(out) < cap:
                out.append(by_kind[k][i])
                progressed = True
        if not progressed:
            break
        i += 1
    return out


def per_kind_accuracy(ev: list[C.TrainExample], correct: list[bool]) -> dict[str, float]:
    tot: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    for e, c in zip(ev, correct):
        tot[e.kind][0] += int(c)
        tot[e.kind][1] += 1
    return {k: c / n for k, (c, n) in sorted(tot.items())}


def needs_retry(job: Job, gate: float, escalated: bool) -> bool:
    """Retry policy: once, on the large domain data, when the gate is below 0.90."""
    return not escalated and gate < RETRY_THRESHOLD


def data_version(manifest: dict) -> int | None:
    return manifest.get("data_version")


def is_done(job: Job, adapter_dir: Path, version: int) -> bool:
    """Idempotence: entry exists with matching seed, adapter and data_version."""
    entry = adapter_dir / "registry_entry.json"
    if not entry.exists():
        return False
    try:
        e = C.RegistryEntry.model_validate_json(entry.read_text())
        return e.seed == job.seed and e.adapter_name == job.adapter_name and e.data_version == version
    except Exception:
        return False


def registry_summary(entries: list[C.RegistryEntry]) -> dict[str, dict]:
    out = {}
    for d in C.DOMAINS:
        mine = [e for e in entries if e.domain == d]
        gates = [e.gate_task_ok for e in mine]
        out[d] = {
            "adapters": [e.adapter_name for e in mine],
            "missing": not mine,
            "gate_mean": sum(gates) / len(gates) if gates else None,
            "gate_min": min(gates, default=None),
            "below_threshold": sum(x < RETRY_THRESHOLD for x in gates),
        }
    return out
