"""Unit tests for ui.link_review module and profile other_links integration."""
import copy
import json
import unittest
from unittest.mock import patch, MagicMock
import requests

from core.url_utils import normalize_url
from ui.link_review import (
    build_link_rows,
    apply_link_rows,
    check_link_status,
    ApplyResult,
)
from app import merge_profiles


class TestLinkReview(unittest.TestCase):
    """Test suite covering the 10 link review and verification requirements."""

    def setUp(self):
        self.sample_profile = {
            "name": "Jane Doe",
            "email": "jane@example.com",
            "phone": "+1-555-0100",
            "linkedin": "https://linkedin.com/in/janedoe",
            "github": "https://github.com/janedoe",
            "portfolio": "https://janedoe.dev",
            "base_role": "Full-Stack Developer",
            "projects": [
                {
                    "name": "TaskFlow",
                    "repo_url": "https://github.com/janedoe/taskflow",
                    "live_url": "https://taskflow.live",
                    "extra_live_urls": ["https://taskflow-demo.fly.dev"],
                }
            ],
            "other_links": ["https://blog.janedoe.dev"],
            "unreviewed_links": [
                {"url": "https://unknown.com/spec", "reason": "unmatched domain"}
            ],
        }

    def test_1_build_link_rows_all_sources(self):
        """1. build_link_rows includes slot links, project links, extra_live_urls, other_links and unreviewed_links with reasons."""
        rows = build_link_rows(self.sample_profile)
        types = [r["type"] for r in rows]
        sources = [r["source"] for r in rows]
        belongs = [r["belongs_to"] for r in rows]
        urls = [r["url"] for r in rows]

        # Verify slots
        self.assertIn("linkedin", types)
        self.assertIn("github", types)
        self.assertIn("portfolio", types)
        self.assertIn("https://linkedin.com/in/janedoe", urls)
        self.assertIn("https://github.com/janedoe", urls)
        self.assertIn("https://janedoe.dev", urls)

        # Verify project links
        self.assertIn("https://github.com/janedoe/taskflow", urls)
        self.assertIn("https://taskflow.live", urls)
        self.assertIn("https://taskflow-demo.fly.dev", urls)
        taskflow_rows = [r for r in rows if r["belongs_to"] == "TaskFlow"]
        self.assertEqual(len(taskflow_rows), 3)

        # Verify other_links
        other_row = next((r for r in rows if r["url"] == "https://blog.janedoe.dev"), None)
        self.assertIsNotNone(other_row)
        self.assertEqual(other_row["type"], "other")

        # Verify unreviewed_links with reason
        unrev_row = next((r for r in rows if r["url"] == "https://unknown.com/spec"), None)
        self.assertIsNotNone(unrev_row)
        self.assertEqual(unrev_row["type"], "unassigned")
        self.assertEqual(unrev_row["reason"], "unmatched domain")

    def test_2_missing_linkedin_produces_empty_editable_row(self):
        """2. Missing LinkedIn produces an empty editable row."""
        p = copy.deepcopy(self.sample_profile)
        p["linkedin"] = ""
        rows = build_link_rows(p)

        li_rows = [r for r in rows if r["type"] == "linkedin"]
        self.assertEqual(len(li_rows), 1)
        self.assertEqual(li_rows[0]["url"], "")
        self.assertEqual(li_rows[0]["belongs_to"], "Profile")
        self.assertTrue(li_rows[0]["keep"])

    def test_3_duplicate_urls_differing_by_scheme_or_slash_appear_once(self):
        """3. Duplicate URLs differing by www / trailing slash / scheme appear once."""
        p = {
            "linkedin": "",
            "github": "",
            "portfolio": "https://www.example.com/",
            "projects": [],
            "other_links": ["http://example.com"],
            "unreviewed_links": [],
        }
        rows = build_link_rows(p)
        example_rows = [r for r in rows if "example.com" in r["url"]]
        self.assertEqual(len(example_rows), 1)

    def test_4_apply_link_rows_editing_project_repo_updates_project_only(self):
        """4. apply_link_rows: editing a project's repo URL updates that project only."""
        p = {
            "projects": [
                {"name": "Proj A", "repo_url": "https://github.com/user/a", "live_url": ""},
                {"name": "Proj B", "repo_url": "https://github.com/user/b", "live_url": ""},
            ]
        }
        rows = build_link_rows(p)
        # Edit Proj A repo row
        for r in rows:
            if r["belongs_to"] == "Proj A" and r["type"] == "repo":
                r["url"] = "https://github.com/user/a-v2"

        updated, errors = apply_link_rows(p, rows)
        self.assertEqual(len(errors), 0)
        self.assertEqual(updated["projects"][0]["repo_url"], "https://github.com/user/a-v2")
        self.assertEqual(updated["projects"][1]["repo_url"], "https://github.com/user/b")

    def test_5_apply_link_rows_keep_false_removes_link(self):
        """5. apply_link_rows: keep=False removes the link from the right place."""
        p = copy.deepcopy(self.sample_profile)
        rows = build_link_rows(p)

        # Uncheck keep on github and extra_live_urls
        for r in rows:
            if r["type"] == "github":
                r["keep"] = False
            if r["url"] == "https://taskflow-demo.fly.dev":
                r["keep"] = False

        updated, errors = apply_link_rows(p, rows)
        self.assertEqual(len(errors), 0)
        self.assertEqual(updated["github"], "")
        self.assertEqual(updated["projects"][0]["live_url"], "https://taskflow.live")
        self.assertNotIn("https://taskflow-demo.fly.dev", updated["projects"][0].get("extra_live_urls", []))
        self.assertEqual(updated["linkedin"], "https://linkedin.com/in/janedoe")

    def test_6_apply_link_rows_invalid_or_javascript_rejected(self):
        """6. apply_link_rows: invalid or javascript: URL is rejected and reported, profile unchanged."""
        p = copy.deepcopy(self.sample_profile)
        rows = build_link_rows(p)

        # Inject dangerous javascript URL
        rows.append({
            "url": "javascript:alert('xss')",
            "type": "other",
            "belongs_to": "Profile",
            "source": "Other",
            "keep": True,
        })

        updated, errors = apply_link_rows(p, rows)
        self.assertGreater(len(errors), 0)
        self.assertIn("javascript:alert('xss')", errors[0])
        # Profile must be unchanged
        self.assertEqual(updated["linkedin"], self.sample_profile["linkedin"])
        self.assertEqual(updated["other_links"], self.sample_profile["other_links"])

    def test_7_reassign_unassigned_link_to_project(self):
        """7. Reassigning an unassigned link to a project removes it from unreviewed_links and sets repo_url or live_url correctly."""
        p = {
            "projects": [{"name": "MyEngine", "repo_url": "", "live_url": ""}],
            "unreviewed_links": [
                {"url": "https://github.com/org/my-engine-repo", "reason": "Ambiguous repo"}
            ],
        }
        rows = build_link_rows(p)
        unrev = next(r for r in rows if r["type"] == "unassigned")
        unrev["belongs_to"] = "MyEngine"
        unrev["type"] = "repo"

        updated, errors = apply_link_rows(p, rows)
        self.assertEqual(len(errors), 0)
        self.assertEqual(updated["projects"][0]["repo_url"], "https://github.com/org/my-engine-repo")
        self.assertEqual(len(updated["unreviewed_links"]), 0)

    @patch("requests.head")
    def test_8_check_link_status_responses(self, mock_head):
        """8. check_link_status: 200 -> OK, timeout -> Not reachable, 403 and linkedin.com -> Couldn't check."""
        # Case A: 200 OK
        mock_resp_200 = MagicMock()
        mock_resp_200.status_code = 200
        mock_head.return_value = mock_resp_200
        self.assertEqual(check_link_status("https://example.com/ok"), "OK")

        # Case B: Timeout -> Not reachable
        mock_head.side_effect = requests.exceptions.Timeout("Connection timed out")
        self.assertEqual(check_link_status("https://slow-site.com"), "Not reachable")

        # Case C: 403 -> Couldn't check
        mock_head.side_effect = None
        mock_resp_403 = MagicMock()
        mock_resp_403.status_code = 403
        mock_head.return_value = mock_resp_403
        self.assertEqual(check_link_status("https://protected-site.com"), "Couldn't check")

        # Case D: linkedin.com blocked domain -> Couldn't check (zero requests made)
        mock_head.reset_mock()
        res = check_link_status("https://www.linkedin.com/in/someone")
        self.assertEqual(res, "Couldn't check")
        mock_head.assert_not_called()

    def test_9_other_links_survives_merge_and_save_load_round_trip(self):
        """9. other_links survives a profile save/load round trip and merge_profiles."""
        existing = {
            "name": "Jane",
            "other_links": ["https://blog.janedoe.dev"],
        }
        incoming = {
            "name": "Jane",
            "other_links": ["https://notes.janedoe.dev"],
        }
        merged = merge_profiles(existing, incoming)
        self.assertIn("https://blog.janedoe.dev", merged["other_links"])
        self.assertIn("https://notes.janedoe.dev", merged["other_links"])

        # Empty incoming other_links does not erase existing
        merged_empty = merge_profiles(existing, {"other_links": []})
        self.assertEqual(merged_empty["other_links"], ["https://blog.janedoe.dev"])

        # JSON round-trip
        dumped = json.dumps(merged)
        loaded = json.loads(dumped)
        self.assertEqual(loaded["other_links"], merged["other_links"])

    def test_10_existing_no_network_extraction_test(self):
        """10. Existing no-network extraction test still passes."""
        from test_project_links import TestProjectExtraction
        suite = unittest.TestSuite()
        suite.addTest(TestProjectExtraction("test_no_network_fetch"))
        runner = unittest.TextTestRunner()
        result = runner.run(suite)
        self.assertTrue(result.wasSuccessful())


if __name__ == "__main__":
    unittest.main()
