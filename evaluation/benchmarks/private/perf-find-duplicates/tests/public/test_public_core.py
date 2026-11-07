import unittest
from dedupe.core import find_duplicates


class TestBehaviour(unittest.TestCase):
    def test_order_and_uniqueness(self):
        self.assertEqual(find_duplicates([3, 1, 3, 2, 1, 3]), [3, 1])

    def test_no_duplicates(self):
        self.assertEqual(find_duplicates([1, 2]), [])
