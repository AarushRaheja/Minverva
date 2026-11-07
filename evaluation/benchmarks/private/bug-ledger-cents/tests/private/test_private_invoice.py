import unittest
from ledger.invoice import invoice_total
from ledger.money import to_cents
from ledger.tax import tax_cents


class TestCents(unittest.TestCase):
    def test_float_price_keeps_its_cents(self):
        self.assertEqual(to_cents(19.99), 1999)
        self.assertEqual(to_cents(1.15), 115)

    def test_tax_rounds_half_up(self):
        self.assertEqual(tax_cents(1999, 0.075), 150)
        self.assertEqual(tax_cents(1000, 0.0825), 83)

    def test_total_end_to_end(self):
        self.assertEqual(invoice_total([(19.99, 3)], 0.075), 64.47)
