"""Regression tests: manual questionnaire onboarding (no-resume path).

Covers build_manual_profile(), validate_manual_answers(), canonical-schema
compatibility with extraction output, merge preservation, and blank-city safety.
Importing app spawns daemon scheduler threads (established pattern — they die
at process exit; no jobs.db writes inside the test window).
"""
import copy
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import app as A


def answers(**kw):
    base = {"name": "", "roles": [], "level": "1-3 years", "skills": [],
            "city": "", "modes": []}
    base.update(kw)
    return base


class TestManualValidation(unittest.TestCase):
    def test_role_required(self):
        err = A.validate_manual_answers(answers(roles=[]))
        self.assertIsInstance(err, str)
        self.assertIn("target job role", err)
        err2 = A.validate_manual_answers(answers(roles=["  ", ""]))
        self.assertIsInstance(err2, str)

    def test_valid_passes(self):
        self.assertIsNone(A.validate_manual_answers(answers(roles=["PHP Developer"])))
        self.assertIsNone(A.validate_manual_answers(answers(roles=[" X ", "Y "])))


class TestManualBuilder(unittest.TestCase):
    def test_multi_roles(self):
        p = A.build_manual_profile(answers(roles=["PHP Developer", " React Developer ", "PHP Developer"]))
        self.assertEqual(p["base_role"], "PHP Developer")
        self.assertEqual(p["search_terms"], ["PHP Developer", "React Developer"])

    def test_all_levels(self):
        for label, years in [("Fresher / Student", 0), ("0-1 years", 1), ("1-3 years", 2),
                             ("3-5 years", 4), ("5+ years", 6)]:
            with self.subTest(level=label):
                self.assertEqual(A.build_manual_profile(answers(level=label))["experience_years"], years)
        self.assertEqual(A.build_manual_profile(answers(level="bogus"))["experience_years"], 0)

    def test_skills_cleaned(self):
        p = A.build_manual_profile(answers(skills=["PHP", " php ", "", "MySQL", "PHP"]))
        self.assertEqual(p["skills"], ["PHP", "MySQL"])

    def test_city_optional(self):
        p = A.build_manual_profile(answers(city=""))
        self.assertEqual(p["location"]["city"], "")
        self.assertEqual(p["location"]["preferred_regions"], "Remote")
        p2 = A.build_manual_profile(answers(city="Pune"))
        self.assertEqual(p2["location"]["city"], "Pune")
        self.assertIn("Pune", p2["location"]["preferred_regions"])

    def test_modes_mapping(self):
        self.assertEqual(A.build_manual_profile(answers(modes=[]))["work_preferences"],
                         {"remote": True, "hybrid": True, "onsite": True})
        self.assertEqual(A.build_manual_profile(answers(modes=["Remote"]))["work_preferences"],
                         {"remote": True, "hybrid": False, "onsite": False})
        self.assertEqual(A.build_manual_profile(answers(modes=["Hybrid", "On-site"]))["work_preferences"],
                         {"remote": False, "hybrid": True, "onsite": True})

    def test_empty_name_allowed_review_enforces(self):
        self.assertEqual(A.build_manual_profile(answers())["name"], "")
        self.assertEqual(A.build_manual_profile(answers(name="Aarav"))["name"], "Aarav")

    def test_resume_text_honest(self):
        p = A.build_manual_profile(answers(name="Aarav", roles=["PHP Developer"],
                                           skills=["PHP"], city="Pune", level="1-3 years"))
        txt = p["resume_text"]
        for bit in ("Aarav", "PHP Developer", "PHP", "Pune", "2 years"):
            self.assertIn(bit, txt)
        self.assertNotIn("http", txt)
        self.assertNotIn("github", txt.lower())

    def test_schema_compatible_with_extraction(self):
        parsed = A.parse_resume_heuristics("Aarav Sharma\naarav@example.com\nPHP, MySQL")
        manual = A.build_manual_profile(answers(roles=["PHP Developer"], skills=["PHP"]))
        self.assertTrue(set(manual) <= set(parsed),
                        f"extra keys: {sorted(set(manual) - set(parsed))}")

    def test_limits(self):
        p = A.build_manual_profile(answers(roles=[f"Role {i}" for i in range(20)],
                                           skills=[f"S{i}" for i in range(100)]))
        self.assertLessEqual(len(p["search_terms"]), 8)
        self.assertLessEqual(len(p["skills"]), 40)

    def test_blank_city_label_safe(self):
        self.assertEqual(A.get_location_label({"location": {"city": "", "state": ""}}), "India")


class TestOnboardingPathState(unittest.TestCase):
    def test_two_paths_defined(self):
        self.assertEqual(list(A.ONB_PATHS), ["📄 Upload Resume", "✍️ Answer Questions"])

    def test_draft_value_fallback(self):
        self.assertEqual(A._onb_val(None, "name", "D"), "D")
        self.assertEqual(A._onb_val({}, "name", "D"), "D")
        self.assertEqual(A._onb_val({"name": "Aarav"}, "name", "D"), "Aarav")
        self.assertEqual(A._onb_val({"name": ""}, "name", "D"), "")

    def test_draft_index_mapping(self):
        opts = ["a", "b", "c"]
        self.assertEqual(A._onb_index(opts, "b"), 1)
        self.assertEqual(A._onb_index(opts, "zzz"), 0)
        self.assertEqual(A._onb_index(opts, None, default=2), 2)

    def test_no_duplicate_widget_keys_across_panes(self):
        import re
        src = open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "app.py"), encoding="utf-8").read()
        keys = re.findall(r'key="(onb_[^"]+|btn_onb_[^"]+)"', src)
        onboard_keys = [k for k in keys if k.startswith(("onb_q_", "onb_name", "onb_city",
                                                         "onb_role", "onb_file", "onb_pasted",
                                                         "onb_remember", "btn_onb_"))]
        self.assertEqual(len(onboard_keys), len(set(onboard_keys)),
                         f"duplicate widget keys: {sorted({k for k in onboard_keys if onboard_keys.count(k) > 1})}")
        for k in ("btn_onb_goto_upload", "btn_onb_goto_manual", "btn_onb_back"):
            self.assertIn(k, onboard_keys)


class TestOnboardingSteps(unittest.TestCase):
    def test_go_step_clamps(self):
        ss = {}
        self.assertEqual(A.onb_go_step(ss, 1), 1)
        self.assertEqual(A.onb_go_step(ss, 2), 2)
        self.assertEqual(ss["onb_step"], 2)
        self.assertEqual(A.onb_go_step(ss, 99), 2)
        self.assertEqual(A.onb_go_step(ss, 0), 1)
        self.assertEqual(A.onb_go_step(ss, None), 1)
        self.assertEqual(A.onb_go_step(ss, "bogus"), 1)

    def test_go_step_preserves_everything_else(self):
        ss = {"onb_step": 1, "onb_path": A.ONB_PATHS[1],
              "onb_draft_manual": {"roles": "X"}, "pending_profile": {"a": 1},
              "onb_path_last": "stale"}
        A.onb_go_step(ss, 2)
        self.assertEqual(ss, {"onb_step": 2, "onb_path": A.ONB_PATHS[1],
                              "onb_draft_manual": {"roles": "X"}, "pending_profile": {"a": 1},
                              "onb_path_last": "stale"})

    def test_step_transitions_roundtrip(self):
        ss = {}
        A.onb_go_step(ss, 2)
        A.onb_go_step(ss, 1)
        self.assertEqual(ss["onb_step"], 1)


class TestOnboardingPolish(unittest.TestCase):
    def test_step_labels(self):
        self.assertEqual(A.onb_step_label(1), "Step 1 of 3 — Choose how to create your profile.")
        self.assertEqual(A.onb_step_label(2, A.ONB_PATHS[0]), f"Step 2 of 3 — {A.ONB_PATHS[0]}")
        self.assertEqual(A.onb_step_label(2, ""), "Step 2 of 3 — Complete the selected path.")
        self.assertEqual(A.onb_step_label(3), "Step 3 of 3 — Review & confirm.")
        self.assertEqual(A.onb_step_label(0), A.onb_step_label(1))
        self.assertEqual(A.onb_step_label(99), A.onb_step_label(3))
        self.assertEqual(A.onb_step_label("bogus"), A.onb_step_label(1))

    def test_card_labels(self):
        self.assertEqual(A.onb_card_label(A.ONB_PATHS[0], A.ONB_PATHS[0], "Upload Resume →"),
                         "✓ Upload Resume →")
        self.assertEqual(A.onb_card_label("", A.ONB_PATHS[1], "Answer Questions →"),
                         "Answer Questions →")
        self.assertEqual(A.onb_card_label(A.ONB_PATHS[1], A.ONB_PATHS[1], "X"), "✓ X")

    def test_benefits_present(self):
        src = open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "app.py"), encoding="utf-8").read()
        for bit in ("prop-benefit", "stack-fit scoring", "live links extracted", "ATS resume tailor"):
            self.assertIn(bit, src)

    def test_demo_entry_preserved_but_demoted(self):
        import re
        src = open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "app.py"), encoding="utf-8").read()
        flat = re.sub(r"\s+", " ", src)
        # top-bar entry point intact
        self.assertIn('key="btn_top_demo_action"', flat)
        # in-panel demo CTA is secondary now (single prominent demo entry)
        self.assertIn('key="btn_recruiter_tour", type="secondary"', flat)
        self.assertNotIn('key="btn_recruiter_tour", type="primary"', flat)

    def test_panel_fixed_height(self):
        # Genuine fixed-size wizard (verified against live DOM: Step 1 outer was
        # 531.5x758.7px, Step 2 was 531.5x868.4px — the unconstrained outer
        # panel was the expanding parent). Outer card has a REAL height
        # (min(720px, calc(100vh - 180px))), flex column, overflow hidden; ONLY
        # the inner body scrolls (flex:1 + min-height:0 + overflow-y:auto).
        # Demo lives outside the card; review renders inside the same card.
        import re
        src = open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "app.py"), encoding="utf-8").read()
        flat = re.sub(r"\s+", " ", src)
        self.assertIn('with st.container(border=True, key="onboard_panel"):', flat)
        self.assertNotIn("height=620", flat)
        self.assertNotIn("ONB_STEP_BODY_H", src)
        self.assertIn('key="onboard_step_body"', flat)
        self.assertIn('key="onboard_head"', flat)
        self.assertIn('key="onboard_step_foot"', flat)
        self.assertIn('key="onboard_demo"', flat)
        # demo container opens before the wizard panel (separate card)
        self.assertLess(src.find('key="onboard_demo"'), src.find('key="onboard_panel"'))
        # review renders inside the wizard, not via a full-page takeover
        self.assertNotIn("def render_confirm_screen", src)
        self.assertIn("_is_review", flat)
        self.assertIn('key="btn_confirm_go"', flat)
        for bit in ("height: min(720px, calc(100vh - 180px))",
                    ".st-key-onboard_panel > div",
                    "flex: 1 1 auto",
                    "min-height: 0",
                    "box-sizing: border-box",
                    "overflow: hidden",
                    ".st-key-onboard_step_body",
                    "overflow-y: auto",
                    "@media (max-width: 640px)",
                    'key="btn_onb_back"',
                    "body_msg"):
            self.assertIn(bit, src, f"missing: {bit}")


class TestClickableCards(unittest.TestCase):
    def test_bridge_is_accessible(self):
        script = A.onb_path_cards_script()
        for bit in ('role", "button"', 'tabindex", "0"', "aria-label",
                    '"Enter"', '" "', "btn.click()", "onbWired",
                    "Upload Resume", "Answer Questions", "catch"):
            self.assertIn(bit, script, f"missing: {bit}")

    def test_bridge_targets_stable_container(self):
        # Regression: stVerticalBlockBorderWrapper does not exist in this
        # Streamlit version (verified in the installed frontend bundle), so
        # the bridge must not depend on it.
        script = A.onb_path_cards_script()
        self.assertNotIn("stVerticalBlockBorderWrapper", script)
        self.assertIn('div[data-testid="stVerticalBlock"]', script)
        self.assertIn('span[data-onb-card="', script)

    def test_markers_present_in_both_cards(self):
        src = open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "app.py"), encoding="utf-8").read()
        self.assertIn('<span data-onb-card="upload">', src)
        self.assertIn('<span data-onb-card="manual">', src)

    def test_card_css_states(self):
        src = open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "app.py"), encoding="utf-8").read()
        for bit in (".onb-path-card:hover", ".onb-path-card:focus-visible",
                    "outline: 2px solid #10b981", "cursor: pointer"):
            self.assertIn(bit, src)

    def test_bridge_wired_after_cards(self):
        import re
        src = open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "app.py"), encoding="utf-8").read()
        flat = re.sub(r"\s+", " ", src)
        self.assertIn("st.html(onb_path_cards_script(), unsafe_allow_javascript=True)", flat)


class TestManualMerge(unittest.TestCase):
    EXISTING = {
        "name": "Old Name", "base_role": "Old Role", "skills": ["PHP"],
        "projects": [{"name": "Shop", "repo_url": "https://github.com/u/shop", "bullets": ["X"]}],
        "education": [{"degree": "BCA", "institution": "SNDT", "year": "2022"}],
        "location": {"city": "Mumbai", "state": "Maharashtra", "country": "India",
                     "preferred_regions": "Mumbai, Remote"},
    }

    def test_manual_preserves_lists(self):
        manual = A.build_manual_profile(answers(roles=["React Developer"], skills=["React"]))
        out = A.merge_profiles(copy.deepcopy(self.EXISTING), manual)
        self.assertEqual(out["projects"], self.EXISTING["projects"])
        self.assertEqual(out["education"], self.EXISTING["education"])
        self.assertEqual(out["base_role"], "React Developer")
        self.assertIn("React", out["skills"])
        self.assertIn("PHP", out["skills"])

    def test_manual_city_blank_keeps_stored(self):
        manual = A.build_manual_profile(answers(roles=["X"]))
        out = A.merge_profiles(copy.deepcopy(self.EXISTING), manual)
        self.assertEqual(out["location"]["city"], "Mumbai")

    def test_repeated_manual_idempotent(self):
        manual = A.build_manual_profile(answers(roles=["X"], skills=["React"]))
        once = A.merge_profiles(copy.deepcopy(self.EXISTING), manual)
        self.assertEqual(A.merge_profiles(once, manual), once)


if __name__ == "__main__":
    unittest.main(verbosity=2)
