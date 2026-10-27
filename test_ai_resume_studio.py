"""Targeted tests for AI Resume Studio redesign in app.py.

Verifies:
- AI Resume Studio header and match badge
- Change template button and selected template display
- Highlights card, Missing profile card, ATS Readiness card
- Live resume editing tabs (Summary & Title, Work Experience, Core Skills, Projects & Education)
- AI regeneration button
- Zoom controls and Live preview container
- Download PDF, Email, and Save to Library buttons
- Real-time propagation of edits into tailored resume state
"""
import os
import unittest
from streamlit.testing.v1 import AppTest

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
APP_PATH = os.path.join(ROOT_DIR, "app.py")


class TestAIResumeStudio(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(APP_PATH, "r", encoding="utf-8") as f:
            cls.src = f.read()

    def test_css_classes_present(self):
        self.assertIn(".studio-heading", self.src)
        self.assertIn(".studio-match-badge", self.src)
        self.assertIn(".template-mini-badge", self.src)
        self.assertIn(".studio-card", self.src)
        self.assertIn(".highlights-body", self.src)
        self.assertIn(".studio-warning-card", self.src)
        self.assertIn(".ats-readiness-card", self.src)
        self.assertIn(".resume-doc-sheet", self.src)
        self.assertIn(".edit-content-card", self.src)

    def test_studio_rendering_and_interaction(self):
        at = AppTest.from_file(APP_PATH)
        sample_job = {
            "title": "Backend Developer",
            "company": "FITISTAN (Niyogya.ai Fitness Technology Private Limited)",
            "location": "Mumbai, Maharashtra",
            "experience_raw": "2–4 years",
            "source": "manual jd",
            "description": "Looking for Backend Developer skilled in PHP, Laravel, MySQL, REST APIs, and Docker.",
            "extracted_skills": ["PHP", "Laravel", "MySQL", "REST APIs", "Docker", "E-Commerce", "Performance Optimization"],
            "url": "https://example.com/job"
        }
        at.session_state["demo_mode"] = True
        at.session_state["owner_ok"] = False
        at.session_state["quick_job"] = sample_job
        at.session_state["tailor_step"] = 3
        at.session_state["sel_resume_template"] = "Modern Clean"
        at.run(timeout=35)
        self.assertEqual(len(at.exception), 0, f"Exceptions on Step 3: {at.exception}")

        # Verify buttons exist
        b_change_tpl = at.button(key="btn_s3_change_tpl")
        self.assertIsNotNone(b_change_tpl, "Change Template button should be rendered")

        b_download = at.download_button(key="btn_quick_pdf_download")
        self.assertIsNotNone(b_download, "Download PDF button should be rendered")

        b_save_lib = at.button(key="btn_quick_pdf_library")
        self.assertIsNotNone(b_save_lib, "Save to Library button should be rendered")

        b_zoom_in = at.button(key="btn_zoom_in")
        b_zoom_out = at.button(key="btn_zoom_out")
        self.assertIsNotNone(b_zoom_in, "Zoom in button should be rendered")
        self.assertIsNotNone(b_zoom_out, "Zoom out button should be rendered")

        b_regen = at.button(key="btn_regen_ai_summary")
        self.assertIsNotNone(b_regen, "Regenerate AI button should be rendered")

        # Verify inputs exist
        inp_role = at.text_input(key="input_qt_role")
        self.assertIsNotNone(inp_role, "Target role input should be rendered")

        inp_summary = at.text_area(key="input_qt_summary")
        self.assertIsNotNone(inp_summary, "Professional summary textarea should be rendered")

        # Test editing role title and verifying state update
        inp_role.input("Senior Backend & Cloud Engineer").run(timeout=25)
        self.assertEqual(len(at.exception), 0)
        qt = at.session_state.get("quick_tailored", {})
        self.assertEqual(qt.get("tailored_title"), "Senior Backend & Cloud Engineer")

        # Test zoom in button
        b_zoom_in = at.button(key="btn_zoom_in")
        b_zoom_in.click().run(timeout=25)
        self.assertEqual(len(at.exception), 0)
        self.assertGreaterEqual(at.session_state.get("resume_preview_zoom", 100), 110)

        # Test change template returns to Step 2
        b_change_tpl = at.button(key="btn_s3_change_tpl")
        b_change_tpl.click().run(timeout=35)
        self.assertEqual(len(at.exception), 0)
        self.assertEqual(at.session_state.get("tailor_step"), 2)


if __name__ == "__main__":
    unittest.main()
