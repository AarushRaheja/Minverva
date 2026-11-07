import unittest
from auth import sessions


class TestSessions(unittest.TestCase):
    def setUp(self):
        sessions.clear()

    def test_round_trip(self):
        tok = sessions.create("ann")
        self.assertEqual(sessions.user_for(tok), "ann")
        sessions.revoke(tok)
        self.assertIsNone(sessions.user_for(tok))
