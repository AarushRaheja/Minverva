import sqlite3
import unittest
from migrate.runner import MigrationError, Runner

M1 = (1, "users", "CREATE TABLE users(id INTEGER)")
M2 = (2, "posts", "CREATE TABLE posts(id INTEGER); INSERT INTO posts VALUES (1);")
BAD = (3, "bad", "CREATE TABLE half(id INTEGER); INSERT INTO nope VALUES (1);")


def tables(c):
    return {r[0] for r in c.execute("select name from sqlite_master where type='table'")}


class TestRunner(unittest.TestCase):
    def setUp(self):
        self.c = sqlite3.connect(":memory:")

    def test_stage1_orders_and_is_idempotent(self):
        r = Runner(self.c, [M2, M1])
        self.assertEqual(r.upgrade(), [1, 2])
        self.assertEqual(r.upgrade(), [])

    def test_stage2_failure_rolls_back_only_that_one(self):
        with self.assertRaisesRegex(MigrationError, "3"):
            Runner(self.c, [M1, M2, BAD]).upgrade()
        self.assertIn("posts", tables(self.c))
        self.assertNotIn("half", tables(self.c))
        self.assertEqual(self.c.execute("select count(*) from schema_migrations").fetchone()[0], 2)

    def test_stage3_duplicates_run_nothing(self):
        with self.assertRaises(MigrationError):
            Runner(self.c, [M1, (1, "again", "CREATE TABLE x(id INTEGER)")]).upgrade()
        self.assertNotIn("users", tables(self.c))

    def test_stage3_changed_sql_detected(self):
        Runner(self.c, [M1]).upgrade()
        with self.assertRaises(MigrationError):
            Runner(self.c, [(1, "users", "CREATE TABLE users(id TEXT)"), M2]).upgrade()
        self.assertNotIn("posts", tables(self.c))

    def test_stage4_status(self):
        Runner(self.c, [M1]).upgrade()
        s = Runner(self.c, [M2, M1]).status()
        self.assertEqual(s, [{"version": 1, "name": "users", "applied": True}, {"version": 2, "name": "posts", "applied": False}])
