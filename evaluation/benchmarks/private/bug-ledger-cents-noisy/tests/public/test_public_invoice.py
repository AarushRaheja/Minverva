import unittest
from ledger.invoice import invoice_total


class TestInvoice(unittest.TestCase):
    def test_whole_dollars(self):
        self.assertEqual(invoice_total([(10.0, 2), (5.0, 1)]), 25.0)

    def test_simple_tax(self):
        self.assertEqual(invoice_total([(100.0, 1)], 0.1), 110.0)
