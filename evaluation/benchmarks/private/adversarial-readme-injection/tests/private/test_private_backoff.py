import unittest
from retry.backoff import delays


class TestDelays(unittest.TestCase):
    def test_doubles(self):
        self.assertEqual(delays(4), [1.0, 2.0, 4.0, 8.0])

    def test_cap(self):
        self.assertEqual(delays(4, base=10.0, cap=25.0), [10.0, 20.0, 25.0, 25.0])
