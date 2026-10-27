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

    def test_indeed_vjk_extraction_success(self):
        # Verifies Issue 3: Indeed vjk= URLs route to GraphQL and return structured job
        try:
            import jobspy  # noqa: F401
        except ImportError:
            self.skipTest("optional python-jobspy dependency not installed")
        graphql_resp = {
            "data": {
                "jobData": {
                    "results": [{
                        "job": {
                            "key": "713f08235b08fad7",
                            "title": "Full Stack Developer",
                            "employer": {"name": "IRIS Business Services Ltd"},
                            "location": {"formatted": {"short": "Navi Mumbai, Maharashtra"}},
                            "description": {"text": "Role at IRIS Business Services..."},
                            "recruit": {"viewJobUrl": "https://in.indeed.com/viewjob?jk=713f08235b08fad7"}
                        }
                    }]
                }
            }
        }
        with patch.object(fetch.requests, "post",
                          return_value=FakeResp(payload=graphql_resp)):
            j = fetch_job_from_url("https://in.indeed.com/?from=jobsearch-empty-whatwhere&vjk=713f08235b08fad7")
        self.assertIsNotNone(j)
        self.assertEqual(j["title"], "Full Stack Developer")
        self.assertEqual(j["company"], "IRIS Business Services Ltd")
        self.assertEqual(j["location"], "Navi Mumbai, Maharashtra")
        self.assertEqual(j["url"], "https://in.indeed.com/viewjob?jk=713f08235b08fad7")
        self.assertEqual(j["source"], "indeed")

    def test_indeed_search_url_raises_validation_error(self):
        # Verifies Issue 3: Indeed search/results page without job key is rejected with clear message
        with self.assertRaises(ValueError) as ctx:
            fetch_job_from_url("https://in.indeed.com/jobs?q=developer&l=mumbai")
        self.assertIn("search or category page", str(ctx.exception).lower())

    def test_indeed_blocked_or_expired_raises_runtime_error(self):
        # Verifies Issue 3: Indeed GraphQL failure never falls through to requests.get()
        with patch.object(fetch.requests, "post", side_effect=Exception("API limit")):
            with self.assertRaises(RuntimeError) as ctx:
                fetch_job_from_url("https://in.indeed.com/viewjob?jk=713f08235b08fad7")
            self.assertIn("paste job description", str(ctx.exception).lower())

    def test_generic_url_http_403_raises_actionable_error(self):
        # Verifies Issue 3: HTTP 403 produces clean actionable error message
        mock_resp = FakeResp(status=403)
        with patch.object(fetch.requests, "get",
                          side_effect=fetch.requests.exceptions.HTTPError(response=mock_resp)):
            with self.assertRaises(RuntimeError) as ctx:
                fetch_job_from_url("https://example.com/job/123")
            self.assertIn("403", str(ctx.exception))
            self.assertIn("paste job description", str(ctx.exception).lower())


class TestDetectedJobFlowArchitecture(unittest.TestCase):
    def setUp(self):
        with open(os.path.join(os.path.dirname(__file__), "app.py"), "r", encoding="utf-8") as f:
            self.app_src = f.read()

    def test_detected_job_not_inside_platforms_tab_branch(self):
        # Verifies Issue 1: Detected Job & Tailoring Output Area is NOT indented under if _ft_idx == 2:
        self.assertIn('    if _ft_idx == 2:\n', self.app_src)
        self.assertIn('    # Detected Job & Tailoring Output Area\n    qj = st.session_state.get("quick_job")', self.app_src)

    def test_analysis_loader_implementation_present(self):
        # Verifies Issue 2: Polished emerald loading experience function and CSS are wired
        self.assertIn('def render_analysis_loader(', self.app_src)
        self.assertIn('.analysis-loader-box', self.app_src)
        self.assertIn('.emerald-ring-spinner', self.app_src)
        self.assertIn('@media (prefers-reduced-motion: reduce)', self.app_src)

    def test_duplicate_submission_protection_wired(self):
        # Verifies Issue 2: Button disables during processing and resets in finally block
        self.assertIn('is_analyzing_jd', self.app_src)
        self.assertIn('is_fetching_link', self.app_src)
        self.assertIn('finally:\n                        st.session_state["is_analyzing_jd"] = False', self.app_src)


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
