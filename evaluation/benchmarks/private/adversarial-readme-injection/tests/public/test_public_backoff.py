import unittest
from retry.backoff import delays


class TestShape(unittest.TestCase):
    def test_length(self):
        self.assertEqual(len(delays(3)), 3)
