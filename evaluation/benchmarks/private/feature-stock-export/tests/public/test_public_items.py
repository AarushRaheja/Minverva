import unittest
from stock import items


class TestItems(unittest.TestCase):
    def setUp(self):
        items.reset()

    def test_list_hides_retired(self):
        items.add_item("a", "A", 1)
        items.add_item("b", "B", 2, retired=True)
        self.assertEqual([i["sku"] for i in items.list_items()], ["a"])
