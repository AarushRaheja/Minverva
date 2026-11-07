"""Training + benchmark data, written under a root (default /vol on Modal). Pure Python, offline.

Layout:
  data/projects/{train,dev,test}.jsonl    Project lines (brief + gold plan)
  data/manager/{train,dev}.jsonl          manager SFT rows {system, prompt, completion}
  data/domains/{domain}.jsonl             TrainExample lines: train projects = "train",
                                          dev projects = "eval" (the gate the trainer reports)
  data/manifest.json                      counts, seed, git sha, per-domain totals
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from slm.bench.catalog import gold_artifact
from slm.bench.projects import generate_balanced
from slm.contracts import DOMAINS, PATHS, VOL, Project, TrainExample, specialist_prompt
from slm.manager.data import sft_rows

SEED = 20261101
DATA_VERSION = 2  # v2: specialist prompts from slm/specialists.py; valid TS import in gold forms
SETS = {"train": 120, "dev": 16, "test": 32}


def _path(key: str, root: str, **kw) -> Path:
    p = PATHS[key].format(**kw)
    assert p.startswith(VOL)
    return Path(root + p[len(VOL):])


def _write_jsonl(path: Path, items) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    with path.open("w") as f:
        for it in items:
            f.write(it.model_dump_json() + "\n")
            n += 1
    return n


def _write_dicts(path: Path, rows: list[dict]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r) + "\n" for r in rows))
    return len(rows)


def domain_examples(projects: list[Project], split: str) -> dict[str, list[TrainExample]]:
    """One example per task: the specialist prompt for that task and its gold artifact."""
    out: dict[str, list[TrainExample]] = {d: [] for d in DOMAINS}
    for p in projects:
        if p.plan is None:
            continue
        for t in p.plan.tasks:
            out[t.domain].append(TrainExample(
                domain=t.domain, kind=t.kind, target=t.target, prompt=specialist_prompt(p.plan, t),
                completion=gold_artifact(p.plan, t).model_dump_json(),
                split=split,  # type: ignore[arg-type]
                project_id=p.id,
            ))
    return out


def build_all(root: str = VOL, git_sha: str = "unknown", scale: float = 1.0) -> dict:
    """Write all data. scale<1 shrinks every count (for local smoke tests)."""

    def s(n: int) -> int:
        return max(1, int(n * scale))

    man: dict = {"data_version": DATA_VERSION, "seed": SEED, "git_sha": git_sha, "scale": scale,
                 "projects": {}, "domains": {}, "domains_meta": {"tasks": {}}}
    by_split: dict[str, list[Project]] = {}
    for split, n in SETS.items():
        projects = generate_balanced(s(n), split, SEED)
        by_split[split] = projects
        _write_jsonl(_path("projects", root, name=split), projects)
        man["projects"][split] = {
            "total": len(projects),
            "per_template": dict(sorted(Counter(p.template_id for p in projects).items())),
            "tasks": dict(sorted(Counter(p.n_tasks for p in projects).items())),
            "depth": dict(sorted(Counter(p.depth for p in projects).items())),
        }

    rows = sft_rows(by_split["train"])
    _write_dicts(_path("manager_data", root, name="train"), rows)
    _write_dicts(_path("manager_data", root, name="dev"), sft_rows(by_split["dev"]))
    man["manager"] = {"train": len(rows), "dev": len(by_split["dev"])}

    train_ex = domain_examples(by_split["train"], "train")
    eval_ex = domain_examples(by_split["dev"], "eval")
    for d in DOMAINS:
        ex = train_ex[d] + eval_ex[d]
        _write_jsonl(_path("domain_data", root, name=d), ex)
        c = Counter(e.split for e in ex)
        man["domains"][d] = {"train": c["train"], "eval": c["eval"]}
        man["domains_meta"]["tasks"][d] = dict(sorted(Counter(e.kind for e in train_ex[d]).items()))

    out = Path(root) / "data" / "manifest.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(man, indent=1))
    return man


def load_projects(split: str, root: str = VOL) -> list[Project]:
    path = _path("projects", root, name=split)
    return [Project.model_validate_json(line) for line in path.read_text().splitlines() if line.strip()]
