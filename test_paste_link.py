"""Regression tests for Paste Link URL import + standalone JD matching
(run: python test_paste_link.py). No network: all HTTP is mocked."""
import os
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import fetch
from fetch import db, fetch_job_from_url, save
from matcher import compute_match


class FakeResp:
    def __init__(self, status=200, text="", payload=None):
        self.status_code = status
        self.text = text
        self._payload = payload or {}

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise Exception(f"HTTP {self.status_code}")


def _profile():
    return {
        "base_role": "Full Stack Developer",
        "skills": ["PHP", "Laravel", "MySQL", "JavaScript"],
        "location": {"city": "Mumbai", "state": "Maharashtra", "country": "India"},
        "experience_years": 2,
        "resume_text": "PHP Laravel developer with MySQL and JavaScript experience.",
    }


class TestFetchJobFromUrl(unittest.TestCase):
    def test_empty_url_returns_none(self):
        self.assertIsNone(fetch_job_from_url(""))
        self.assertIsNone(fetch_job_from_url("   "))
        self.assertIsNone(fetch_job_from_url(None))

    def test_lever_api_success(self):
        payload = {"text": "Backend Engineer",
                   "categories": {"location": "Bangalore"},
                   "descriptionPlain": "Build APIs with Node.",
                   "company": "Acme"}
        with patch.object(fetch.requests, "get",
                          return_value=FakeResp(payload=payload)):
            j = fetch_job_from_url("https://jobs.lever.co/acme/abc-123")
        self.assertEqual(j["title"], "Backend Engineer")
        self.assertEqual(j["location"], "Bangalore")
        self.assertIn("Build APIs", j["description"])
        self.assertEqual(j["source"], "lever")

    def test_greenhouse_api_success(self):
        payload = {"title": "PHP Developer",
                   "location": {"name": "Remote"},
                   "content": "<p>Laravel + MySQL role</p>"}
        with patch.object(fetch.requests, "get",
                          return_value=FakeResp(payload=payload)):
            j = fetch_job_from_url("https://boards.greenhouse.io/acme/jobs/42")
        self.assertEqual(j["title"], "PHP Developer")
        self.assertNotIn("<p>", j["description"])
        self.assertIn("Laravel", j["description"])
        self.assertEqual(j["source"], "greenhouse")

    def test_smartrecruiters_api_success(self):
        payload = {"name": "Frontend Dev",
                   "company": {"name": "Acme"},
                   "location": {"city": "Pune"},
                   "jobAd": {"sections": {"job": {"text": "<b>React role</b>"}}}}
        with patch.object(fetch.requests, "get",
                          return_value=FakeResp(payload=payload)):
            j = fetch_job_from_url("https://jobs.smartrecruiters.com/Acme/abc123")
        self.assertEqual(j["title"], "Frontend Dev")
        self.assertEqual(j["company"], "Acme")
        self.assertEqual(j["source"], "smartrecruiters")

    def test_generic_html_fallback(self):
        html_page = ("<html><head><title>Senior PHP Developer - Indeed</title></head>"
                     "<body><script>var x=1;</script><h1>Job</h1>"
                     "<p>Laravel, MySQL, 2 years experience</p></body></html>")
        with patch.object(fetch.requests, "get",
                          return_value=FakeResp(text=html_page)):
            j = fetch_job_from_url("https://example.com/careers/123")
        self.assertEqual(j["title"], "Senior PHP Developer")
        self.assertNotIn("var x", j["description"])
        self.assertIn("Laravel", j["description"])
        self.assertEqual(j["source"], "manual")

    def test_inaccessible_page_raises_for_fallback(self):
        # App catches this and shows manual-JD fallback; the import must not
        # silently return a bogus job.
        with patch.object(fetch.requests, "get",
                          side_effect=Exception("blocked")):
            with self.assertRaises(Exception):
                fetch_job_from_url("https://example.com/nope")


class TestStandaloneMatching(unittest.TestCase):
    def test_manual_jd_matches_without_db_record(self):
        job = {"title": "PHP Laravel Developer", "company": "Acme",
               "location": "Mumbai, India",
               "description": "Need PHP, Laravel, MySQL, 1-3 years experience.",
               "url": "#", "source": "manual-jd"}
        m = compute_match(_profile(), job)
        self.assertIn("match_score", m)
        self.assertIn("category", m)
        self.assertIn("eligible", m)
        self.assertGreaterEqual(m["match_score"], 0)


class TestSingleSave(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.orig_db = fetch.DB
        fetch.DB = os.path.join(self.tmp, "jobs.db")

    def tearDown(self):
        fetch.DB = self.orig_db

    def test_save_single_and_dedup(self):
        con = db()
        row = {"title": "Dev", "company": "Acme", "location": "Remote",
               "description": "PHP role", "url": "https://example.com/j/1",
               "source": "manual-jd", "posted_at": ""}
        self.assertEqual(save(con, [row]), 1)
        save(con, [row])  # INSERT OR IGNORE dedup (total_changes is cumulative)
        n = con.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
        self.assertEqual(n, 1)
        got = con.execute("SELECT title,source FROM jobs").fetchone()
        self.assertEqual(tuple(got), ("Dev", "manual-jd"))
        con.close()

    def test_save_skips_empty_url(self):
        con = db()
        self.assertEqual(save(con, [{"title": "x", "url": ""}]), 0)
        con.close()


if __name__ == "__main__":
    unittest.main(verbosity=2)
