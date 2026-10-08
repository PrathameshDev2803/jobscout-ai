"""Regression tests for Remember-Me persistence (run: python test_remember_me.py)."""
import json
import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from session_store import (clear_onboard_marker, create_user_session,
                           delete_user_session, get_user_session,
                           has_onboard_marker, set_onboard_marker)


class TestSessions(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.db = os.path.join(self.tmp, "sessions.db")
        self.prof = os.path.join(self.tmp, "profile.json")

    def test_create_and_validate(self):
        p = {"name": "Bhai", "skills": ["PHP"]}
        sid, exp = create_user_session(p, duration_months=3, db_path=self.db)
        self.assertTrue(sid and exp)
        got = get_user_session(sid, self.db)
        self.assertEqual(got["name"], "Bhai")

    def test_unknown_sid_returns_none(self):
        self.assertIsNone(get_user_session("nope", self.db))
        self.assertIsNone(get_user_session("", self.db))
        self.assertIsNone(get_user_session(None, self.db))

    def test_expired_sid_rejected_and_pruned(self):
        import sqlite3
        from session_store import ensure_session_db
        sid, _ = create_user_session({"name": "X"}, 1, self.db)
        past = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
        con = ensure_session_db(self.db)
        con.execute("UPDATE user_sessions SET expires_at=? WHERE sid=?", (past, sid))
        con.commit()
        con.close()
        self.assertIsNone(get_user_session(sid, self.db))

    def test_naive_datetime_expiry_tolerated(self):
        """Legacy rows without tzinfo must not kill the session."""
        import sqlite3
        from session_store import ensure_session_db
        sid, _ = create_user_session({"name": "Y"}, 1, self.db)
        naive_future = (datetime.now(timezone.utc) + timedelta(days=30)).replace(tzinfo=None).isoformat()
        con = ensure_session_db(self.db)
        con.execute("UPDATE user_sessions SET expires_at=? WHERE sid=?", (naive_future, sid))
        con.commit()
        con.close()
        got = get_user_session(sid, self.db)
        self.assertIsNotNone(got)
        self.assertEqual(got["name"], "Y")

    def test_delete_revokes(self):
        sid, _ = create_user_session({"name": "Z"}, 1, self.db)
        delete_user_session(sid, self.db)
        self.assertIsNone(get_user_session(sid, self.db))

    def test_marker_roundtrip(self):
        self.assertFalse(has_onboard_marker(self.prof))
        with open(self.prof, "w", encoding="utf-8") as f:
            json.dump({"name": "Bhai", "skills": ["PHP"]}, f)
        self.assertFalse(has_onboard_marker(self.prof))
        set_onboard_marker(self.prof)
        self.assertTrue(has_onboard_marker(self.prof))
        # data preserved
        with open(self.prof, encoding="utf-8") as f:
            self.assertEqual(json.load(f)["name"], "Bhai")
        clear_onboard_marker(self.prof)
        self.assertFalse(has_onboard_marker(self.prof))
        with open(self.prof, encoding="utf-8") as f:
            self.assertEqual(json.load(f)["name"], "Bhai")


if __name__ == "__main__":
    unittest.main(verbosity=2)
