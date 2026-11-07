import sqlite3
import unittest
from migrate.runner import MigrationError, Runner


class TestStructure(unittest.TestCase):
    def test_error_type_exists(self):
        self.assertTrue(issubclass(MigrationError, Exception))
        self.assertIsNotNone(Runner(sqlite3.connect(":memory:"), []))
