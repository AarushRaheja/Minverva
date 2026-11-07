import unittest
from dedupe.core import find_duplicates


class Counted:
    eqs = 0

    def __init__(self, v):
        self.v = v

    def __hash__(self):
        return hash(self.v)

    def __eq__(self, other):
        Counted.eqs += 1
        return self.v == other.v


class TestSpeed(unittest.TestCase):
    def test_comparisons_stay_linear(self):
        Counted.eqs = 0
        n = 2000
        out = find_duplicates([Counted(i) for i in range(n)] + [Counted(0), Counted(0)])
        self.assertEqual([x.v for x in out], [0])
        self.assertLess(Counted.eqs, 5 * n)
