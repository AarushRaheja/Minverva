import csv
import os
import tempfile
import unittest
from stock import items


class TestExport(unittest.TestCase):
    def setUp(self):
        items.reset()
        items.add_item("b2", 'Bolt, "large"', 5)
        items.add_item("a1", "Nut", 3)
        items.add_item("z9", "Old", 1, retired=True)
        self.path = os.path.join(tempfile.mkdtemp(), "o.csv")

    def rows(self):
        with open(self.path, newline="") as f:
            return list(csv.reader(f))

    def test_sorted_with_header_and_count(self):
        self.assertEqual(items.export_csv(self.path), 2)
        self.assertEqual(self.rows(), [["sku", "name", "quantity"], ["a1", "Nut", "3"], ["b2", 'Bolt, "large"', "5"]])

    def test_include_retired(self):
        self.assertEqual(items.export_csv(self.path, include_retired=True), 3)
        self.assertEqual(self.rows()[-1][0], "z9")

    def test_list_items_unchanged(self):
        self.assertEqual(sorted(i["sku"] for i in items.list_items()), ["a1", "b2"])
