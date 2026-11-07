import unittest
from datetime import date
from importer.dates import parse_date


class TestSlash(unittest.TestCase):
    def test_only_one_reading_is_valid(self):
        self.assertEqual(parse_date("25/12/2026"), date(2026, 12, 25))
        self.assertEqual(parse_date("12/25/2026"), date(2026, 12, 25))

    def test_two_readings_is_rejected(self):
        with self.assertRaises(ValueError):
            parse_date("03/04/2026")

    def test_same_date_either_way_is_fine(self):
        self.assertEqual(parse_date("05/05/2026"), date(2026, 5, 5))

    def test_invalid_rejected(self):
        for bad in ("31/02/2026", "13/13/2026", "1/2", "a/b/2026"):
            with self.assertRaises(ValueError):
                parse_date(bad)
