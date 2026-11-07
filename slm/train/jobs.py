"""Training jobs: one LoRA adapter per domain (plus the manager, owned by slm/manager).

There is no atomicity sweep any more: the architecture fixes the team at four specialists, so a
job is exactly one domain's data and its adapter name.
"""

from __future__ import annotations

from pydantic import BaseModel

from slm.contracts import DOMAINS
from slm.domains import ADAPTER


class Job(BaseModel):
    adapter_name: str
    domain: str
    seed: int


def jobs(seed: int = 0) -> list[Job]:
    return [Job(adapter_name=ADAPTER[d], domain=d, seed=seed) for d in DOMAINS]


def job_for(domain: str, seed: int = 0) -> Job:
    return Job(adapter_name=ADAPTER[domain], domain=domain, seed=seed)


def chunk(jobs_: list[Job], per_container: int) -> list[list[Job]]:
    """Balanced chunks: sizes differ by at most one, order preserved."""
    if per_container < 1:
        raise ValueError("per_container must be >= 1")
    if not jobs_:
        return []
    n = -(-len(jobs_) // per_container)
    base, extra = divmod(len(jobs_), n)
    out, i = [], 0
    for c in range(n):
        size = base + (1 if c < extra else 0)
        out.append(jobs_[i:i + size])
        i += size
    return out
