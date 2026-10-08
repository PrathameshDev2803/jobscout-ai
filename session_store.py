"""Server-side persistent sessions + on-disk onboarding marker.

Ponytail: sid sessions live in sessions.db (gitignored) — NOT jobs.db, which is
git-tracked, so git pull/checkout can never wipe logins again.
Disk marker (_onboarded_at inside profile.json) lets a fresh browser session skip
re-upload: the resume is already on this machine, no sid needed.
Pure stdlib — safe to import from unit tests without a Streamlit runtime.
"""
import json
import os
import secrets
import sqlite3
from datetime import datetime, timedelta, timezone

BASE = os.path.dirname(os.path.abspath(__file__))
SESSION_DB = os.path.join(BASE, "sessions.db")
MARKER_KEY = "_onboarded_at"


def ensure_session_db(db_path=SESSION_DB):
    con = sqlite3.connect(db_path, timeout=30.0)
    con.execute("""CREATE TABLE IF NOT EXISTS user_sessions(
      sid TEXT PRIMARY KEY,
      user_name TEXT,
      profile_json TEXT,
      duration_months INTEGER,
      created_at TEXT,
      expires_at TEXT)""")
    con.commit()
    return con


def _parse_expiry(exp_str):
    """Tolerant ISO parse: naive timestamps assumed UTC (legacy rows)."""
    exp_dt = datetime.fromisoformat(exp_str)
    if exp_dt.tzinfo is None:
        exp_dt = exp_dt.replace(tzinfo=timezone.utc)
    return exp_dt


def create_user_session(profile, duration_months=1, db_path=SESSION_DB):
    """Generate cryptographically secure session valid for N months."""
    sid = secrets.token_urlsafe(24)
    now = datetime.now(timezone.utc)
    days = 30 * max(1, int(duration_months or 1))
    expires_at = (now + timedelta(days=days)).isoformat()
    con = ensure_session_db(db_path)
    try:
        con.execute("""
          INSERT OR REPLACE INTO user_sessions
            (sid, user_name, profile_json, duration_months, created_at, expires_at)
          VALUES (?, ?, ?, ?, ?, ?)
        """, (sid, (profile or {}).get("name", "Developer"), json.dumps(profile or {}),
              duration_months, now.isoformat(), expires_at))
        con.commit()
        # ponytail: prune dead rows on write; keeps table bounded, zero cron needed
        try:
            con.execute("DELETE FROM user_sessions WHERE expires_at < ?",
                        (now.isoformat(),))
            con.commit()
        except Exception:
            pass
    finally:
        con.close()
    return sid, expires_at


def get_user_session(sid, db_path=SESSION_DB):
    """Validate and return profile if session is active and unexpired."""
    if not sid or not isinstance(sid, str):
        return None
    try:
        con = ensure_session_db(db_path)
        try:
            row = con.execute(
                "SELECT profile_json, expires_at FROM user_sessions WHERE sid=?",
                (sid.strip(),)).fetchone()
        finally:
            con.close()
        if not row:
            return None
        prof_json, exp_str = row[0], row[1]
        if datetime.now(timezone.utc) > _parse_expiry(exp_str):
            delete_user_session(sid, db_path)
            return None
        return json.loads(prof_json)
    except Exception:
        return None


def delete_user_session(sid, db_path=SESSION_DB):
    """Revoke and delete persistent session."""
    if not sid:
        return
    try:
        con = ensure_session_db(db_path)
        try:
            con.execute("DELETE FROM user_sessions WHERE sid=?", (sid.strip(),))
            con.commit()
        finally:
            con.close()
    except Exception:
        pass


def has_onboard_marker(profile_path):
    """True if this machine already completed onboarding (resume on disk)."""
    try:
        if not os.path.exists(profile_path):
            return False
        with open(profile_path, encoding="utf-8") as f:
            return bool(json.load(f).get(MARKER_KEY))
    except Exception:
        return False


def set_onboard_marker(profile_path):
    """Stamp onboarding completion; preserves all existing profile data."""
    try:
        p = {}
        if os.path.exists(profile_path):
            with open(profile_path, encoding="utf-8") as f:
                p = json.load(f)
        p[MARKER_KEY] = datetime.now(timezone.utc).isoformat()
        with open(profile_path, "w", encoding="utf-8") as f:
            json.dump(p, f, indent=2)
    except Exception:
        pass


def clear_onboard_marker(profile_path):
    """Forget onboarding (Switch profile flow); keeps resume data intact."""
    try:
        if not os.path.exists(profile_path):
            return
        with open(profile_path, encoding="utf-8") as f:
            p = json.load(f)
        if MARKER_KEY in p:
            del p[MARKER_KEY]
            with open(profile_path, "w", encoding="utf-8") as f:
                json.dump(p, f, indent=2)
    except Exception:
        pass
