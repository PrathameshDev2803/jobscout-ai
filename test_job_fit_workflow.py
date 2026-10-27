"""Targeted regression tests for Job & Fit redesign and 3-step workflow in app.py.

Verifies:
- Detected job top card and badges
- Default step 1 landing (tailor_step = 1)
- Job & Fit analysis dashboard rendering (score gauge, fit assessment, matching/missing panels)
- Stepper navigation: 01 Job & Fit -> 02 Template Gallery -> 03 AI Resume Studio
- Action buttons: Choose Template, View Full JD, Edit Details, Reset
"""
import os
import unittest
from streamlit.testing.v1 import AppTest

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
APP_PATH = os.path.join(ROOT_DIR, "app.py")


class TestJobFitWorkflow(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(APP_PATH, "r", encoding="utf-8") as f:
            cls.src = f.read()

    def test_css_classes_present(self):
        self.assertIn(".detected-card", self.src)
        self.assertIn(".fit-analysis-card", self.src)
        self.assertIn(".fit-top-cluster", self.src)
        self.assertIn(".fit-gauge-assessment", self.src)
        self.assertIn(".fit-skills-grid", self.src)
        self.assertIn(".fit-panel.matching", self.src)
        self.assertIn(".fit-panel.missing", self.src)
        self.assertIn(".fit-skill-pill", self.src)

    def test_stepper_button_styling_present(self):
        self.assertIn('st-key-step_nav_1', self.src)
        self.assertIn('st-key-step_nav_2', self.src)
        self.assertIn('st-key-step_nav_3', self.src)

    def test_default_tailor_step_is_one(self):
        # Initial step after parse or link fetch must be 1
        self.assertIn('st.session_state["tailor_step"] = 1', self.src)

    def test_app_test_job_detected_and_step_navigation(self):
        at = AppTest.from_file(APP_PATH)
        # Seed a detected job in session_state
        sample_job = {
            "title": "Full Stack Developer",
            "company": "IRIS RegTech Solutions",
            "location": "Turbhe, Navi Mumbai",
            "experience_raw": "2–5 years",
            "source": "manual jd",
            "description": "Looking for Full Stack Developer with React, Python, Django, SQL, NoSQL, Angular, Vue.",
            "extracted_skills": ["React", "Angular", "Vue", "Python", "Django", "Flask", "Java", "REST APIs", "SQL", "NoSQL"],
            "url": "https://example.com/job"
        }
        at.session_state["demo_mode"] = True
        at.session_state["owner_ok"] = False
        at.session_state["quick_job"] = sample_job
        at.session_state["tailor_step"] = 1
        at.run(timeout=30)
        self.assertEqual(len(at.exception), 0, f"Exceptions on Step 1: {at.exception}")

        # Check step buttons exist
        b1 = at.button(key="step_nav_1")
        b2 = at.button(key="step_nav_2")
        b3 = at.button(key="step_nav_3")
        self.assertIsNotNone(b1)
        self.assertIsNotNone(b2)
        self.assertIsNotNone(b3)

        # Check action buttons on step 1
        btn_step2 = at.button(key="btn_q_re_tailor") or at.button(key="btn_q_go_step2")
        self.assertIsNotNone(btn_step2)
        btn_reset = at.button(key="btn_q_reset")
        self.assertIsNotNone(btn_reset)

        # Click step 2
        b2.click().run(timeout=30)
        self.assertEqual(len(at.exception), 0)
        self.assertEqual(at.session_state["tailor_step"], 2)

        # Click step 3
        b3 = at.button(key="step_nav_3")
        b3.click().run(timeout=30)
        self.assertEqual(len(at.exception), 0)
        self.assertEqual(at.session_state["tailor_step"], 3)

        # Click step 1 again
        b1 = at.button(key="step_nav_1")
        b1.click().run(timeout=30)
        self.assertEqual(len(at.exception), 0)
        self.assertEqual(at.session_state["tailor_step"], 1)

        # Click Reset button
        btn_reset = at.button(key="btn_q_reset")
        btn_reset.click().run(timeout=30)
        self.assertEqual(len(at.exception), 0)
        self.assertIsNone(at.session_state.get("quick_job"))

    def test_score_consistency_in_job_fit_step1(self):
        at = AppTest.from_file(APP_PATH)
        job_with_gaps = {
            "title": "Full Stack Developer",
            "company": "IRIS RegTech Solutions",
            "location": "Turbhe, Navi Mumbai",
            "experience_raw": "2–5 years",
            "source": "manual jd",
            "description": "Looking for Full Stack Developer with React, Python, Git. Other stack: NodeJs, Angular, VueJs, Ruby On Rails, Redis, Postgres, Cassandra.",
            "extracted_skills": ["React", "Python", "SQL", "NoSQL", "Git", "NodeJs", "Angular", "VueJs", "Ruby On Rails", "Redis", "Postgres", "Cassandra"],
            "url": "https://example.com/job"
        }
        at.session_state["demo_mode"] = True
        at.session_state["owner_ok"] = False
        at.session_state["quick_job"] = job_with_gaps
        at.session_state["tailor_step"] = 1
        at.run(timeout=30)
        self.assertEqual(len(at.exception), 0)

        # Inspect rendered markdown
        rendered_md = [m.value for m in at.markdown]
        fit_cards = [m for m in rendered_md if '<div class="fit-analysis-card">' in m]
        self.assertTrue(len(fit_cards) > 0, "Job & Fit analysis card should be rendered")
        card_content = fit_cards[0]

        # Ensure 100% Match is NOT rendered when missing skills
        self.assertNotIn(">100%</text>", card_content)
        # Ensure fit badge is NOT Strong fit with high skill coverage
        self.assertNotIn("with high skill coverage across the required tech stack", card_content)
        # Ensure skill counts are rendered
        self.assertIn("found</span>", card_content)
        self.assertIn("missing</span>", card_content)


if __name__ == "__main__":
    unittest.main()
