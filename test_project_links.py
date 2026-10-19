"""Regression tests: GitHub repo vs profile classification, per-project live/demo
URL extraction + association, ambiguity review queue, merge preservation.

Importing app spawns daemon scheduler threads (established pattern — they die
at process exit; no jobs.db writes inside the test window).
"""
import copy
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import app as A


def classified_for(urls, text=""):
    return A.classify_links(list(urls), text)


class TestGithubClassification(unittest.TestCase):
    def test_profile_only(self):
        c = classified_for(["https://github.com/prathameshdev2803"])
        self.assertEqual(c["github"], "https://github.com/prathameshdev2803")
        self.assertEqual(c["repos"], [])

    def test_repo_retained_and_distinguished(self):
        c = classified_for(["https://github.com/u/alpha"])
        self.assertEqual(c["repos"], ["https://github.com/u/alpha"])
        self.assertEqual(c["github"], "https://github.com/u")  # derived, single owner
        self.assertNotEqual(c["github"], c["repos"][0])

    def test_multiple_repos_single_owner(self):
        c = classified_for(["https://github.com/u/alpha", "https://github.com/u/beta"])
        self.assertEqual(len(c["repos"]), 2)
        self.assertEqual(c["github"], "https://github.com/u")

    def test_multi_owner_no_derivation(self):
        c = classified_for(["https://github.com/u/alpha", "https://github.com/org/tool"])
        self.assertEqual(len(c["repos"]), 2)
        self.assertEqual(c["github"], "")  # never invent across owners/orgs

    def test_explicit_profile_wins(self):
        c = classified_for(["https://github.com/org/tool", "https://github.com/u"])
        self.assertEqual(c["github"], "https://github.com/u")

    def test_reserved_subpage_ignored(self):
        c = classified_for(["https://github.com/u/pulls", "https://github.com/features"])
        self.assertEqual(c["repos"], [])
        self.assertEqual(c["github"], "")

    def test_git_suffix_normalized(self):
        c = classified_for(["https://github.com/u/alpha.git"])
        self.assertEqual(c["repos"], ["https://github.com/u/alpha"])

    def test_repos_excluded_from_portfolio(self):
        c = classified_for(["https://github.com/u/alpha"], "")
        self.assertNotIn("https://github.com/u/alpha",
                         [c["portfolio"]] + list(c["other_links"]))


RESUME_LABELED = """Prathamesh Jadhav
Full-Stack Developer | Mumbai
prathamesh@example.com | +91 93266 71284
github.com/prathameshdev2803 | linkedin.com/in/prathamesh-jadhav

PROJECTS
Expense Tracker — PHP & MySQL
GitHub: https://github.com/prathameshdev2803/expense-tracker
Live: https://expense.example.com
• Income/expense management with CRUD operations.
NoteStack — React / Node
GitHub: https://github.com/prathameshdev2803/notestack
• Rich-text notes with backend persistence.

EDUCATION
BCA, Chandrabhan Sharma College, 2024.
"""

RESUME_AMBIGUOUS = """Prathamesh Jadhav
github.com/prathameshdev2803

PROJECTS
Alpha Tools — PHP
• Does things well and reliably.
Beta Dash — React
• Dashboards with charts and filters.
https://stranger.example.com/widgets

EDUCATION
BCA, 2024.
"""

RESUME_NO_SECTION = """Prathamesh Jadhav
prathamesh@example.com

WORK EXPERIENCE
Traction Shastra - Web Developer, Nov 2025 - Present
• Build end-to-end web features with PHP and MySQL.
See my work at https://github.com/prathameshdev2803/shop
"""


def parse(text, links):
    return A.parse_resume_heuristics(text, links=list(links))


class TestProjectExtraction(unittest.TestCase):
    def test_labeled_association(self):
        links = ["https://github.com/prathameshdev2803",
                 "https://github.com/prathameshdev2803/expense-tracker",
                 "https://expense.example.com",
                 "https://github.com/prathameshdev2803/notestack",
                 "https://linkedin.com/in/prathamesh-jadhav"]
        p = parse(RESUME_LABELED, links)
        by_name = {e["name"]: e for e in p["projects"]}
        self.assertIn("Expense Tracker", by_name)
        exp = by_name["Expense Tracker"]
        self.assertEqual(exp["repo_url"], "https://github.com/prathameshdev2803/expense-tracker")
        self.assertEqual(exp["live_url"], "https://expense.example.com")
        self.assertEqual(exp["stack"], "PHP & MySQL")
        self.assertTrue(any("CRUD" in b for b in exp["bullets"]))
        ns = by_name["NoteStack"]
        self.assertEqual(ns["repo_url"], "https://github.com/prathameshdev2803/notestack")
        self.assertEqual(ns["live_url"], "")

    def test_sameline_bare_url(self):
        text = ("Prathamesh Jadhav\n\nPROJECTS\n"
                "Gamma App https://github.com/prathameshdev2803/gamma\n"
                "• Gamma does things.\n\nEDUCATION\nBCA.")
        p = parse(text, ["https://github.com/prathameshdev2803/gamma"])
        self.assertEqual(len(p["projects"]), 1)
        self.assertEqual(p["projects"][0]["repo_url"], "https://github.com/prathameshdev2803/gamma")

    def test_ambiguous_goes_unreviewed(self):
        p = parse(RESUME_AMBIGUOUS, ["https://github.com/prathameshdev2803",
                                     "https://stranger.example.com/widgets"])
        self.assertEqual(len(p["projects"]), 2)  # names+bullets still captured
        attached = [e.get("live_url", "") for e in p["projects"]]
        self.assertNotIn("https://stranger.example.com/widgets", attached)
        flagged = [u["url"] for u in p.get("unreviewed_links", [])]
        self.assertIn("https://stranger.example.com/widgets", flagged)
        self.assertTrue(all(u.get("reason") for u in p["unreviewed_links"]))

    def test_mixed_clickable_visible_dedup(self):
        # same repo as clickable annotation AND visible text (with trailing period)
        text = ("Prathamesh Jadhav\n\nPROJECTS\n"
                "Delta — Go\nGitHub: https://github.com/prathameshdev2803/delta.\n"
                "• Delta bullet here.\n\nEDUCATION\nBCA.")
        p = parse(text, ["https://github.com/prathameshdev2803/delta",
                         "https://github.com/prathameshdev2803/delta"])
        self.assertEqual(len(p["projects"]), 1)
        self.assertEqual(p["projects"][0]["repo_url"], "https://github.com/prathameshdev2803/delta")
        self.assertEqual(p.get("unreviewed_links", []), [])

    def test_multiple_live_urls_no_collapse(self):
        text = ("Prathamesh Jadhav\n\nPROJECTS\n"
                "Omega — Python\nLive: https://omega.example.com\nDemo: https://demo.example.com/omega\n"
                "• Omega bullet here for real.\n\nEDUCATION\nBCA.")
        p = parse(text, ["https://omega.example.com", "https://demo.example.com/omega"])
        self.assertEqual(len(p["projects"]), 1)
        entry = p["projects"][0]
        self.assertEqual(entry["live_url"], "https://omega.example.com")
        self.assertIn("https://demo.example.com/omega", entry.get("extra_live_urls", []))

    def test_no_section_no_bogus_entries(self):
        p = parse(RESUME_NO_SECTION, ["https://github.com/prathameshdev2803/shop"])
        self.assertEqual(p.get("projects", []), [])
        flagged = [u["url"] for u in p.get("unreviewed_links", [])]
        self.assertIn("https://github.com/prathameshdev2803/shop", flagged)

    def test_no_network_fetch(self):
        import socket
        orig = socket.socket

        def _boom(*a, **k):
            raise RuntimeError("network disabled in test")

        socket.socket = _boom
        try:
            classified_for(["https://github.com/u/alpha", "https://x.example.com/a"])
            A.extract_project_entries(RESUME_LABELED, ["https://github.com/u/alpha"])
            parse(RESUME_LABELED, ["https://github.com/u/alpha"])
        finally:
            socket.socket = orig

    def test_gemini_merge_keeps_projects(self):
        payload = ('{"skills": ["PHP"], "base_role": "PHP Developer", '
                   '"search_terms": ["PHP Developer"], "experience_years": 1, '
                   '"linkedin": "", "github": "", "portfolio": ""}')
        orig = A.call_gemini_api
        A.call_gemini_api = lambda prompt, key: payload
        try:
            p = A.parse_resume_to_profile(
                RESUME_LABELED, api_key="dummy",
                links=["https://github.com/prathameshdev2803/expense-tracker"])
        finally:
            A.call_gemini_api = orig
        names = [e["name"] for e in p.get("projects", [])]
        self.assertIn("Expense Tracker", names)


class TestProjectMergePreservation(unittest.TestCase):
    EXISTING = {
        "name": "Prathamesh Jadhav",
        "projects": [
            {"name": "Expense Tracker", "stack": "PHP & MySQL",
             "repo_url": "https://github.com/u/expense-tracker",
             "live_url": "https://expense.example.com", "bullets": ["CRUD app."]},
        ],
        "unreviewed_links": [{"url": "https://old.example.com/x", "reason": "r"}],
    }

    def test_existing_urls_survive_empty_incoming(self):
        out = A.merge_profiles(copy.deepcopy(self.EXISTING),
                               {"projects": [{"name": "Expense Tracker", "repo_url": "",
                                              "live_url": None, "bullets": []}]})
        exp = out["projects"][0]
        self.assertEqual(exp["repo_url"], "https://github.com/u/expense-tracker")
        self.assertEqual(exp["live_url"], "https://expense.example.com")

    def test_same_name_different_repo_appends(self):
        out = A.merge_profiles(copy.deepcopy(self.EXISTING),
                               {"projects": [{"name": "Expense Tracker",
                                              "repo_url": "https://github.com/u/expense-v2",
                                              "bullets": ["V2."]}]})
        repos = sorted(p.get("repo_url", "") for p in out["projects"])
        self.assertEqual(repos, ["https://github.com/u/expense-tracker",
                                 "https://github.com/u/expense-v2"])

    def test_extra_live_urls_union(self):
        out = A.merge_profiles(copy.deepcopy(self.EXISTING),
                               {"projects": [{"name": "Expense Tracker",
                                              "extra_live_urls": ["https://demo.example.com/e"]}]})
        exp = out["projects"][0]
        self.assertEqual(exp["live_url"], "https://expense.example.com")
        self.assertIn("https://demo.example.com/e", exp["extra_live_urls"])
        again = A.merge_profiles(out, {"projects": [{"name": "Expense Tracker",
                                                     "extra_live_urls": ["https://demo.example.com/e"]}]})
        self.assertEqual(again["projects"][0]["extra_live_urls"], exp["extra_live_urls"])

    def test_unreviewed_union_no_dup(self):
        out = A.merge_profiles(copy.deepcopy(self.EXISTING),
                               {"unreviewed_links": [
                                   {"url": "https://old.example.com/x", "reason": "r2"},
                                   {"url": "https://new.example.com/y", "reason": "r"}]})
        urls = [u["url"] for u in out["unreviewed_links"]]
        self.assertEqual(sorted(urls), ["https://new.example.com/y", "https://old.example.com/x"])
        again = A.merge_profiles(out, {"unreviewed_links": [{"url": "https://new.example.com/y",
                                                             "reason": "r"}]})
        self.assertEqual([u["url"] for u in again["unreviewed_links"]], urls)


class TestUnreviewedDedup(unittest.TestCase):
    TEXT = ("Aarav Sharma\naarav@example.com\n\nSKILLS\nPHP\n\n"
            "See https://linkedin.com/in/aarav-sharma and "
            "https://github.com/aaravsharma-dev plus https://aaravsharma.dev "
            "and https://github.com/aaravsharma-dev/shop")

    def test_classified_slots_excluded(self):
        # No PROJECTS section: profile/portfolio URLs must not re-enter review.
        p = A.parse_resume_heuristics(
            self.TEXT,
            links=["https://linkedin.com/in/aarav-sharma",
                   "https://github.com/aaravsharma-dev",
                   "https://aaravsharma.dev",
                   "https://github.com/aaravsharma-dev/shop"])
        flagged = [u["url"] for u in p.get("unreviewed_links", [])]
        self.assertNotIn("https://www.linkedin.com/in/aarav-sharma", flagged)
        self.assertNotIn("https://github.com/aaravsharma-dev", flagged)
        self.assertNotIn("https://aaravsharma.dev", flagged)

    def test_unattached_repo_stays_reviewable(self):
        # Repos have no persistent slot outside projects: keep, don't drop.
        p = A.parse_resume_heuristics(
            self.TEXT,
            links=["https://github.com/aaravsharma-dev/shop"])
        flagged = [u["url"] for u in p.get("unreviewed_links", [])]
        self.assertIn("https://github.com/aaravsharma-dev/shop", flagged)

    def test_normalized_duplicates(self):
        # Mirror the real extract_pdf flow: every visible URL is also a link candidate.
        p = A.parse_resume_heuristics(
            self.TEXT,
            links=["https://github.com/aaravsharma-dev/",
                   "https://github.com/aaravsharma-dev",
                   "https://linkedin.com/in/aarav-sharma",
                   "https://aaravsharma.dev",
                   "https://github.com/aaravsharma-dev/shop"])
        flagged = [u["url"] for u in p.get("unreviewed_links", [])]
        # slash variants collapse; stored slots excluded; slot-less repo stays reviewable
        self.assertEqual(flagged, ["https://github.com/aaravsharma-dev/shop"])

    def test_labeled_attach_still_wins(self):
        text = ("Aarav Sharma\n\nPROJECTS\nOmega — Python\n"
                "Live: https://aaravsharma.dev\n• Omega bullet here.\n\nEDUCATION\nBCA.")
        p = A.parse_resume_heuristics(text, links=["https://aaravsharma.dev"])
        projs = {e["name"]: e for e in p.get("projects", [])}
        self.assertEqual(projs.get("Omega", {}).get("live_url"), "https://aaravsharma.dev")


if __name__ == "__main__":
    unittest.main(verbosity=2)
