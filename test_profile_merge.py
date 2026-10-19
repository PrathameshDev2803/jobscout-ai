"""Regression tests: resume-upload merge must never wipe stored profile data.

Covers save_active_profile(merge=True) contract via the pure merge_profiles()
plus end-to-end tmp-disk checks. Importing app spawns daemon scheduler threads
(proven harmless — they die at process exit, no jobs.db writes in test window).
"""
import copy
import inspect
import json
import os
import sys
import tempfile
import unittest
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import app as A


EXISTING = {
    "name": "Prathamesh Jadhav",
    "email": "prathameshjadhav2803@gmail.com",
    "phone": "+91 93266 71284",
    "linkedin": "https://www.linkedin.com/in/prathamesh-jadhav",
    "github": "github.com/PrathameshDev2803",
    "portfolio": "",
    "base_role": "PHP Developer",
    "search_terms": ["PHP Developer", "Web Developer"],
    "skills": ["PHP", "MySQL", "Git"],
    "skills_categorized": {"Backend": "PHP, MySQL"},
    "location": {"city": "Mumbai", "state": "Maharashtra", "country": "India",
                 "preferred_regions": "Mumbai, Remote"},
    "work_preferences": {"remote": True, "hybrid": True, "onsite": True},
    "experience_years": 1,
    "experience": [{"company": "Traction Shastra", "role": "Web Developer",
                   "period": "Nov 2025 - Present", "bullets": ["Built features."]}],
    "projects": [
        {"name": "Expense Tracker", "stack": "PHP & MySQL",
         "repo_url": "https://github.com/PrathameshDev2803/Expense-Tracker",
         "bullets": ["CRUD app."]},
        {"name": "JobScout AI", "stack": "Python",
         "repo_url": "https://github.com/PrathameshDev2803/jobscout-ai",
         "live_url": "https://jobscout-dev.streamlit.app",
         "bullets": ["Job platform."]},
    ],
    "education": [{"degree": "BCA", "institution": "Chandrabhan Sharma College", "year": "2024"}],
    "additional": {"target_role": "PHP Developer", "location": "Mumbai"},
    "resume_text": "old resume text",
}

# Typical thin extraction output: scalars present, lists often empty/missing.
THIN_PARSE = {
    "name": "Prathamesh Jadhav",
    "email": "",
    "phone": None,
    "linkedin": "",
    "github": "",
    "portfolio": "",
    "base_role": "Full-Stack Developer",
    "search_terms": [],
    "skills": ["PHP", "React"],
    "skills_categorized": {},
    "location": {"city": "", "state": "", "country": ""},
    "work_preferences": {"remote": True, "hybrid": True, "onsite": True},
    "experience_years": 1.0,
    "experience": [],
    "resume_text": "new resume text",
}


class TestProfileMerge(unittest.TestCase):
    def test_projects_survive_missing_key(self):
        inc = {k: v for k, v in THIN_PARSE.items() if k != "projects"}
        # also no education key at all (parser never emits it)
        out = A.merge_profiles(copy.deepcopy(EXISTING), inc)
        self.assertEqual(len(out["projects"]), 2)
        self.assertEqual(len(out["education"]), 1)

    def test_projects_survive_empty_list(self):
        inc = dict(THIN_PARSE, projects=[], education=[], experience=[])
        out = A.merge_profiles(copy.deepcopy(EXISTING), inc)
        self.assertEqual(out["projects"], EXISTING["projects"])
        self.assertEqual(out["education"], EXISTING["education"])
        self.assertEqual(out["experience"], EXISTING["experience"])

    def test_urls_survive_missing_incoming(self):
        inc = {"projects": [
            {"name": "expense tracker",  # case-insensitive same project
             "stack": "PHP & MySQL & JS",  # genuine update applies
             "repo_url": "", "live_url": None, "bullets": []},
        ]}
        out = A.merge_profiles(copy.deepcopy(EXISTING), inc)
        exp = [p for p in out["projects"] if p["name"] == "Expense Tracker"][0]
        self.assertEqual(exp["repo_url"], "https://github.com/PrathameshDev2803/Expense-Tracker")
        self.assertEqual(exp["stack"], "PHP & MySQL & JS")
        # live url on the other project untouched
        js = [p for p in out["projects"] if p["name"] == "JobScout AI"][0]
        self.assertEqual(js["live_url"], "https://jobscout-dev.streamlit.app")

    def test_new_valid_fields_saved(self):
        inc = {"projects": [{"name": "NoteStack", "stack": "React",
                             "repo_url": "https://github.com/u/notestack",
                             "bullets": ["Notes."]}],
               "custom_note": "hello",
               "skills": ["Laravel"]}
        out = A.merge_profiles(copy.deepcopy(EXISTING), inc)
        self.assertEqual(len(out["projects"]), 3)
        self.assertIn("Laravel", out["skills"])
        self.assertEqual(out["custom_note"], "hello")
        # existing order preserved, new appended
        self.assertEqual(out["projects"][-1]["name"], "NoteStack")

    def test_repeated_merge_idempotent(self):
        inc = {"skills": ["PHP", "React"], "search_terms": ["Web Developer", "React Developer"],
               "projects": [{"name": "Expense Tracker", "stack": "PHP & MySQL",
                             "bullets": ["CRUD app.", "New bullet."]}],
               "experience": copy.deepcopy(EXISTING["experience"])}
        once = A.merge_profiles(copy.deepcopy(EXISTING), inc)
        twice = A.merge_profiles(once, inc)
        self.assertEqual(once, twice)
        self.assertEqual(len(once["skills"]), len(set(s.lower() for s in once["skills"])))
        self.assertEqual(len(once["projects"]), 2)

    def test_scalar_and_years_rules(self):
        out = A.merge_profiles(copy.deepcopy(EXISTING),
                               {"name": "  ", "email": None, "phone": "",
                                "base_role": "Full-Stack Developer",
                                "experience_years": 0})
        self.assertEqual(out["name"], "Prathamesh Jadhav")
        self.assertEqual(out["email"], "prathameshjadhav2803@gmail.com")
        self.assertEqual(out["base_role"], "Full-Stack Developer")
        self.assertEqual(out["experience_years"], 1)
        out2 = A.merge_profiles(copy.deepcopy(EXISTING), {"experience_years": 2})
        self.assertEqual(out2["experience_years"], 2)
        out3 = A.merge_profiles(copy.deepcopy(EXISTING), {"experience_years": "N/A"})
        self.assertEqual(out3["experience_years"], 1)

    def test_nested_dict_rules(self):
        out = A.merge_profiles(copy.deepcopy(EXISTING),
                               {"location": {"city": "Pune"},
                                "work_preferences": {"onsite": False},
                                "additional": {"location": "Pune"}})
        self.assertEqual(out["location"]["city"], "Pune")
        self.assertEqual(out["location"]["state"], "Maharashtra")  # untouched keys kept
        self.assertIs(out["work_preferences"]["onsite"], False)  # explicit False wins
        self.assertIs(out["work_preferences"]["remote"], True)
        self.assertEqual(out["additional"]["target_role"], "PHP Developer")
        self.assertEqual(out["additional"]["location"], "Pune")

    def test_inputs_not_mutated(self):
        e, i = copy.deepcopy(EXISTING), copy.deepcopy(THIN_PARSE)
        A.merge_profiles(e, i)
        self.assertEqual(e, EXISTING)
        self.assertEqual(i, THIN_PARSE)

    def test_default_is_replace(self):
        sig = inspect.signature(A.save_active_profile)
        self.assertIn("merge", sig.parameters)
        self.assertIs(sig.parameters["merge"].default, False)

    def test_replace_mode_verbatim_tmp_disk(self):
        tmp = tempfile.mkdtemp()
        prof_path = os.path.join(tmp, "profile.json")
        res_path = os.path.join(tmp, "resume.txt")
        old_profile, old_resume, old_st = A.PROFILE, A.RESUME_TXT, A.st
        A.PROFILE, A.RESUME_TXT = prof_path, res_path
        A.st = SimpleNamespace(session_state={})
        try:
            thin = dict(THIN_PARSE)
            A.save_active_profile(thin)  # default replace
            with open(prof_path, encoding="utf-8") as f:
                saved = json.load(f)
            self.assertNotIn("projects", saved)  # replace keeps old behavior byte-for-byte
            self.assertEqual(saved["base_role"], "Full-Stack Developer")
        finally:
            A.PROFILE, A.RESUME_TXT, A.st = old_profile, old_resume, old_st

    def test_merge_mode_tmp_disk_end_to_end(self):
        tmp = tempfile.mkdtemp()
        prof_path = os.path.join(tmp, "profile.json")
        res_path = os.path.join(tmp, "resume.txt")
        with open(prof_path, "w", encoding="utf-8") as f:
            json.dump(copy.deepcopy(EXISTING), f)
        old_profile, old_resume, old_st = A.PROFILE, A.RESUME_TXT, A.st
        A.PROFILE, A.RESUME_TXT = prof_path, res_path
        A.st = SimpleNamespace(session_state={})
        try:
            A.save_active_profile(dict(THIN_PARSE), merge=True)
            with open(prof_path, encoding="utf-8") as f:
                saved = json.load(f)
            self.assertEqual(len(saved["projects"]), 2)  # survived
            self.assertIn("React", saved["skills"])  # unioned
            self.assertEqual(saved["base_role"], "Full-Stack Developer")  # updated
            self.assertEqual(saved["email"], "prathameshjadhav2803@gmail.com")  # kept
            with open(res_path, encoding="utf-8") as f:
                self.assertEqual(f.read(), "new resume text")
            # repeat: still no duplicates (ignore re-stamped onboard marker)
            A.save_active_profile(dict(THIN_PARSE), merge=True)
            with open(prof_path, encoding="utf-8") as f:
                saved2 = json.load(f)
            self.assertTrue(saved2.pop("_onboarded_at", None))
            saved.pop("_onboarded_at", None)
            self.assertEqual(saved, saved2)
        finally:
            A.PROFILE, A.RESUME_TXT, A.st = old_profile, old_resume, old_st

    def test_load_profile_workflow_intact(self):
        p = A.load_profile()
        self.assertIsInstance(p, dict)
        for k in ("name", "skills", "location", "search_terms"):
            self.assertIn(k, p)


if __name__ == "__main__":
    unittest.main(verbosity=2)
