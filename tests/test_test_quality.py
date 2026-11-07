from __future__ import annotations

from slm.bench.catalog import gold_artifacts
from slm.bench.mutants import mutants_for
from slm.bench.variety import generate_varied
from slm.contracts import integrate
from slm.domains import DOMAINS
from slm.manager.spec import SpecTest, gold_spec
from slm.manager.test_compile import compile_test

SEED = 20261101


def _projects():
    return generate_varied(40, "dev", SEED) + generate_varied(40, "train", SEED)


def _tests(spec):
    out = list(spec.system_tests)
    for d in DOMAINS:
        out += spec.domain(d).integration_tests
    for _, task in spec.tasks():
        out += [s.test for s in task.steps]
    return out


def test_every_gold_test_compiles():
    for p in _projects():
        for t in _tests(gold_spec(p.plan)):
            assert compile_test(t) is not None, (t.id, t.description, t.expected)


def _test(description: str, expected: str) -> SpecTest:
    return SpecTest(id="x", scope="unit", description=description, expected=expected, verifies=["table:x"])


def test_a_check_uses_the_values_in_the_text():
    check = compile_test(_test("Send GET /api/wrongs when two rows exist.",
                               "The response lists both rows, newest id first."))
    assert check.kind == "list_order" and check.arg("path") == "/api/wrongs"


def test_paraphrases_and_contradictions_do_not_compile():
    assert compile_test(_test("Fetch all the rows.", "It lists them.")) is None
    assert compile_test(_test("Apply the boat schema to a database.",
                              "CREATE TABLE dock succeeds and the table has title and id columns.")) is None
    assert compile_test(_test("Render BoatPage with a stubbed fetch returning two rows.",
                              "DockPage renders one list item per row.")) is None


def test_every_mutant_changes_its_file_and_ids_are_unique():
    for p in _projects():
        files = {f.path: f.content for f in integrate(p.id, p.plan, gold_artifacts(p.plan)).files}
        mutants = mutants_for(p.plan, files)
        assert len({m.id for m in mutants}) == len(mutants)
        assert all(m.content != files[m.path] for m in mutants)
        for m in mutants:
            if m.path.endswith(".py"):
                compile(m.content, m.path, "exec")
