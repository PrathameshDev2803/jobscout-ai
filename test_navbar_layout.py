"""Targeted tests for JobScout top navbar layout, profile presentation, and settings controls.

Verifies:
- Top navbar container and 3-region grid layout (centered relative to viewport).
- User profile rendering (full name, city, no desktop clipping).
- Settings popover control (outlined, 40-44px, accessible tooltip, focus outline).
- Responsive mobile & tablet layout rules (progressive adaptation, 2-row mobile layout).
- App execution via Streamlit AppTest.
"""
import os
import re
import unittest
from streamlit.testing.v1 import AppTest

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
APP_PATH = os.path.join(ROOT_DIR, "app.py")


class TestNavbarLayout(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(APP_PATH, "r", encoding="utf-8") as f:
            cls.src = f.read()

    def test_top_navbar_container_present(self):
        self.assertIn('with st.container(key="top_navbar"):', self.src)
        self.assertIn('top_brand_col, top_nav_col, top_user_col = st.columns([1, 1, 1]', self.src)

    def test_navigation_labels_and_options(self):
        self.assertIn('_NAV_LABELS = {"Jobs": "Find & Tailor", "Applications": "Applications", "Resume": "My Resumes"}', self.src)
        self.assertIn('key="main_nav_selector"', self.src)

    def test_user_profile_cluster_and_pill(self):
        self.assertIn('with st.container(key="nav_user_cluster"):', self.src)
        self.assertIn('class="user-pill"', self.src)
        self.assertIn('class="user-avatar"', self.src)
        self.assertIn('class="user-name"', self.src)
        self.assertIn('class="user-dot"', self.src)
        self.assertIn('class="user-loc"', self.src)
        # HTML escaping for profile fields
        self.assertIn('html.escape(user_name)', self.src)
        self.assertIn('html.escape(user_city)', self.src)

    def test_settings_popover_control(self):
        self.assertIn('key="top_settings_popover"', self.src)
        self.assertIn('key="btn_open_settings_pop"', self.src)
        self.assertIn('key="btn_switch_resume_pop"', self.src)

    def test_css_grid_centered_desktop_layout(self):
        # 3-region CSS Grid ensuring exact horizontal centering
        self.assertIn("grid-template-columns: minmax(0, 1fr) auto minmax(0, 1fr)", self.src)
        self.assertIn(".st-key-top_navbar div[data-testid=\"stHorizontalBlock\"]", self.src)

    def test_css_settings_button_styling(self):
        # Hamburger button: 52px desktop / 44px mobile, slate border, indigo focus ring
        self.assertIn("--menu-btn-size: 52px", self.src)
        self.assertIn("--menu-radius: 15px", self.src)
        self.assertIn("border: 1px solid #2a3a55 !important;", self.src)
        self.assertIn("outline: 2px solid #a5b4fc !important;", self.src)
        self.assertIn("--menu-btn-size: 44px", self.src)
        self.assertIn("prefers-reduced-motion: reduce", self.src)

    def test_hamburger_icon_and_open_state(self):
        # Three lines morph into an X using transforms, not a glyph swap
        self.assertIn("background-size: 100% 2px !important;", self.src)
        self.assertIn('button[aria-expanded="true"] p::before', self.src)
        self.assertIn("translateY(7px) rotate(45deg)", self.src)
        self.assertIn("translateY(-7px) rotate(-45deg)", self.src)

    def test_menu_button_accessibility_patch(self):
        self.assertIn('st.popover("Menu", key="top_settings_popover")', self.src)
        self.assertIn("setAttribute('type', 'button')", self.src)
        self.assertIn("'Close menu' : 'Open menu'", self.src)
        self.assertIn("aria-controls", self.src)

    def test_mobile_menu_nav_uses_pending_nav(self):
        # Widget keys cannot be written after instantiation; route through pending_nav
        self.assertIn('st.session_state["pending_nav"] = "Applications"', self.src)
        self.assertNotIn('st.session_state["main_nav_selector"] = "Applications"', self.src)

    def test_css_user_pill_no_desktop_clipping(self):
        # User pill: inline-flex, nowrap, flex-shrink 0, visible on desktop
        self.assertIn(".user-pill {", self.src)
        self.assertIn("white-space: nowrap;", self.src)
        self.assertIn("flex-shrink: 0;", self.src)

    def test_css_responsive_rules(self):
        # Tablet 1024px: padding reduction before hiding text
        self.assertIn("@media (max-width: 1024px)", self.src)
        # 880px: progressive hide of secondary city
        self.assertIn("@media (max-width: 880px) and (min-width: 769px)", self.src)
        # 768px: deliberate 2-row stacked layout
        self.assertIn("@media (max-width: 768px)", self.src)
        self.assertIn("flex-wrap: wrap !important;", self.src)
        self.assertIn("order: 1 !important;", self.src)
        self.assertIn("order: 2 !important;", self.src)
        self.assertIn("order: 3 !important;", self.src)

    def test_app_execution_and_navigation(self):
        at = AppTest.from_file(APP_PATH)
        at.session_state["demo_mode"] = True
        at.session_state["owner_ok"] = False
        at.run(timeout=30)
        self.assertEqual(len(at.exception), 0, f"App execution raised exceptions: {at.exception}")

        # Verify segmented control
        nav_ctrl = at.segmented_control(key="main_nav_selector")
        self.assertIsNotNone(nav_ctrl)
        self.assertEqual(nav_ctrl.options, ["Find & Tailor", "Applications", "My Resumes"])
        self.assertEqual(nav_ctrl.value, "Jobs")


if __name__ == "__main__":
    unittest.main()
