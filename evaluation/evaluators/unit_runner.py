"""Runs inside the grader sandbox with -I: python unit_runner.py <tree> <out.json>. Standard library only."""
import json
import os
import sys
import unittest

tree, out = sys.argv[1], sys.argv[2]
sys.path.insert(0, tree)
os.chdir(tree)
results = {}


class Recorder(unittest.TestResult):
    def _set(self, test, value):
        results[f"{suite}::{test.id()}"] = value

    def addSuccess(self, test):
        self._set(test, "pass")

    def addFailure(self, test, err):
        self._set(test, "fail")

    def addError(self, test, err):
        self._set(test, "error")

    def addSkip(self, test, reason):
        self._set(test, "skip")

    def addExpectedFailure(self, test, err):
        self._set(test, "fail")

    def addUnexpectedSuccess(self, test):
        self._set(test, "fail")


for suite in ("public", "private"):
    start = os.path.join(tree, "tests", suite)
    if os.path.isdir(start):
        sys.path.insert(0, start)
        unittest.defaultTestLoader.discover(start, top_level_dir=start).run(Recorder())
        unittest.defaultTestLoader._top_level_dir = None
with open(out, "w") as f:
    json.dump(results, f)
