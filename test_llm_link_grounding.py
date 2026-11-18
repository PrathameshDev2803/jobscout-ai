"""Unit tests for Gemini LLM social link grounding & hallucination prevention.
Verifies all 6 required behaviors:
1. LLM returns an ungrounded LinkedIn URL -> rejected.
2. LLM returns a URL matching verified link differing by www/trailing slash/scheme/case -> accepted.
3. LLM returns a GitHub repo URL for github slot -> rejected.
4. Heuristic already found a LinkedIn -> heuristic value kept.
5. LLM returns javascript: or >250 char URL -> rejected.
6. All three slots grounded -> all accepted.
"""
import json
import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import app as A
from core.url_utils import is_url_grounded, is_valid_slot_shape, normalize_url, sanitize_url


class TestLLMLinkGrounding(unittest.TestCase):

    def test_1_ungrounded_linkedin_rejected(self):
        """1. LLM returns a LinkedIn URL not present in links or text -> rejected, profile['linkedin'] stays ''."""
        text = ("Jane Doe\nFull Stack Developer\nEmail: jane@example.com\n"
                "Skills: Python, Django, PostgreSQL\nExperience: 2 years building web apps.\n"
                "Education: BCA, 2023.")
        payload = json.dumps({
            "skills": ["Python"],
            "base_role": "Full Stack Developer",
            "search_terms": ["Python Developer"],
            "experience_years": 2.0,
            "linkedin": "https://www.linkedin.com/in/hallucinated-user",
            "github": "",
            "portfolio": ""
        })
        with patch.object(A, "call_gemini_api", return_value=payload):
            p = A.parse_resume_to_profile(text, api_key="test_key", links=[])
        self.assertEqual(p["linkedin"], "")
        self.assertFalse(is_url_grounded(
            "https://www.linkedin.com/in/hallucinated-user",
            verified_links=[],
            resume_text=text,
            slot="linkedin"
        ))

    def test_2_normalized_link_accepted(self):
        """2. LLM returns a URL that matches a verified link only differing by www / trailing slash / scheme / case -> accepted."""
        verified = ["https://linkedin.com/in/janedoe"]
        text = "Jane Doe\nCheck my profile on LinkedIn\nSkills: Python, Django\nExperience: 2 years."
        payload = json.dumps({
            "skills": ["Python"],
            "base_role": "Software Engineer",
            "search_terms": ["Software Engineer"],
            "experience_years": 2.0,
            "linkedin": "http://www.LINKEDIN.com/in/janedoe/",
            "github": "",
            "portfolio": ""
        })
        with patch.object(A, "call_gemini_api", return_value=payload):
            p = A.parse_resume_to_profile(text, api_key="test_key", links=verified, classified_links={})
        self.assertTrue(p["linkedin"].startswith("http"))
        self.assertEqual(normalize_url(p["linkedin"]), "linkedin.com/in/janedoe")
        self.assertTrue(is_url_grounded(
            "http://www.LINKEDIN.com/in/janedoe/",
            verified_links=verified,
            resume_text="",
            slot="linkedin"
        ))

    def test_3_github_repo_rejected_for_github_slot(self):
        """3. LLM returns a GitHub repo URL for the 'github' slot -> rejected."""
        text = ("Jane Doe\n"
                "Projects:\n"
                "Alpha: https://github.com/janedoe/my-awesome-repo\n"
                "Tool: https://github.com/org/external-tool\n"
                "Skills: Python\nExperience: 2 years.")
        verified = ["https://github.com/janedoe/my-awesome-repo", "https://github.com/org/external-tool"]
        payload = json.dumps({
            "skills": ["Python"],
            "base_role": "Python Developer",
            "search_terms": ["Python Developer"],
            "experience_years": 2.0,
            "linkedin": "",
            "github": "https://github.com/janedoe/my-awesome-repo",
            "portfolio": ""
        })
        with patch.object(A, "call_gemini_api", return_value=payload):
            p = A.parse_resume_to_profile(text, api_key="test_key", links=verified)
        self.assertEqual(p["github"], "")
        self.assertFalse(is_valid_slot_shape("github", "https://github.com/janedoe/my-awesome-repo"))
        self.assertFalse(is_url_grounded(
            "https://github.com/janedoe/my-awesome-repo",
            verified_links=verified,
            resume_text=text,
            slot="github"
        ))

    def test_4_heuristic_already_found_linkedin_kept(self):
        """4. Heuristic already found a LinkedIn and LLM returns a different one -> heuristic value kept."""
        text = "Jane Doe\nLinkedIn: https://www.linkedin.com/in/real-candidate\nSkills: Python\nExperience: 2 years."
        verified = ["https://www.linkedin.com/in/real-candidate"]
        payload = json.dumps({
            "skills": ["Python"],
            "base_role": "Python Developer",
            "search_terms": ["Python Developer"],
            "experience_years": 2.0,
            "linkedin": "https://www.linkedin.com/in/other-candidate",
            "github": "",
            "portfolio": ""
        })
        with patch.object(A, "call_gemini_api", return_value=payload):
            p = A.parse_resume_to_profile(text, api_key="test_key", links=verified)
        self.assertEqual(p["linkedin"], "https://www.linkedin.com/in/real-candidate")

    def test_5_malicious_or_oversized_url_rejected(self):
        """5. LLM returns a javascript: or >250 char URL -> rejected."""
        text = "Jane Doe\nSoftware Engineer\nSkills: Python\nExperience: 2 years."
        # Subtest A: javascript: scheme
        payload_js = json.dumps({
            "skills": ["Python"],
            "base_role": "Python Developer",
            "search_terms": ["Python Developer"],
            "experience_years": 2.0,
            "linkedin": "javascript:alert(1)",
            "github": "",
            "portfolio": ""
        })
        with patch.object(A, "call_gemini_api", return_value=payload_js):
            p = A.parse_resume_to_profile(text, api_key="test_key", links=[])
        self.assertEqual(p["linkedin"], "")
        self.assertFalse(is_url_grounded("javascript:alert(1)", verified_links=[], resume_text=text, slot="linkedin"))

        # Subtest B: > 250 characters
        oversized = "https://linkedin.com/in/" + "a" * 250
        payload_long = json.dumps({
            "skills": ["Python"],
            "base_role": "Python Developer",
            "search_terms": ["Python Developer"],
            "experience_years": 2.0,
            "linkedin": oversized,
            "github": "",
            "portfolio": ""
        })
        with patch.object(A, "call_gemini_api", return_value=payload_long):
            p2 = A.parse_resume_to_profile(text, api_key="test_key", links=[])
        self.assertEqual(p2["linkedin"], "")
        self.assertFalse(is_url_grounded(oversized, verified_links=[], resume_text=text, slot="linkedin"))

    def test_6_all_three_slots_grounded_accepted(self):
        """6. All three slots grounded -> all accepted."""
        text = ("Jane Doe\n"
                "Profile links: Check my work.\n"
                "Skills: Python, Django, React\n"
                "Experience: 2 years of experience.")
        verified = [
            "https://linkedin.com/in/janedoe",
            "https://github.com/janedoe",
            "https://janedoe.dev"
        ]
        payload = json.dumps({
            "skills": ["Python"],
            "base_role": "Full Stack Developer",
            "search_terms": ["Full Stack Developer"],
            "experience_years": 2.0,
            "linkedin": "https://www.linkedin.com/in/janedoe/",
            "github": "https://github.com/janedoe/",
            "portfolio": "https://janedoe.dev"
        })
        with patch.object(A, "call_gemini_api", return_value=payload):
            p = A.parse_resume_to_profile(text, api_key="test_key", links=verified, classified_links={})
        self.assertEqual(normalize_url(p["linkedin"]), "linkedin.com/in/janedoe")
        self.assertEqual(normalize_url(p["github"]), "github.com/janedoe")
        self.assertEqual(normalize_url(p["portfolio"]), "janedoe.dev")
        self.assertTrue(is_url_grounded("https://www.linkedin.com/in/janedoe/", verified_links=verified, resume_text="", slot="linkedin"))
        self.assertTrue(is_url_grounded("https://github.com/janedoe/", verified_links=verified, resume_text="", slot="github"))
        self.assertTrue(is_url_grounded("https://janedoe.dev", verified_links=verified, resume_text="", slot="portfolio"))

    def test_grounded_via_resume_text_when_links_empty(self):
        """Verifies (b): URL present in resume text is grounded even when verified_links is empty."""
        text = ("Jane Doe\n"
                "Find my code at github.com/janedoe\n"
                "Skills: Python, React\n"
                "Experience: 2 years.")
        self.assertTrue(is_url_grounded("https://github.com/janedoe", verified_links=[], resume_text=text, slot="github"))
        self.assertFalse(is_url_grounded("https://github.com/imposter", verified_links=[], resume_text=text, slot="github"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
