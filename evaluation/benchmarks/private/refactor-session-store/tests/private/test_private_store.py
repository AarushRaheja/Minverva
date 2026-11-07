import unittest
from auth import billing, sessions
from auth.store import SessionStore


class TestStore(unittest.TestCase):
    def test_instances_are_separate(self):
        a, b = SessionStore(), SessionStore()
        tok = a.create("ann")
        self.assertEqual(a.user_for(tok), "ann")
        self.assertIsNone(b.user_for(tok))

    def test_module_functions_use_one_default_store(self):
        sessions.clear()
        tok = sessions.create("bo")
        self.assertEqual(billing.bill_owner(tok), "bill:bo")
        self.assertFalse(hasattr(sessions, "_SESSIONS") and sessions._SESSIONS)

    def test_clear_and_revoke(self):
        s = SessionStore()
        t = s.create("x")
        s.revoke(t)
        self.assertIsNone(s.user_for(t))
        t = s.create("y")
        s.clear()
        self.assertIsNone(s.user_for(t))
