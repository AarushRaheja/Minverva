import unittest
from datetime import date
from importer.dates import parse_date


class TestIso(unittest.TestCase):
    def test_iso(self):
        self.assertEqual(parse_date(" 2026-03-04 "), date(2026, 3, 4))
