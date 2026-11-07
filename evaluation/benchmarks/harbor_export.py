"""Write repository tasks in Harbor's task format, so they can run in Docker. Hidden tests go only in tests/, which
Harbor copies in at verification time, after the agent has finished."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from evaluation.benchmarks.task_registry import TaskSpec
from evaluation.evaluators.correctness import RUNNER

IMAGE = "python:3.13-slim"
DOCKERFILE = f"""FROM {IMAGE}
RUN apt-get update && apt-get install -y --no-install-recommends git && rm -rf /var/lib/apt/lists/*
WORKDIR /workspace
COPY repository/ /workspace/
"""
TASK_TOML = """schema_version = "1.4"

[metadata]
author_name = "{author}"
category = "{task_class}"
difficulty = "{difficulty}"
tags = ["private-stress-suite", "{capability}"]

[verifier]
timeout_sec = 120.0

[agent]
timeout_sec = 900.0

[environment]
build_timeout_sec = 600.0
cpus = 2
memory_mb = 4096
storage_mb = 4096
network_mode = "no-network"
"""
TEST_SH = """#!/bin/sh
# Restores pristine tests, runs everything, and passes only if the recorded fail-to-pass and pass-to-pass tests do.
cd /workspace
rm -rf tests
mkdir -p tests
cp -r /tests/public tests/public
cp -r /tests/private tests/private
python3 -I /tests/unit_runner.py /workspace /tmp/results.json
python3 -I /tests/check.py /tests/expected.json /tmp/results.json > /logs/verifier/reward.txt
"""
CHECK_PY = """import json, sys
want, got = (json.load(open(p)) for p in sys.argv[1:3])
print(1 if all(got.get(t) == "pass" for t in want) else 0)
"""
SOLVE_SH = """#!/bin/sh
cp -r /solution/files/. /workspace/
"""


def export_task(spec: TaskSpec, dest: Path) -> Path:
    if spec.family != "repo":
        raise ValueError(f"{spec.id}: only repository tasks export; project builds use the run check")
    d = dest / spec.id
    if d.exists():
        shutil.rmtree(d)
    (d / "environment").mkdir(parents=True)
    (d / "tests").mkdir()
    (d / "solution").mkdir()
    (d / "instruction.md").write_text(spec.instruction)
    (d / "task.toml").write_text(TASK_TOML.format(author=spec.author, task_class=spec.task_class, difficulty=spec.difficulty, capability=spec.capability))
    (d / "environment/Dockerfile").write_text(DOCKERFILE)
    shutil.copytree(spec.path / "repository", d / "environment/repository")
    shutil.copytree(spec.path / "tests/public", d / "environment/repository/tests/public")
    shutil.copytree(spec.path / "tests/public", d / "tests/public")
    shutil.copytree(spec.path / "tests/private", d / "tests/private")
    shutil.copy(RUNNER, d / "tests/unit_runner.py")
    (d / "tests/check.py").write_text(CHECK_PY)
    (d / "tests/expected.json").write_text(json.dumps([*spec.fail_to_pass, *spec.pass_to_pass]))
    (d / "tests/test.sh").write_text(TEST_SH)
    (d / "tests/test.sh").chmod(0o755)
    shutil.copytree(spec.path / "solution", d / "solution/files")
    (d / "solution/solve.sh").write_text(SOLVE_SH)
    (d / "solution/solve.sh").chmod(0o755)
    return d
