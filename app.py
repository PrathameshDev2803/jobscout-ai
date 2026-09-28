"""Personal job tool: Top navigation + clean job workspace. Find -> Tailor -> Apply."""
import html
import json
import os
import re
import sqlite3
import time
import urllib.parse
from datetime import datetime

import requests
import streamlit as st
from dotenv import load_dotenv
from fpdf import FPDF
try:
    import pymupdf as fitz
except ImportError:
    import fitz

from matcher import (compute_match, get_location_label, location_match,
                     profile_location)
from scheduler import (get_scheduler_status, set_scheduler_enabled,
                       start_background_scheduler, trigger_immediate_fetch)
from notifier import (get_smtp_config, is_smtp_configured, send_test_email)
from dotenv import dotenv_values, load_dotenv
from fetch import fetch_job_from_url, save

BASE = os.path.dirname(os.path.abspath(__file__))
ENV_FILE = os.path.join(BASE, ".env")
load_dotenv(ENV_FILE, override=True)
DB = os.path.join(BASE, "jobs.db")
PROFILE = os.path.join(BASE, "profile.json")
RESUME_TXT = os.path.join(BASE, "resume.txt")
ACCENT = "#10b981"


def get_gemini_api_key():
    """Bulletproof loader for GEMINI_API_KEY from session, disk .env, or os.environ."""
    # 1. Check session state if running inside Streamlit
    try:
        if "gemini_api_key" in st.session_state and st.session_state.gemini_api_key:
            k = str(st.session_state.gemini_api_key).strip()
            if k:
                os.environ["GEMINI_API_KEY"] = k
                return k
    except Exception:
        pass

    # 2. Check disk .env file directly (captures real-time edits without server reboot)
    if os.path.exists(ENV_FILE):
        try:
            vals = dotenv_values(ENV_FILE)
            k = (vals.get("GEMINI_API_KEY") or "").strip()
            if k:
                os.environ["GEMINI_API_KEY"] = k
                try:
                    st.session_state.gemini_api_key = k
                except Exception:
                    pass
                return k
        except Exception:
            pass

    # 3. Check os.environ fallback
    k = (os.getenv("GEMINI_API_KEY") or "").strip()
    if k:
        try:
            st.session_state.gemini_api_key = k
        except Exception:
            pass
        return k

    return ""


def set_gemini_api_key(new_key):
    """Persist GEMINI_API_KEY to session state, os.environ, and disk .env."""
    k = (new_key or "").strip()
    try:
        st.session_state.gemini_api_key = k
    except Exception:
        pass
    os.environ["GEMINI_API_KEY"] = k
    try:
        lines = []
        found = False
        if os.path.exists(ENV_FILE):
            with open(ENV_FILE, "r", encoding="utf-8") as f:
                for line in f:
                    if line.strip().startswith("GEMINI_API_KEY="):
                        lines.append(f"GEMINI_API_KEY={k}\n")
                        found = True
                    else:
                        lines.append(line)
        if not found:
            lines.insert(0, f"GEMINI_API_KEY={k}\n")
        with open(ENV_FILE, "w", encoding="utf-8") as f:
            f.writelines(lines)
    except Exception:
        pass
    return k


# ponytail: Top navigation layout replaces permanent sidebar for a distraction-free, full-width workspace
st.set_page_config(page_title="JobTool", layout="wide", initial_sidebar_state="collapsed")


@st.cache_resource
def init_background_scheduler():
    start_background_scheduler(interval_minutes=15)
    return True


init_background_scheduler()

CSS = """
<style>
/* Global page & canvas cleanup */
.block-container {
    max-width: 1240px;
    padding-top: 0.75rem !important;
    padding-bottom: 3.5rem !important;
}

/* Hide permanent sidebar and native collapse controls */
section[data-testid="stSidebar"] {
    display: none !important;
}
button[data-testid="stSidebarCollapseButton"] {
    display: none !important;
}
[data-testid="collapsedControl"] {
    display: none !important;
}
header[data-testid="stHeader"] {
    background: transparent !important;
    height: 1.2rem !important;
}

/* Top Navbar Styling */
.nav-brand {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 2px 0;
    user-select: none;
}
.brand-icon {
    font-size: 22px;
    filter: drop-shadow(0 0 10px rgba(16, 185, 129, 0.45));
}
.brand-title {
    font-size: 21px;
    font-weight: 850;
    letter-spacing: -0.03em;
    color: #ffffff;
}
.brand-pro {
    font-size: 9.5px;
    font-weight: 800;
    letter-spacing: 0.06em;
    color: #10b981;
    background: rgba(16, 185, 129, 0.12);
    border: 1px solid rgba(16, 185, 129, 0.3);
    padding: 1px 6px;
    border-radius: 999px;
    margin-left: 2px;
}

/* Modern Segmented Control / Navbar tabs */
div[data-testid="stSegmentedControl"] {
    background: #0d111a !important;
    border: 1px solid #1e2638 !important;
    border-radius: 10px !important;
    padding: 3px !important;
    box-shadow: 0 4px 14px rgba(0, 0, 0, 0.25) !important;
    width: 100% !important;
}
div[data-testid="stSegmentedControl"] button {
    font-size: 13.5px !important;
    font-weight: 600 !important;
    border-radius: 7px !important;
    border: none !important;
    padding: 6px 16px !important;
    transition: all 0.15s ease !important;
}
div[data-testid="stSegmentedControl"] button[aria-checked="true"] {
    background: #10b981 !important;
    color: #04130d !important;
    font-weight: 750 !important;
    box-shadow: 0 2px 8px rgba(16, 185, 129, 0.35) !important;
}
div[data-testid="stSegmentedControl"] button[aria-checked="false"] {
    color: #94a3b8 !important;
    background: transparent !important;
}
div[data-testid="stSegmentedControl"] button[aria-checked="false"]:hover {
    color: #ffffff !important;
    background: rgba(255, 255, 255, 0.06) !important;
}

/* User pill on navbar right */
.user-pill {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    background: #10141f;
    border: 1px solid #1e2638;
    border-radius: 999px;
    padding: 5px 12px;
    font-size: 12.5px;
    color: #cbd5e1;
    white-space: nowrap;
    float: right;
}
.user-avatar { font-size: 13px; }
.user-name { font-weight: 650; color: #f1f5f9; }
.user-dot { color: #475569; }
.user-loc { color: #94a3b8; font-size: 11.5px; }

/* Filter Pills styling (Concept 1: [ All 112 ] [ New 112 ] [ Strong 60 ] ...) */
div[data-testid="stPills"] {
    gap: 6px !important;
}
div[data-testid="stPills"] button {
    border-radius: 999px !important;
    padding: 4px 14px !important;
    font-size: 12.5px !important;
    font-weight: 600 !important;
    border: 1px solid #202738 !important;
    background: #0f131d !important;
    color: #94a3b8 !important;
    transition: all 0.15s ease !important;
}
div[data-testid="stPills"] button:hover {
    border-color: #334155 !important;
    color: #ffffff !important;
}
div[data-testid="stPills"] button[aria-checked="true"] {
    background: #10b981 !important;
    color: #04130d !important;
    font-weight: 750 !important;
    border-color: #10b981 !important;
    box-shadow: 0 2px 8px rgba(16, 185, 129, 0.3) !important;
}

/* Slim status bar below header */
.workspace-header {
    margin-top: 6px;
    margin-bottom: 8px;
}
.workspace-title {
    font-size: 24px;
    font-weight: 800;
    color: #ffffff;
    letter-spacing: -0.02em;
    margin-bottom: 2px;
}
.statusbar {
    color: #94a3b8;
    font-size: 13px;
    padding: 2px 0 10px 0;
}
.statusbar b { color: #f1f5f9; }

/* Utility Bar: Fast Tailor + Auto-sync */
.utility-container {
    background: #0d111a;
    border: 1px solid #1c2436;
    border-radius: 11px;
    padding: 8px 12px;
    margin: 8px 0 14px 0;
}
.sync-badge {
    display: inline-flex;
    align-items: center;
    gap: 4px;
    font-weight: 650;
    font-size: 12px;
    color: #10b981;
}
.sync-badge.fetching {
    color: #38bdf8;
    animation: sync-pulse 1.5s infinite;
}
.sync-badge.muted {
    color: #64748b;
}
@keyframes sync-pulse {
    0%, 100% { opacity: 1; }
    50% { opacity: 0.45; }
}

/* Job Cards (Obsidian / Bento Grid) */
div[data-testid="stColumn"]:has(.job-card) {
    background: #11141e;
    border: 1px solid #1e2638;
    border-radius: 12px;
    padding: 14px 14px 8px 14px !important;
    transition: all 0.18s ease;
}
div[data-testid="stColumn"]:has(.job-card):hover {
    border-color: #334155;
    background: #141824;
    transform: translateY(-1px);
}
div[data-testid="stColumn"]:has(.job-card.selcol) {
    border-color: #10b981;
}
.job-card { background: transparent !important; border: none !important; padding: 0 !important; margin: 0 !important; }
.job-title { font-weight: 700; font-size: 15px; line-height: 1.35; color: #f8fafc; padding-right: 58px; }
.job-company { color: #8b93a1; font-size: 13px; margin-top: 3px; }
.job-meta { color: #7d8590; font-size: 12px; margin-top: 7px; }
.pct { float: right; font-size: 12px; font-weight: 750; border-radius: 999px; padding: 2px 8px; border: 1px solid; }
.pct-mute { color: #94a3b8; background: rgba(255,255,255,0.05); border-color: rgba(255,255,255,0.08); }
.pct-hot { color: #10b981; background: rgba(16,185,129,0.14); border-color: rgba(16,185,129,0.3); }
.chip { display: inline-block; font-size: 11px; color: #cbd5e1; background: #192030; border: 1px solid rgba(255,255,255,0.06); border-radius: 6px; padding: 2px 7px; margin: 4px 4px 0 0; }
.card-foot { display: flex; justify-content: space-between; align-items: center; border-top: 1px solid #1e2638; margin-top: 10px; padding-top: 8px; font-size: 12px; color: #7d8590; }

/* Ghost buttons inside card */
div[data-testid="stColumn"]:has(.job-card) div.stButton > button,
div[data-testid="stColumn"]:has(.job-card) a[data-testid="stLinkButton"] {
    background: transparent !important;
    border: none !important;
    color: #94a3b8 !important;
    font-size: 13px !important;
    padding: 4px 6px !important;
    border-radius: 8px !important;
}
div[data-testid="stColumn"]:has(.job-card) div.stButton > button:hover {
    color: #fff !important;
    background: rgba(255,255,255,0.06) !important;
}
div[data-testid="stColumn"]:has(.job-card) div[data-testid="stHorizontalBlock"] > div:nth-child(2) button {
    color: #10b981 !important;
    font-weight: 700 !important;
}

/* Filtered card styling */
div[data-testid="stColumn"]:has(.filtered-card) {
    background: #10131b !important;
    border: 1px dashed rgba(248, 113, 113, 0.45) !important;
}
div[data-testid="stColumn"]:has(.filtered-card):hover {
    border-color: rgba(248, 113, 113, 0.8) !important;
    background: #141620 !important;
}
.filtered-pill {
    float: right;
    font-size: 10.5px;
    font-weight: 700;
    color: #f87171;
    background: rgba(239, 68, 68, 0.15);
    border: 1px solid rgba(239, 68, 68, 0.3);
    border-radius: 999px;
    padding: 1px 7px;
    margin-left: 6px;
}
.filtered-why {
    background: rgba(239, 68, 68, 0.08);
    border-left: 2px solid #ef4444;
    color: #fca5a5;
    font-size: 11px;
    padding: 4px 8px;
    border-radius: 0 4px 4px 0;
    margin: 6px 0 4px 0;
    line-height: 1.3;
}

/* Drawer */
.drawer {
    background: #0f131d;
    border: 1px solid #1e2638;
    border-radius: 12px;
    padding: 16px;
    position: sticky;
    top: 12px;
}

/* Major Platforms Radar Bento Cards */
.platform-card {
    background: #0f131e;
    border: 1px solid #1d2537;
    border-radius: 10px;
    padding: 10px 12px;
    margin-bottom: 8px;
    transition: all 0.2s ease;
    display: flex;
    flex-direction: column;
    justify-content: space-between;
    min-height: 98px;
}
.platform-card:hover {
    border-color: #38bdf8;
    background: #141a29;
    transform: translateY(-2px);
}
.platform-head {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 4px;
}
.platform-name {
    font-size: 13px;
    font-weight: 700;
    color: #f8fafc;
    display: flex;
    align-items: center;
    gap: 6px;
}
.platform-badge {
    font-size: 9.5px;
    font-weight: 700;
    padding: 1px 6px;
    border-radius: 4px;
    border: 1px solid;
}
.platform-desc {
    font-size: 11px;
    color: #94a3b8;
    line-height: 1.35;
    margin-bottom: 8px;
}

/* Settings & Application cards */
.metric-box {
    background: #0f131e;
    border: 1px solid #1c2436;
    border-radius: 10px;
    padding: 12px 16px;
    text-align: center;
}
/* Detected Job Card (Fast Tailor parsed card) */
.detected-card {
    background: #0d121c;
    border: 1px solid rgba(16, 185, 129, 0.45);
    border-radius: 12px;
    padding: 16px 18px;
    margin: 10px 0 14px 0;
    box-shadow: 0 4px 20px rgba(0, 0, 0, 0.35);
}
.detected-pill {
    display: inline-flex;
    align-items: center;
    gap: 5px;
    font-size: 11px;
    font-weight: 750;
    color: #10b981;
    background: rgba(16, 185, 129, 0.15);
    border: 1px solid rgba(16, 185, 129, 0.35);
    border-radius: 999px;
    padding: 2px 9px;
    margin-bottom: 8px;
}
.detected-title {
    font-size: 18px;
    font-weight: 800;
    color: #f8fafc;
    line-height: 1.3;
}
.detected-company {
    font-size: 14px;
    font-weight: 600;
    color: #94a3b8;
    margin-top: 3px;
}
.detected-meta {
    font-size: 12.5px;
    color: #7d8590;
    margin-top: 6px;
    margin-bottom: 8px;
}
.detected-divider {
    border: 0;
    border-top: 1px solid #1e2638;
    margin: 12px 0 10px 0;
}
.detected-match-row {
    display: flex;
    justify-content: space-between;
    align-items: center;
    flex-wrap: wrap;
    gap: 8px;
}
.detected-score {
    font-size: 14.5px;
    font-weight: 750;
    color: #10b981;
}
.detected-missing {
    font-size: 12px;
    color: #f87171;
}

/* --- Visual Template Gallery & Live Studio Styles --- */
.gallery-cat-header {
    font-size: 14.5px;
    font-weight: 800;
    letter-spacing: 0.04em;
    color: #f1f5f9;
    text-transform: uppercase;
    margin: 18px 0 10px 0;
    padding-bottom: 5px;
    border-bottom: 1px solid #1e2638;
    display: flex;
    align-items: center;
    gap: 8px;
}
.template-card-box {
    background: #0d111a;
    border: 1px solid #1c2436;
    border-radius: 12px;
    padding: 10px;
    margin-bottom: 12px;
    transition: all 0.2s ease;
    box-shadow: 0 4px 14px rgba(0, 0, 0, 0.25);
}
.template-card-box:hover {
    border-color: #334155;
    transform: translateY(-2px);
    box-shadow: 0 8px 24px rgba(0, 0, 0, 0.45);
}
.template-card-box.selected {
    border-color: #10b981;
    background: #0f1624;
    box-shadow: 0 0 18px rgba(16, 185, 129, 0.25);
}
.template-badge-pill {
    display: inline-block;
    font-size: 10px;
    font-weight: 650;
    padding: 2px 6px;
    border-radius: 4px;
    background: rgba(255, 255, 255, 0.05);
    color: #cbd5e1;
    border: 1px solid rgba(255, 255, 255, 0.1);
    margin: 2px 3px 2px 0;
}
.template-badge-pill.safe {
    background: rgba(16, 185, 129, 0.12);
    color: #10b981;
    border-color: rgba(16, 185, 129, 0.3);
}

/* AI Changes Audit & Missing Skills Card */
.ai-audit-card {
    background: #0c111a;
    border: 1px solid #1e2638;
    border-radius: 10px;
    padding: 12px 14px;
    margin-bottom: 14px;
}
.ai-audit-title {
    font-size: 13px;
    font-weight: 750;
    color: #10b981;
    display: flex;
    align-items: center;
    gap: 6px;
    margin-bottom: 7px;
}
.ai-audit-item {
    font-size: 12px;
    color: #cbd5e1;
    margin-bottom: 3px;
    line-height: 1.35;
}
.ai-warning-card {
    background: rgba(239, 68, 68, 0.07);
    border: 1px solid rgba(239, 68, 68, 0.28);
    border-radius: 8px;
    padding: 9px 12px;
    margin-top: 10px;
}
.ai-warning-title {
    font-size: 11.5px;
    font-weight: 750;
    color: #f87171;
    margin-bottom: 4px;
}
.ai-warning-note {
    font-size: 11px;
    color: #94a3b8;
    margin-top: 4px;
    line-height: 1.3;
}
.live-preview-box {
    background: #0a0d15;
    border: 1px solid #1e2638;
    border-radius: 10px;
    padding: 8px;
    margin-bottom: 12px;
    box-shadow: 0 4px 18px rgba(0, 0, 0, 0.4);
}
</style>
"""
st.markdown(CSS, unsafe_allow_html=True)


def get_major_platforms(p, target_q=""):
    role = target_q.strip() if target_q.strip() else p.get("base_role", "Full Stack Developer")
    loc_city = p.get("location", {}).get("city", "Mumbai") if isinstance(p.get("location"), dict) else "Mumbai"
    role_enc = urllib.parse.quote(role)
    city_enc = urllib.parse.quote(loc_city)
    city_slug = re.sub(r'[^a-zA-Z0-9]+', '-', loc_city.lower()).strip('-')

    hc_state = {"searchQuery": role, "sortBy": "date"}
    hc_enc = urllib.parse.quote(json.dumps(hc_state))

    return [
        {
            "id": "indeed",
            "name": "Indeed India",
            "icon": "💼",
            "badge": "Top Volume",
            "badge_bg": "rgba(37,99,235,0.18)",
            "badge_color": "#60a5fa",
            "badge_border": "rgba(59,130,246,0.3)",
            "desc": "India's highest volume job board. Direct corporate & agency postings.",
            "url": f"https://in.indeed.com/jobs?q={role_enc}&l={city_enc}",
            "hint": "Search, copy viewjob URL, paste in Tab 2"
        },
        {
            "id": "linkedin",
            "name": "LinkedIn Jobs",
            "icon": "🔷",
            "badge": "High Response",
            "badge_bg": "rgba(14,165,233,0.18)",
            "badge_color": "#38bdf8",
            "badge_border": "rgba(14,165,233,0.3)",
            "desc": "Direct recruiter listings & easy-apply corporate and startup roles.",
            "url": f"https://www.linkedin.com/jobs/search/?keywords={role_enc}&location={city_enc}",
            "hint": "Copy LinkedIn job post link and paste in Tab 2"
        },
        {
            "id": "naukri",
            "name": "Naukri.com",
            "icon": "🎯",
            "badge": "India #1",
            "badge_bg": "rgba(249,115,22,0.18)",
            "badge_color": "#fb923c",
            "badge_border": "rgba(249,115,22,0.3)",
            "desc": "India's largest IT job portal with verified enterprise recruiters.",
            "url": f"https://www.naukri.com/jobs-in-{city_slug}?k={role_enc}",
            "hint": "Open, copy job link or JD text into Tab 1/2"
        },
        {
            "id": "wellfound",
            "name": "Wellfound (AngelList)",
            "icon": "✌️",
            "badge": "VC Startups",
            "badge_bg": "rgba(244,63,94,0.18)",
            "badge_color": "#fb7185",
            "badge_border": "rgba(244,63,94,0.3)",
            "desc": "Top-tier Silicon Valley & Indian VC-backed seed/series A startups.",
            "url": f"https://wellfound.com/jobs?role={role_enc}",
            "hint": "Direct founder & engineering lead contact"
        },
        {
            "id": "hiringcafe",
            "name": "HiringCafe",
            "icon": "☕",
            "badge": "No-Spam ATS",
            "badge_bg": "rgba(245,158,11,0.18)",
            "badge_color": "#fbbf24",
            "badge_border": "rgba(245,158,11,0.3)",
            "desc": "Stealth company crawler: Direct Greenhouse, Lever & Ashby listings.",
            "url": f"https://hiring.cafe/?searchState={hc_enc}",
            "hint": "Direct company career page links"
        },
        {
            "id": "instahyre",
            "name": "Instahyre",
            "icon": "⚡",
            "badge": "AI Match",
            "badge_bg": "rgba(16,185,129,0.18)",
            "badge_color": "#34d399",
            "badge_border": "rgba(16,185,129,0.3)",
            "desc": "Curated tech engineering jobs with salary bands and verified HR.",
            "url": "https://www.instahyre.com/jobs/",
            "hint": "Premium Indian product companies"
        },
        {
            "id": "cutshort",
            "name": "Cutshort",
            "icon": "🚀",
            "badge": "Fast Track",
            "badge_bg": "rgba(139,92,246,0.18)",
            "badge_color": "#a78bfa",
            "badge_border": "rgba(139,92,246,0.3)",
            "desc": "Direct connection with hiring managers & CTOs without agency spam.",
            "url": "https://cutshort.io/",
            "hint": "Match directly with engineering leads"
        },
        {
            "id": "yc",
            "name": "Y Combinator Startups",
            "icon": "🟧",
            "badge": "Top 1%",
            "badge_bg": "rgba(249,115,22,0.18)",
            "badge_color": "#fb923c",
            "badge_border": "rgba(249,115,22,0.3)",
            "desc": "Work at YC-funded startups. High equity, cutting-edge AI & modern stacks.",
            "url": f"https://www.workatastartup.com/jobs?query={role_enc}",
            "hint": "High-growth YC startup opportunities"
        },
        {
            "id": "foundit",
            "name": "Foundit (Monster)",
            "icon": "🟣",
            "badge": "Enterprise",
            "badge_bg": "rgba(99,102,241,0.18)",
            "badge_color": "#818cf8",
            "badge_border": "rgba(99,102,241,0.3)",
            "desc": "Leading Indian IT MNCs, banking & enterprise technology consultancies.",
            "url": f"https://www.foundit.in/srp/results?query={role_enc}&locations={city_enc}",
            "hint": "Enterprise Indian tech roles"
        },
        {
            "id": "glassdoor",
            "name": "Glassdoor India",
            "icon": "🟢",
            "badge": "Verified Reviews",
            "badge_bg": "rgba(5,150,105,0.18)",
            "badge_color": "#10b981",
            "badge_border": "rgba(5,150,105,0.3)",
            "desc": "Roles with verified salary transparency & employee work culture reviews.",
            "url": f"https://www.glassdoor.co.in/Job/jobs.htm?sc.keyword={role_enc}",
            "hint": "Check salary range before applying"
        }
    ]


def load_profile():
    if not os.path.exists(PROFILE):
        example_p = os.path.join(BASE, "profile.example.json")
        if os.path.exists(example_p):
            try:
                import shutil
                shutil.copyfile(example_p, PROFILE)
            except Exception:
                pass
    target = PROFILE if os.path.exists(PROFILE) else os.path.join(BASE, "profile.example.json")
    with open(target, encoding="utf-8") as f:
        p = json.load(f)

    if not os.path.exists(RESUME_TXT):
        example_r = os.path.join(BASE, "resume.example.txt")
        if os.path.exists(example_r):
            try:
                import shutil
                shutil.copyfile(example_r, RESUME_TXT)
            except Exception:
                pass
    target_res = RESUME_TXT if os.path.exists(RESUME_TXT) else os.path.join(BASE, "resume.example.txt")

    if (not p.get("resume_text") or "PASTE your base resume" in p.get("resume_text", "")) and os.path.exists(target_res):
        with open(target_res, encoding="utf-8") as f:
            p["resume_text"] = f.read()
    return p


def ensure_db():
    con = sqlite3.connect(DB, timeout=30.0)
    con.execute("""CREATE TABLE IF NOT EXISTS jobs(
      url_hash TEXT PRIMARY KEY, title TEXT, company TEXT, location TEXT,
      description TEXT, url TEXT, source TEXT, posted_at TEXT, created_at TEXT,
      applied INTEGER DEFAULT 0)""")
    cols = [r[1] for r in con.execute("PRAGMA table_info(jobs)")]
    if "shortlisted" not in cols:
        con.execute("ALTER TABLE jobs ADD COLUMN shortlisted INTEGER DEFAULT 0")
    if "closed" not in cols:
        con.execute("ALTER TABLE jobs ADD COLUMN closed INTEGER DEFAULT 0")
    if "alert_sent" not in cols:
        con.execute("ALTER TABLE jobs ADD COLUMN alert_sent INTEGER DEFAULT 1")
    if "app_status" not in cols:
        con.execute("ALTER TABLE jobs ADD COLUMN app_status TEXT DEFAULT 'Applied'")
    if "app_notes" not in cols:
        con.execute("ALTER TABLE jobs ADD COLUMN app_notes TEXT DEFAULT ''")
    con.commit()
    return con


def is_job_closed(url):
    if not url or url == "#":
        return False
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        r = requests.get(url, headers=headers, timeout=6, allow_redirects=True)
        if r.status_code in (404, 410):
            return True
        txt = r.text.lower()
        closed_signals = [
            "no longer accepting applications",
            "closed-job__flavor--closed",
            "this job has expired",
            "job is no longer available",
            "this job is closed",
            "posting has expired",
            "position has been filled"
        ]
        return any(sig in txt for sig in closed_signals)
    except Exception:
        return False


def get_jobs(q=""):
    if not os.path.exists(DB):
        return []
    con = ensure_db()
    con.row_factory = sqlite3.Row
    rows = [dict(r) for r in con.execute("SELECT * FROM jobs ORDER BY created_at DESC LIMIT 300")]
    con.close()
    if q:
        q = q.lower()
        rows = [r for r in rows if q in ((r["title"] or "") + (r["company"] or "") + (r["description"] or "")).lower()]
    return rows


def extract_pdf(file):
    try:
        import fitz
        doc = fitz.open(stream=file.read(), filetype="pdf")
        return "\n".join(p.get_text() for p in doc)[:12000]
    except Exception:
        file.seek(0)
        try:
            from pypdf import PdfReader
            r = PdfReader(file)
            return "\n".join(p.extract_text() or "" for p in r.pages)[:12000]
        except Exception as e:
            return f"PDF parse fail: {e}"


def call_gemini_api(prompt, api_key):
    """Invoke Gemini API with automatic model rotation across active endpoints and fast timeout."""
    if not api_key:
        return None
    import requests
    candidate_models = ["gemini-3.8-flash", "gemma-4-26b-a4b-it", "gemini-3.5-flash", "gemini-flash-latest"]
    for model_name in candidate_models:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={api_key}"
        try:
            resp = requests.post(url, json={"contents": [{"parts": [{"text": prompt}]}]}, timeout=6)
            if resp.status_code == 200:
                data = resp.json()
                cands = data.get("candidates", [])
                if cands:
                    parts = cands[0].get("content", {}).get("parts", [])
                    if parts and "text" in parts[0]:
                        return parts[0]["text"]
        except Exception:
            continue
    return None


def heuristic_tailor(resume_text, job, skills):
    """Smart ATS tailor with Prathamesh Jadhav's authentic career details and JD keyword injection."""
    jd_text = (job.get("description") or "").lower()
    user_skills = skills or [
        "PHP", "Laravel", "MySQL", "JavaScript", "HTML5", "CSS3", "React.js", "REST APIs",
        "Node.js", "Express.js", "SQL", "MongoDB", "phpMyAdmin", "AJAX", "jQuery", "Git", "GitHub", "Composer"
    ]
    matched = [s for s in user_skills if s.lower() in jd_text]

    title = job.get("title") or "PHP Developer / Full-Stack Developer"
    company = job.get("company") or "the company"

    base_score = 80
    score = min(96, base_score + len(matched) * 3)

    common_reqs = ["PHP", "Laravel", "MySQL", "JavaScript", "React", "REST APIs", "Git", "Node.js", "Docker", "Tailwind CSS", "Bootstrap", "AJAX"]
    missing = [s for s in common_reqs if s.lower() in jd_text and s.lower() not in resume_text.lower()][:4]

    primary_skills = ", ".join(matched[:4]) if matched else "PHP, MySQL, JavaScript, React, REST APIs"
    summary = (
        f"PHP / Full-Stack Developer with hands-on experience in PHP, MySQL, JavaScript, HTML, CSS, React and Git. "
        f"Currently developing client websites and web applications with backend logic, database integrations, REST APIs, "
        f"and responsive interfaces. Experienced with {primary_skills} and actively expanding backend expertise with Laravel "
        f"aligned with {title} requirements at {company}."
    )

    ts_bullets = [
        "Develop and maintain business websites and web applications using PHP, MySQL, JavaScript, HTML and CSS.",
        "Build backend functionality, CRUD operations, SQL queries and database integrations.",
        "Develop responsive interfaces using JavaScript, React, Bootstrap and Tailwind CSS.",
        "Integrate REST APIs and third-party services; work with PHPMailer and PhpOffice libraries.",
        "Use Git/GitHub for version control and contribute to structured, maintainable development.",
        "Implement WCAG 2.2 AA accessibility improvements, responsive fixes and SEO-related technical updates."
    ]

    cat_skills = {
        "Backend & APIs:": "PHP, Laravel, Node.js, Express.js, REST APIs",
        "Database & Storage:": "MySQL, SQL, MongoDB, phpMyAdmin",
        "Frontend & UI:": "HTML5, CSS3, JavaScript, React.js, Bootstrap, Tailwind CSS",
        "Web & Concepts:": "AJAX, jQuery, JSON, CRUD, MVC, OOP, Responsive Design",
        "Tools & Libraries:": "Git, GitHub, Composer, XAMPP, PHPMailer, PhpOffice, Tiptap"
    }

    return {
        "ats_score": score,
        "missing_skills": missing,
        "tailored_title": f"PHP Developer - {title}" if "php" in title.lower() else f"Full-Stack Developer - {title}",
        "tailored_summary": summary,
        "traction_shastra_bullets": ts_bullets,
        "categorized_skills": cat_skills,
        "tailored_bullets": ts_bullets,
        "cover_line": f"Excited to bring my PHP and full-stack web engineering experience, problem-solving mindset, and dedication to clean code to the {title} role at {company}.",
        "is_smart_fallback": True
    }



def gemini_parse_jd(raw_text):
    """Extract job title, company, location, experience, skills, and apply URL from raw copy-pasted JD text using Gemini + heuristic fallback."""
    api_key = get_gemini_api_key()

    def heuristic_extract(txt):
        lines = [line.strip() for line in txt.splitlines() if line.strip()]
        title = "Software Developer"
        for line in lines[:10]:
            clean_l = re.sub(r'^[^\w]+', '', line)
            if any(k in clean_l.lower() for k in ["developer", "engineer", "lead", "architect", "programmer", "php", "full stack", "frontend", "backend", "intern", "react", "node", "python"]):
                title = clean_l[:60]
                break
        company = "Not detected"
        for line in lines[:12]:
            clean_c = line.strip("•- \t")
            if clean_c != title and 2 <= len(clean_c) <= 40 and not any(k in clean_c.lower() for k in ["apply", "job", "description", "full-time", "remote", "experience", "skills", "location", "years", "permanent", "details", "overview"]):
                company = clean_c
                break
        location = "Not detected"
        lower_txt = txt.lower()
        if "remote" in lower_txt:
            location = "Remote"
        elif "mumbai" in lower_txt:
            location = "Mumbai, Maharashtra"
        elif "bangalore" in lower_txt or "bengaluru" in lower_txt:
            location = "Bengaluru, Karnataka"
        elif "delhi" in lower_txt or "ncr" in lower_txt or "gurgaon" in lower_txt or "noida" in lower_txt:
            location = "Delhi NCR"
        elif "pune" in lower_txt:
            location = "Pune, Maharashtra"
        elif "hyderabad" in lower_txt:
            location = "Hyderabad, Telangana"
        elif "chennai" in lower_txt:
            location = "Chennai, Tamil Nadu"
        elif "india" in lower_txt:
            location = "India"

        exp_raw = "Not specified"
        m_exp = re.search(r'(\d+[\s\-\–to]*\d*)\s*(?:years?|yrs?)', txt, re.IGNORECASE)
        if m_exp:
            exp_raw = m_exp.group(0).strip()

        urls = re.findall(r'https?://[^\s<>"]+|www\.[^\s<>"]+', txt)
        emails = re.findall(r'[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+', txt)
        apply_val = urls[0] if urls else (emails[0] if emails else "")

        return {
            "title": title,
            "company": company,
            "location": location,
            "experience_raw": exp_raw,
            "skills": [],
            "responsibilities": [],
            "apply_url": apply_val,
            "description": txt
        }

    if not api_key:
        return heuristic_extract(raw_text)

    prompt = f"""You are an expert recruitment parser. Analyze this raw copy-pasted job posting text.
Extract metadata accurately. If a field is not explicitly present or clear in text, output "Not detected".

RAW JOB POSTING:
\"\"\"
{raw_text[:5000]}
\"\"\"

Return STRICT JSON only:
{{
  "title": "Concise job title (e.g. 'PHP Developer' or 'React Full Stack Developer')",
  "company": "Company name or 'Not detected'",
  "location": "City/Region/Remote or 'Not detected'",
  "experience_raw": "e.g. '0-4 Years' or '2+ Years' or 'Not specified'",
  "skills": ["Skill1", "Skill2", "Skill3", "...up to 12 top tech skills required..."],
  "responsibilities": ["2-3 key responsibilities"],
  "apply_url": "Apply link or HR email if mentioned in text, otherwise empty string",
  "clean_description": "Cleaned readable job description text without browser headers/footers"
}}"""

    raw_resp = call_gemini_api(prompt, api_key)
    if raw_resp:
        try:
            txt = re.sub(r"```json|```", "", raw_resp).strip()
            m_json = re.search(r"\{.*\}", txt, re.DOTALL)
            if m_json:
                data = json.loads(m_json.group(0))
                return {
                    "title": data.get("title") or "Software Developer",
                    "company": data.get("company") or "Not detected",
                    "location": data.get("location") or "Not detected",
                    "experience_raw": data.get("experience_raw") or "Not specified",
                    "skills": data.get("skills", []),
                    "responsibilities": data.get("responsibilities", []),
                    "apply_url": data.get("apply_url") or "",
                    "description": data.get("clean_description") or raw_text
                }
        except Exception:
            pass

    return heuristic_extract(raw_text)


def gemini_tailor(resume_text, job, skills):
    """Generate tailored resume summary, ATS keywords and bullets with Gemini AI or Smart ATS fallback."""
    api_key = get_gemini_api_key()
    if not api_key:
        return heuristic_tailor(resume_text, job, skills)

    jd = (job.get("description") or "")[:4000]
    prompt = f"""You are an ATS resume tuner for Prathamesh Jadhav, a PHP Developer & Full-Stack Developer.
RESUME:
{resume_text[:4500]}

TARGET JOB: {job.get('title')} at {job.get('company')}
JOB DESCRIPTION:
{jd}

Tailor Prathamesh's resume content specifically for this job. Ground all bullets in his actual work experience at Traction Shastra (Web Developer, Nov 2025 - Present) and his authentic projects (Expense Tracker, NoteStack, Hospital Management System, AI Resume Matcher & ATS Optimizer). Weave in high-priority keywords from the JD naturally with quantifiable achievements.

Return STRICT JSON only:
{{
  "ats_score": 88,
  "missing_skills": ["Skill1", "Skill2"],
  "tailored_title": "PHP Developer - {job.get('title')}",
  "tailored_summary": "...2-3 impactful lines highlighting PHP/Laravel, MySQL, JavaScript/React, REST APIs tailored to {job.get('company')}...",
  "traction_shastra_bullets": [
    "Develop and maintain business websites and web applications using PHP, MySQL, JavaScript, HTML and CSS...",
    "Build backend functionality, CRUD operations, SQL queries and database integrations...",
    "Develop responsive interfaces using JavaScript, React, Bootstrap and Tailwind CSS...",
    "Integrate REST APIs and third-party services; work with PHPMailer and PhpOffice libraries...",
    "Implement WCAG 2.2 AA accessibility improvements, responsive fixes and SEO-related technical updates..."
  ],
  "cover_line": "...1 compelling line for application hook...",
  "categorized_skills": {{
    "Backend & APIs:": "PHP, Laravel, Node.js, Express.js, REST APIs",
    "Database & Storage:": "MySQL, SQL, MongoDB, phpMyAdmin",
    "Frontend & UI:": "HTML5, CSS3, JavaScript, React.js, Bootstrap, Tailwind CSS",
    "Web & Concepts:": "AJAX, jQuery, JSON, CRUD, MVC, OOP, Responsive Design",
    "Tools & Libraries:": "Git, GitHub, Composer, XAMPP, PHPMailer, PhpOffice, Tiptap"
  }}
}}
No commentary or text outside JSON."""

    raw_resp = call_gemini_api(prompt, api_key)
    if raw_resp:
        try:
            txt = re.sub(r"```json|```", "", raw_resp).strip()
            m_json = re.search(r"\{.*\}", txt, re.DOTALL)
            if m_json:
                data = json.loads(m_json.group(0))
                if "tailored_bullets" not in data and "traction_shastra_bullets" in data:
                    data["tailored_bullets"] = data["traction_shastra_bullets"]
                if "traction_shastra_bullets" not in data and "tailored_bullets" in data:
                    data["traction_shastra_bullets"] = data["tailored_bullets"]
                data["is_smart_fallback"] = False
                return data
        except Exception:
            pass

    return heuristic_tailor(resume_text, job, skills)


def sanitize_pdf_text(text):
    """Normalize and clean Unicode characters so standard PDF fonts never crash."""
    if not text:
        return ""
    if not isinstance(text, str):
        text = str(text)
    replacements = {
        "\u2014": " - ",   # em dash —
        "\u2013": "-",     # en dash –
        "\u2012": "-",
        "\u2010": "-",
        "\u2011": "-",
        "\u2022": "-",     # bullet •
        "\u2023": "-",
        "\u25cf": "-",
        "\u2018": "'",     # single quote ‘
        "\u2019": "'",     # single quote ’
        "\u201c": '"',     # double quote “
        "\u201d": '"',     # double quote ”
        "\u2026": "...",   # ellipsis …
        "\u00a0": " ",     # non-breaking space
        "\u200b": "",      # zero-width space
        "\u2003": " ",
        "\u2002": " ",
        "\u20b9": "Rs.",   # Rupee ₹
        "\u20ac": "EUR",
        "\u00a3": "GBP",
        "\u00a9": "(c)",
        "\u00ae": "(R)",
        "\u2122": "(TM)",
    }
    for orig, repl in replacements.items():
        text = text.replace(orig, repl)
    return text.encode("latin-1", "replace").decode("latin-1")


RESUME_TEMPLATES = {
    "Classic ATS": {
        "category": "ATS SAFE",
        "description": "100% black/white typography, strict traditional formatting. Optimal for Taleo & Workday parsers.",
        "badges": ["ATS Safe ✓", "Single Column", "A4", "1 Page"],
        "c_head": (0, 0, 0),
        "c_accent": (35, 35, 35),
        "c_rule": (0, 0, 0),
        "c_text": (25, 25, 25),
        "c_meta": (70, 70, 70),
        "accent_hex": "#1e293b",
    },
    "Modern Clean": {
        "category": "ATS SAFE",
        "description": "Deep navy header, sky-blue role accent, slate dividers. High-growth tech & startups.",
        "badges": ["ATS Safe ✓", "Clean Tech", "A4", "1 Page"],
        "c_head": (15, 23, 42),
        "c_accent": (2, 132, 199),
        "c_rule": (148, 163, 184),
        "c_text": (30, 41, 59),
        "c_meta": (71, 85, 105),
        "accent_hex": "#0284c7",
    },
    "Executive Slate": {
        "category": "ATS SAFE",
        "description": "Refined charcoal headers with subtle slate rules. High scannability for corporate & consulting roles.",
        "badges": ["ATS Safe ✓", "Executive", "A4", "1 Page"],
        "c_head": (30, 41, 59),
        "c_accent": (71, 85, 105),
        "c_rule": (203, 213, 225),
        "c_text": (30, 41, 59),
        "c_meta": (100, 116, 139),
        "accent_hex": "#475569",
    },
    "Tech Emerald": {
        "category": "DEVELOPER",
        "description": "Developer aesthetic with emerald green headings and compact skills hierarchy.",
        "badges": ["ATS Safe ✓", "Developer", "A4", "1 Page"],
        "c_head": (6, 95, 70),
        "c_accent": (5, 150, 105),
        "c_rule": (5, 150, 105),
        "c_text": (30, 41, 59),
        "c_meta": (71, 85, 105),
        "accent_hex": "#10b981",
    },
    "Minimal Dev": {
        "category": "DEVELOPER",
        "description": "Indigo headers with modern high-contrast section rules and compact bullets.",
        "badges": ["ATS Safe ✓", "Modern Dev", "A4", "1 Page"],
        "c_head": (30, 27, 75),
        "c_accent": (79, 70, 229),
        "c_rule": (165, 180, 252),
        "c_text": (30, 41, 59),
        "c_meta": (71, 85, 105),
        "accent_hex": "#6366f1",
    },
    "Compact Dev": {
        "category": "DEVELOPER",
        "description": "Teal accents with high-density spacing. Fits maximum technical depth in a strict 1-page layout.",
        "badges": ["ATS Safe ✓", "High Density", "A4", "1 Page"],
        "c_head": (19, 78, 74),
        "c_accent": (13, 148, 136),
        "c_rule": (45, 212, 191),
        "c_text": (30, 41, 59),
        "c_meta": (71, 85, 105),
        "accent_hex": "#14b8a6",
    },
}


@st.cache_data(show_spinner=False)
def render_pdf_page_to_png(pdf_bytes: bytes, dpi: int = 110) -> bytes:
    """Render page 0 of a PDF bytes object into PNG bytes using PyMuPDF in memory."""
    if not pdf_bytes:
        return b""
    try:
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        page = doc.load_page(0)
        pix = page.get_pixmap(dpi=dpi)
        return pix.tobytes("png")
    except Exception:
        return b""


def build_tailored_resume_pdf(profile, tailored_data, template="Modern Clean"):
    """
    Generate an authentic, high-impact, single-page ATS resume PDF for Prathamesh Jadhav.
    Optimized for recruiter readability and information density (~75-85% A4 page coverage).
    Template styling: 'Classic ATS', 'Modern Clean', 'Executive Slate', 'Tech Emerald', 'Minimal Dev', or 'Compact Dev'.
    """
    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=10)
    pdf.set_margins(12, 12, 12)
    pdf.add_page()

    t_clean = (template or "").lower()
    tpl_cfg = None
    for k, v in RESUME_TEMPLATES.items():
        if k.lower() in t_clean or t_clean in k.lower():
            tpl_cfg = v
            break
    if not tpl_cfg:
        if "classic" in t_clean:
            tpl_cfg = RESUME_TEMPLATES["Classic ATS"]
        elif "tech" in t_clean or "emerald" in t_clean:
            tpl_cfg = RESUME_TEMPLATES["Tech Emerald"]
        elif "executive" in t_clean or "slate" in t_clean:
            tpl_cfg = RESUME_TEMPLATES["Executive Slate"]
        elif "minimal" in t_clean or "indigo" in t_clean:
            tpl_cfg = RESUME_TEMPLATES["Minimal Dev"]
        elif "compact" in t_clean or "teal" in t_clean:
            tpl_cfg = RESUME_TEMPLATES["Compact Dev"]
        else:
            tpl_cfg = RESUME_TEMPLATES["Modern Clean"]

    c_head = tpl_cfg["c_head"]
    c_accent = tpl_cfg["c_accent"]
    c_rule = tpl_cfg["c_rule"]
    c_text = tpl_cfg.get("c_text", (30, 41, 59))
    c_meta = tpl_cfg.get("c_meta", (71, 85, 105))

    # 1. Header (Name, Subtitle, Contact)
    name = profile.get("name") or "Prathamesh Jadhav"
    pdf.set_font("Helvetica", "B", 18)
    pdf.set_text_color(*c_head)
    pdf.cell(0, 7.5, sanitize_pdf_text(name.upper()), new_x="LMARGIN", new_y="NEXT", align="C")

    role_title = tailored_data.get("tailored_title") or profile.get("base_role") or "PHP DEVELOPER | FULL-STACK DEVELOPER"
    pdf.set_font("Helvetica", "B", 10)
    pdf.set_text_color(*c_accent)
    pdf.cell(0, 5, sanitize_pdf_text(role_title.upper()), new_x="LMARGIN", new_y="NEXT", align="C")

    loc_str = "Mumbai, Maharashtra"
    if isinstance(profile.get("location"), dict):
        loc_str = f"{profile['location'].get('city', 'Mumbai')}, {profile['location'].get('state', 'Maharashtra')}"
    phone = profile.get("phone") or "9326671284"
    email = profile.get("email") or "prathameshjadhav2803@gmail.com"
    github = profile.get("github") or "github.com/PrathameshDev2803"
    contact_line = f"{loc_str}   |   {phone}   |   {email}   |   {github}"

    pdf.set_font("Helvetica", "", 9)
    pdf.set_text_color(*c_meta)
    pdf.cell(0, 4.5, sanitize_pdf_text(contact_line), new_x="LMARGIN", new_y="NEXT", align="C")

    pdf.ln(1.8)
    pdf.set_draw_color(*c_rule)
    pdf.set_line_width(0.35)
    pdf.line(pdf.l_margin, pdf.get_y(), 210 - pdf.r_margin, pdf.get_y())
    pdf.ln(3.5)

    def section_hdr(title):
        pdf.set_font("Helvetica", "B", 10.5)
        pdf.set_text_color(*c_head)
        pdf.cell(0, 5.5, sanitize_pdf_text(title), new_x="LMARGIN", new_y="NEXT")
        pdf.set_draw_color(*c_rule)
        pdf.set_line_width(0.25)
        pdf.line(pdf.l_margin, pdf.get_y(), 210 - pdf.r_margin, pdf.get_y())
        pdf.ln(2.5)

    # 2. Professional Summary
    section_hdr("PROFESSIONAL SUMMARY")
    pdf.set_font("Helvetica", "", 9.5)
    pdf.set_text_color(*c_text)
    summary_txt = tailored_data.get("tailored_summary") or profile.get("summary") or (
        "PHP / Full-Stack Developer with hands-on experience in PHP, MySQL, JavaScript, HTML, CSS, React and Git. "
        "Currently working as a Web Developer, developing client websites and web applications with backend logic, "
        "database integration, responsive interfaces, REST APIs and accessibility improvements. "
        "Currently expanding backend expertise with Laravel."
    )
    pdf.multi_cell(0, 4.8, sanitize_pdf_text(summary_txt), new_x="LMARGIN", new_y="NEXT")
    pdf.ln(3.5)

    # 3. Technical Skills
    section_hdr("TECHNICAL SKILLS")
    cat_skills = tailored_data.get("categorized_skills") or {
        "Backend & APIs:": "PHP, Laravel, Node.js, Express.js, REST APIs",
        "Database & Storage:": "MySQL, SQL, MongoDB, phpMyAdmin",
        "Frontend & UI:": "HTML5, CSS3, JavaScript, React.js, Bootstrap, Tailwind CSS",
        "Web & Concepts:": "AJAX, jQuery, JSON, CRUD, MVC, OOP, Responsive Design",
        "Tools & Libraries:": "Git, GitHub, Composer, XAMPP, PHPMailer, PhpOffice, Tiptap"
    }
    for cat_name, cat_val in cat_skills.items():
        pdf.set_font("Helvetica", "B", 9)
        pdf.set_text_color(*c_accent)
        pdf.cell(38, 4.7, sanitize_pdf_text(cat_name if cat_name.endswith(":") else cat_name + ":"), new_x="RIGHT", new_y="TOP")
        pdf.set_font("Helvetica", "", 9.2)
        pdf.set_text_color(*c_text)
        pdf.cell(0, 4.7, sanitize_pdf_text(cat_val), new_x="LMARGIN", new_y="NEXT")
    pdf.ln(3.5)

    # 4. Professional Experience
    section_hdr("PROFESSIONAL EXPERIENCE")
    pdf.set_font("Helvetica", "B", 10.5)
    pdf.set_text_color(*c_head)
    pdf.cell(130, 5, "TRACTION SHASTRA", new_x="RIGHT", new_y="TOP")
    pdf.set_font("Helvetica", "I", 9)
    pdf.set_text_color(*c_meta)
    pdf.cell(0, 5, "Nov 2025 - Present", new_x="LMARGIN", new_y="NEXT", align="R")

    pdf.set_font("Helvetica", "B", 9.5)
    pdf.set_text_color(*c_accent)
    pdf.cell(0, 4.8, "Web Developer", new_x="LMARGIN", new_y="NEXT")

    pdf.set_font("Helvetica", "", 9.2)
    pdf.set_text_color(*c_text)
    ts_bullets = tailored_data.get("traction_shastra_bullets") or tailored_data.get("tailored_bullets", [])
    if not ts_bullets:
        ts_bullets = [
            "Develop and maintain business websites and web applications using PHP, MySQL, JavaScript, HTML and CSS.",
            "Build backend functionality, CRUD operations, SQL queries and database integrations.",
            "Develop responsive interfaces using JavaScript, React, Bootstrap and Tailwind CSS.",
            "Integrate REST APIs and third-party services; work with PHPMailer and PhpOffice libraries.",
            "Use Git/GitHub for version control and contribute to structured, maintainable development.",
            "Implement WCAG 2.2 AA accessibility improvements, responsive fixes and SEO-related technical updates."
        ]
    for b in ts_bullets:
        pdf.multi_cell(0, 4.6, f"-  {sanitize_pdf_text(b)}", new_x="LMARGIN", new_y="NEXT")
        pdf.ln(0.5)
    pdf.ln(3.0)

    # 5. Selected Projects
    section_hdr("SELECTED PROJECTS")
    projects = profile.get("projects") or [
        {
            "name": "Expense Tracker",
            "stack": "PHP & MySQL",
            "repo_url": "https://github.com/PrathameshDev2803/Expense-Tracker",
            "bullets": ["Income/expense management application with CRUD functionality, SQL queries and database integration."]
        },
        {
            "name": "NoteStack",
            "stack": "React / Tiptap",
            "repo_url": "https://github.com/PrathameshDev2803/notestack",
            "bullets": ["Rich-text note-taking application with localStorage, audio recording and reusable React components."]
        },
        {
            "name": "Hospital Management System",
            "stack": "PHP & MySQL",
            "bullets": ["Academic web application with PHP backend, MySQL database and CRUD-based management."]
        },
        {
            "name": "AI Resume Matcher & ATS Optimizer",
            "stack": "Python, Gemini API, Streamlit",
            "bullets": ["AI application for resume analysis, ATS optimization and career-gap analysis using Gemini API."]
        }
    ]
    for prj in projects:
        pdf.set_font("Helvetica", "B", 9.5)
        pdf.set_text_color(*c_head)
        p_name = prj.get("name", "").upper()
        repo_link = prj.get("repo_url", "")
        if repo_link:
            pdf.cell(125, 4.8, sanitize_pdf_text(p_name), link=repo_link, new_x="RIGHT", new_y="TOP")
        else:
            pdf.cell(125, 4.8, sanitize_pdf_text(p_name), new_x="RIGHT", new_y="TOP")
        pdf.set_font("Helvetica", "I", 8.5)
        pdf.set_text_color(*c_meta)
        pdf.cell(0, 4.8, sanitize_pdf_text(prj.get("stack", "")), new_x="LMARGIN", new_y="NEXT", align="R")

        pdf.set_font("Helvetica", "", 9.2)
        pdf.set_text_color(*c_text)
        for b in prj.get("bullets", []):
            pdf.multi_cell(0, 4.5, f"-  {sanitize_pdf_text(b)}", new_x="LMARGIN", new_y="NEXT")
            pdf.ln(0.4)
        pdf.ln(1.8)

    pdf.ln(1.5)

    # 6. Education
    section_hdr("EDUCATION")
    education_entries = profile.get("education") or [
        {
            "degree": "M.Sc. Data Science & Artificial Intelligence",
            "institution": "Chandrabhan Sharma College, Powai, Mumbai",
            "year": "Currently Pursuing"
        },
        {
            "degree": "Bachelor of Computer Applications (BCA)",
            "institution": "Chandrabhan Sharma College, Powai, Mumbai",
            "year": "2024"
        }
    ]
    for edu in education_entries:
        pdf.set_font("Helvetica", "B", 9.5)
        pdf.set_text_color(*c_head)
        pdf.cell(130, 4.8, sanitize_pdf_text(edu.get("degree", "")), new_x="RIGHT", new_y="TOP")
        pdf.set_font("Helvetica", "I", 9)
        pdf.set_text_color(*c_meta)
        pdf.cell(0, 4.8, sanitize_pdf_text(edu.get("year", "")), new_x="LMARGIN", new_y="NEXT", align="R")
        pdf.set_font("Helvetica", "", 9)
        pdf.set_text_color(*c_meta)
        pdf.cell(0, 4.4, sanitize_pdf_text(edu.get("institution", "")), new_x="LMARGIN", new_y="NEXT")
        pdf.ln(2.0)

    return bytes(pdf.output())


def make_pdf(name, role, summary, bullets, skills, template="Modern Clean"):
    """Backward-compatible wrapper for make_pdf that delegates to build_tailored_resume_pdf."""
    p = load_profile()
    if name and name != "Your Name":
        p["name"] = name
    tailored = {
        "tailored_title": role,
        "tailored_summary": summary,
        "traction_shastra_bullets": bullets if bullets else [
            "Develop and maintain business websites and web applications using PHP, MySQL, JavaScript, HTML and CSS.",
            "Build backend functionality, CRUD operations, SQL queries and database integrations.",
            "Develop responsive interfaces using JavaScript, React, Bootstrap and Tailwind CSS.",
            "Integrate REST APIs and third-party services; work with PHPMailer and PhpOffice libraries.",
            "Use Git/GitHub for version control and contribute to structured, maintainable development.",
            "Implement WCAG 2.2 AA accessibility improvements, responsive fixes and SEO-related technical updates."
        ],
        "categorized_skills": {
            "Backend & APIs:": "PHP, Laravel, Node.js, Express.js, REST APIs",
            "Database & Storage:": "MySQL, SQL, MongoDB, phpMyAdmin",
            "Frontend & UI:": "HTML5, CSS3, JavaScript, React.js, Bootstrap, Tailwind CSS",
            "Web & Concepts:": "AJAX, jQuery, JSON, CRUD, MVC, OOP, Responsive Design",
            "Tools & Libraries:": "Git, GitHub, Composer, XAMPP, PHPMailer, PhpOffice, Tiptap"
        }
    }
    return build_tailored_resume_pdf(p, tailored, template=template)



def time_ago(s):
    if not s or str(s).strip().lower() in ("nan", "none", "null", ""):
        return "recent"
    try:
        s_str = str(s).strip()
        if s_str.replace(".", "", 1).isdigit():
            val = float(s_str)
            if val > 1e11:
                val /= 1000.0
            dt = datetime.utcfromtimestamp(val)
        else:
            clean_s = s_str.replace("Z", "").split("+")[0]
            if len(clean_s) == 10 and clean_s.count("-") == 2:
                dt = datetime.strptime(clean_s, "%Y-%m-%d")
            else:
                dt = datetime.fromisoformat(clean_s)

        now = datetime.utcnow()
        mins = int((now - dt).total_seconds() // 60)
        if mins <= 1:
            return "just now"
        if mins < 60:
            return f"{mins} min ago"
        if mins < 1440:
            return f"{mins // 60}h ago"
        days = mins // 1440
        if days == 1:
            return "1d ago"
        if days < 30:
            return f"{days}d ago"
        return f"{days // 30}mo ago"
    except Exception:
        return "recent"


def format_time_remaining(next_run_ts):
    if not next_run_ts:
        return "Paused"
    diff = int(next_run_ts - time.time())
    if diff <= 0:
        return "due now"
    mins = diff // 60
    secs = diff % 60
    if mins > 0:
        return f"{mins}m {secs:02d}s"
    return f"{secs}s"


def job_time(j):
    posted = j.get("posted_at")
    if posted and str(posted).strip().lower() not in ("nan", "none", "null", ""):
        return time_ago(posted)
    return time_ago(j.get("created_at"))


def match_label(s):
    if s >= 60:
        return ("Strong match", "pct pct-hot")
    if s >= 35:
        return ("Potential", "pct pct-mute")
    return ("Weak match", "pct pct-mute")


def top_chips(job, skills, n=4):
    jd = (job.get("description") or "") + " " + (job.get("title") or "")
    jl = jd.lower()
    hits = [s for s in skills if s.lower() in jl]
    return (hits[:n] or skills[:n])


def render_job_card(j, col, is_filtered=False, key_prefix=""):
    label, pct_cls = match_label(j["_score"])
    pct_html = f"<span class='{pct_cls}'>{j['_score']}%" + (" Match" if j["_score"] >= 60 else "") + "</span>"
    chips = "".join(f"<span class='chip'>{html.escape(c)}</span>" for c in top_chips(j, p["skills"]))
    loc = html.escape((j.get("location") or "Remote")[:34])
    pin = "✓" if j["_loc_ok"] else "✕"
    t = html.escape(j.get("title") or "Untitled")
    co = html.escape(j.get("company") or "Unknown")

    is_closed = bool(j.get("closed"))
    card_cls = "job-card filtered-card" if (is_filtered or is_closed) else "job-card"
    if is_closed:
        status_badge = "<span class='filtered-pill' style='background:rgba(239,68,68,0.2);color:#f87171;border-color:rgba(239,68,68,0.4);'>🚫 Closed</span>"
    elif is_filtered:
        status_badge = "<span class='filtered-pill'>Filtered</span>"
    else:
        status_badge = ""

    rej_html = ""
    if is_filtered and j.get("_rej"):
        rej_text = html.escape(" · ".join(j["_rej"][:2]))
        rej_html = f"<div class='filtered-why'>🚫 {rej_text}</div>"

    card_html = (
        f'<div class="{card_cls}">'
        f'{status_badge}{pct_html}'
        f'<div class="job-title">{t}</div>'
        f'<div class="job-company">{co}</div>'
        f'<div class="job-meta">📍 {loc} {pin} · 🕐 {job_time(j)}</div>'
        f'{rej_html}'
        f'<div>{chips}</div>'
        f'<div class="card-foot"><span>{"Closed" if is_closed else ("Filtered" if is_filtered else j["_cat"])} · {j["_score"]}%</span>'
        f'<span style="font-size:10.5px;color:#9ca3af;background:rgba(255,255,255,0.06);padding:1px 6px;border-radius:4px;border:1px solid rgba(255,255,255,0.08);">{html.escape((j.get("source") or "web").upper()[:14])}</span></div>'
        f'</div>'
    )
    with col:
        st.markdown(card_html, unsafe_allow_html=True)
        b1, b2, b3, b4 = st.columns([1, 1, 0.7, 0.35])
        if b1.button("View JD", key=f"{key_prefix}v_{j['url_hash']}"):
            st.session_state.sel = j["url_hash"]
            st.session_state.tailored = None
            st.rerun()
        if b2.button("Tailor →", key=f"{key_prefix}t_{j['url_hash']}"):
            st.session_state.sel = j["url_hash"]
            st.session_state.auto_tailor = True
            st.rerun()
        b3.link_button("Apply", j["url"] or "#")
        close_icon = "↺" if is_closed else "✕"
        close_help = "Reopen job into active feed" if is_closed else "Mark Closed / Dismiss from active"
        if b4.button(close_icon, key=f"{key_prefix}x_{j['url_hash']}", help=close_help):
            con = ensure_db()
            con.execute("UPDATE jobs SET closed=? WHERE url_hash=?", (0 if is_closed else 1, j["url_hash"]))
            con.commit(); con.close()
            st.rerun()


# ---------- state defaults ----------
st.session_state.setdefault("nav_tab", "Jobs")
st.session_state.setdefault("sel", None)
st.session_state.setdefault("flt", "New")
st.session_state.setdefault("only_strong", False)
st.session_state.setdefault("limit", 12)
st.session_state.setdefault("tailored", None)
st.session_state.setdefault("tailored_for", None)
st.session_state.setdefault("resume_name", None)
st.session_state.setdefault("source_flt", "All Sources")
st.session_state.setdefault("sort_mode", "Highest Match %")
st.session_state.setdefault("quick_job", None)
st.session_state.setdefault("quick_tailored", None)
st.session_state.setdefault("quick_run_tailor", False)
st.session_state.setdefault("instant_tailor_expanded", False)
st.session_state.setdefault("fast_tailor_tab_idx", 0)

p = load_profile()

# Load raw jobs
q_search = st.session_state.get("q_search", "")
raw_jobs = get_jobs(q_search)
unique_sources = ["All Sources"] + sorted(list(set(j.get("source", "other") for j in raw_jobs if j.get("source"))))
sel_source = st.session_state.get("source_flt", "All Sources")
if sel_source not in unique_sources:
    sel_source = "All Sources"

# Target search query for HiringCafe & Major Platforms
target_q = q_search.strip() if q_search.strip() else p.get("base_role", "Full Stack Developer")
hc_state = {"searchQuery": target_q, "sortBy": "date"}
hc_encoded = urllib.parse.quote(json.dumps(hc_state))
hc_url = f"https://hiring.cafe/?searchState={hc_encoded}"

# ---------- data: discovery (eligible) + match score ----------
all_jobs = raw_jobs if sel_source == "All Sources" else [j for j in raw_jobs if j.get("source") == sel_source]
scored = []
for j in all_jobs:
    m = compute_match(p, j)
    j["_score"] = m["match_score"]
    j["_cat"] = m["category"]
    j["_eligible"] = m["eligible"]
    j["_loc_ok"] = m["location_match"]
    j["_loc_reason"] = m["location_reason"]
    j["_rej"] = m["rejection_reasons"]
    j["_tiers"] = m["tiers"]
    j["_matched"] = m["matched_skills"]
    j["_missing_core"] = m["missing_core_skills"]
    j["_exp"] = m["experience_detail"]
    j["_core"] = m["jd_primary_stack"]
    scored.append(j)

sort_mode = st.session_state.get("sort_mode", "Highest Match %")
if sort_mode == "Newest":
    scored.sort(key=lambda x: str(x.get("created_at", "")), reverse=True)
elif sort_mode == "Company":
    scored.sort(key=lambda x: str(x.get("company", "")).lower())
else:  # Highest Match %
    scored.sort(key=lambda x: (x["_eligible"], x["_score"]), reverse=True)

# Track last seen fetch
st.session_state.setdefault("_last_seen_fetch", get_scheduler_status().get("last_run"))

# =========================================================================
# TOP NAVIGATION BAR (Concept 1: JobTool | Jobs | Applications | Resume | Settings | 👤)
# =========================================================================
top_brand_col, top_nav_col, top_user_col = st.columns([1.8, 3.8, 2.0], vertical_alignment="center")

with top_brand_col:
    st.markdown("""
    <div class="nav-brand">
        <span class="brand-icon">⚡</span>
        <span class="brand-title">JobTool</span>
        <span class="brand-pro">PRO</span>
    </div>
    """, unsafe_allow_html=True)

with top_nav_col:
    nav_options = ["Jobs", "Applications", "Resume", "Settings"]
    current_tab = st.session_state.get("nav_tab", "Jobs")
    if current_tab not in nav_options:
        current_tab = "Jobs"
    
    selected_nav = st.segmented_control(
        "Main Navigation",
        options=nav_options,
        default=current_tab,
        key="main_nav_selector",
        label_visibility="collapsed"
    )
    # ponytail: handle deselect gracefully so user is never stranded on a blank view
    if selected_nav is None:
        selected_nav = current_tab
    elif selected_nav != current_tab:
        st.session_state["nav_tab"] = selected_nav
        st.rerun()

with top_user_col:
    user_name = p.get("name", "User")
    user_city = p.get("location", {}).get("city", "Mumbai") if isinstance(p.get("location"), dict) else "Mumbai"
    u_c1, u_c2 = st.columns([2.5, 0.9], vertical_alignment="center")
    with u_c1:
        st.markdown(f"""
        <div class="user-pill" title="Target: {p.get('base_role','Developer')} · {p.get('experience_years',2)}y">
            <span class="user-avatar">👤</span>
            <span class="user-name">{html.escape(user_name)}</span>
            <span class="user-dot">·</span>
            <span class="user-loc">{html.escape(user_city)}</span>
        </div>
        """, unsafe_allow_html=True)
    with u_c2:
        if st.button("⚙️", key="btn_quick_settings_top", help="Open Settings"):
            st.session_state["nav_tab"] = "Settings"
            st.rerun()

st.write("")

# Pools
eligible_pool = [j for j in scored if j["_eligible"] and not j.get("closed")]
ineligible_pool = [j for j in scored if not j["_eligible"] and not j.get("closed")]
closed_pool = [j for j in scored if j.get("closed")]
ineligible_pool.sort(key=lambda x: x["_score"], reverse=True)

n_eligible = len(eligible_pool)
n_new = len([j for j in eligible_pool if not j.get("applied")])
n_strong = len([j for j in eligible_pool if j["_score"] >= 60 and not j.get("applied")])
n_applied = len([j for j in scored if j.get("applied") and not j.get("closed")])
n_shortlisted = len([j for j in scored if j.get("shortlisted") and not j.get("closed")])
n_hidden = len(ineligible_pool)
n_closed = len(closed_pool)

active_nav = st.session_state.get("nav_tab", "Jobs")

# =========================================================================
# WORKSPACE 1: JOBS (Clean Job Matches, Concept 1 Filter Pills & Utility Bar)
# =========================================================================
if active_nav == "Jobs":
    flt = st.session_state.get("flt", "New")
    is_filtered_view = False
    if flt == "New":
        view = [j for j in eligible_pool if not j.get("applied")]
    elif flt == "Strong":
        view = [j for j in eligible_pool if j["_score"] >= 60 and not j.get("applied")]
    elif flt == "Filtered":
        view = ineligible_pool
        is_filtered_view = True
    elif flt == "Closed":
        view = closed_pool
        is_filtered_view = True
    elif flt == "Applied":
        view = [j for j in scored if j.get("applied") and not j.get("closed")]
    elif flt == "Shortlisted":
        view = [j for j in eligible_pool if j.get("shortlisted")]
    else:
        view = eligible_pool

    filtered = ineligible_pool

    # Header
    title_text = "Job Matches"
    if flt == "Filtered":
        title_text = "Filtered Out Jobs (Sorted by Match %)"
    elif flt == "Closed":
        title_text = "Closed / Inactive Jobs"
    
    updated = time_ago(max([j.get("created_at", "") for j in scored], default=""))
    status_text = f"<b>{len(view)}</b> matches · <b>{n_strong}</b> strong · updated {updated} · {n_hidden} filtered"
    if flt == "Filtered":
        status_text = f"<b>{len(view)}</b> filtered jobs · sorted by profile match % · stretch / review"
    elif flt == "Closed":
        status_text = f"<b>{len(view)}</b> closed / inactive jobs"

    st.markdown(f"""
    <div class="workspace-header">
        <div class="workspace-title">{title_text}</div>
        <div class="statusbar">{status_text}</div>
    </div>
    """, unsafe_allow_html=True)

    # Filter Pills (Concept 1: [ All 112 ] [ New 112 ] [ Strong 60 ] [ Filtered 45 ] [ Applied 12 ] [ Closed 4 ])
    filter_pill_options = [
        f"All ({n_eligible})",
        f"New ({n_new})",
        f"Strong ({n_strong})",
        f"Filtered ({n_hidden})",
        f"Applied ({n_applied})",
        f"Closed ({n_closed})"
    ]
    cur_flt_name = st.session_state.get("flt", "New")
    def_pill = next((opt for opt in filter_pill_options if opt.startswith(cur_flt_name)), filter_pill_options[1])

    p_col1, p_col2 = st.columns([4.2, 1.2], vertical_alignment="center")
    with p_col1:
        sel_pill = st.pills("Status Filter", filter_pill_options, default=def_pill, key="job_filter_pills", label_visibility="collapsed")
        if sel_pill:
            new_flt = sel_pill.split()[0]
            if new_flt != st.session_state.get("flt"):
                st.session_state["flt"] = new_flt
                st.session_state["only_strong"] = False
                st.rerun()
    with p_col2:
        st.link_button("☕ HiringCafe Radar ↗", hc_url, use_container_width=True, help=f"Check '{target_q}' live on HiringCafe")

    # Search & Source Controls
    sc1, sc2, sc3 = st.columns([3.0, 1.3, 1.1], vertical_alignment="center")
    with sc1:
        search_val = st.text_input(
            "Search jobs",
            value=st.session_state.get("q_search", ""),
            placeholder="Search jobs... (React, PHP, Node, Mumbai, Remote...)",
            label_visibility="collapsed",
            key="inp_job_search"
        )
        if search_val != st.session_state.get("q_search", ""):
            st.session_state["q_search"] = search_val
            st.rerun()
    with sc2:
        src_idx = unique_sources.index(st.session_state.source_flt) if st.session_state.source_flt in unique_sources else 0
        sel_source_choice = st.selectbox(
            "Source",
            unique_sources,
            index=src_idx,
            label_visibility="collapsed",
            key="sel_job_source"
        )
        if sel_source_choice != st.session_state.source_flt:
            st.session_state["source_flt"] = sel_source_choice
            st.rerun()
    with sc3:
        sort_opts = ["Highest Match %", "Newest", "Company"]
        cur_sort_idx = sort_opts.index(st.session_state.sort_mode) if st.session_state.sort_mode in sort_opts else 0
        sel_sort_choice = st.selectbox(
            "Sort",
            sort_opts,
            index=cur_sort_idx,
            label_visibility="collapsed",
            key="sel_job_sort"
        )
        if sel_sort_choice != st.session_state.sort_mode:
            st.session_state["sort_mode"] = sel_sort_choice
            st.rerun()

    # Small Utility Bar (Concept 1: ⚡ Fast Tailor JD / Link ... Fetching ●)
    st.markdown('<div class="utility-container">', unsafe_allow_html=True)
    util_l, util_r = st.columns([1.7, 1.4], vertical_alignment="center")
    with util_l:
        u1, u2, u3, u4 = st.columns([1.3, 1.1, 1.1, 1.2], vertical_alignment="center")
        u1.markdown("<span style='font-size:13px;font-weight:750;color:#f8fafc;'>🔥 Fast Tailor:</span>", unsafe_allow_html=True)
        if u2.button("📋 Paste JD", key="u_btn_jd", use_container_width=True):
            st.session_state.instant_tailor_expanded = True
            st.session_state.fast_tailor_tab_idx = 0
            st.rerun()
        if u3.button("🔗 Paste Link", key="u_btn_link", use_container_width=True):
            st.session_state.instant_tailor_expanded = True
            st.session_state.fast_tailor_tab_idx = 1
            st.rerun()
        if u4.button("🌐 10 Platforms", key="u_btn_plat", use_container_width=True):
            st.session_state.instant_tailor_expanded = True
            st.session_state.fast_tailor_tab_idx = 2
            st.rerun()

    with util_r:
        @st.fragment(run_every="15s")
        def render_utility_sync():
            sched = get_scheduler_status()
            is_fetch = sched.get("is_fetching", False)
            enabled = sched.get("enabled", True)
            next_run = sched.get("next_run")
            last_run = sched.get("last_run")
            last_res = sched.get("last_result") or {}

            # Detect newly completed background fetch
            last_seen = st.session_state.get("_last_seen_fetch")
            if last_run and last_run != last_seen:
                st.session_state["_last_seen_fetch"] = last_run
                new_n = last_res.get("new_rows", 0)
                if new_n > 0:
                    st.toast(f"🎉 Auto-sync: {new_n} new jobs added!", icon="🚀")
                st.rerun(scope="app")

            rem_str = format_time_remaining(next_run) if enabled else "Paused"
            badge_cls = "sync-badge fetching" if is_fetch else ("sync-badge" if enabled else "sync-badge muted")
            badge_icon = "🔄" if is_fetch else ("🟢" if enabled else "⏸️")
            badge_text = "Fetching jobs..." if is_fetch else (f"Sync: {rem_str}" if enabled else "Paused")

            sr1, sr2, sr3 = st.columns([1.5, 0.9, 0.9], vertical_alignment="center")
            with sr1:
                st.markdown(f"<span class='{badge_cls}' style='font-size:11.5px;'>{badge_icon} <b>{badge_text}</b></span>", unsafe_allow_html=True)
            with sr2:
                if st.button("↻ Fetch", key="util_fetch_btn", use_container_width=True, help="Fetch latest jobs immediately"):
                    with st.spinner("Fetching jobs..."):
                        res = trigger_immediate_fetch(include_jobspy=True, max_spy_wanted=20)
                        if res and res.get("status") == "success":
                            st.toast(f"Added {res.get('new_rows', 0)} new jobs!", icon="✅")
                        st.rerun()
            with sr3:
                if st.button("🔍 Clean", key="util_clean_btn", use_container_width=True, help="Clean expired / closed jobs"):
                    with st.spinner("Checking status..."):
                        to_check = [x for x in scored if x["_eligible"] and not x.get("closed")]
                        closed_cnt = 0
                        con = ensure_db()
                        for cj in to_check:
                            if is_job_closed(cj.get("url")):
                                con.execute("UPDATE jobs SET closed=1 WHERE url_hash=?", (cj["url_hash"],))
                                closed_cnt += 1
                        con.commit(); con.close()
                        if closed_cnt:
                            st.toast(f"Cleaned {closed_cnt} jobs!", icon="🧹")
                        else:
                            st.toast("All eligible jobs active!", icon="✓")
                        st.rerun()

        render_utility_sync()
    st.markdown('</div>', unsafe_allow_html=True)

    # Fast Tailor Hub Expander (One-Shot Giant Textarea & Auto-Extraction)
    quick_expanded = bool(st.session_state.get("quick_job") or st.session_state.get("instant_tailor_expanded"))
    with st.expander("⚡ Fast Tailor (Paste JD, Paste Job Link or Platform Search)", expanded=quick_expanded):
        st.markdown("<p style='font-size:12.5px;color:#9ca3af;margin-bottom:8px;'><b style='color:#10b981;'>⚡ Instant ATS Tailoring:</b> Paste raw JD text or any job link. Gemini extracts title, company, location & skills in one shot, computes match score, and generates a tailored ATS resume PDF in 5 seconds.</p>", unsafe_allow_html=True)
        
        q_tab_jd, q_tab_link, q_tab_platforms = st.tabs(["📄 Paste JD", "🔗 Paste Job Link", "🌐 Platform Search"])

        with q_tab_jd:
            st.markdown("<p style='font-size:13px;color:#94a3b8;margin:2px 0 8px 0;'><b style='color:#f8fafc;'>Paste the complete job description below.</b><br/>No formatting required — just copy everything from the job page (Ctrl+A → Ctrl+C → Ctrl+V). Gemini will auto-extract title, company, location, experience, and skills.</p>", unsafe_allow_html=True)
            
            raw_jd_val = st.text_area(
                "Complete Job Description",
                value=st.session_state.get("raw_jd_cache", ""),
                height=240,
                placeholder="Paste complete job description here...\n\n(No formatting required — just copy everything from Indeed, LinkedIn, Naukri, or any company careers page and paste here. AI will extract all details automatically!)",
                key="giant_jd_textarea",
                label_visibility="collapsed"
            )

            col_sub1, col_sub2, col_sub3 = st.columns([1, 1.8, 1])
            with col_sub2:
                if st.button("✨ Analyze & Tailor", type="primary", use_container_width=True, key="btn_analyze_jd_giant"):
                    if not raw_jd_val.strip():
                        st.error("Please paste the job description text first!")
                    else:
                        st.session_state["raw_jd_cache"] = raw_jd_val.strip()
                        with st.spinner("🤖 Gemini is analyzing JD & extracting job title, company, location, experience and skills..."):
                            extracted = gemini_parse_jd(raw_jd_val.strip())
                            j_obj = {
                                "title": extracted.get("title") or "Software Developer",
                                "company": extracted.get("company") or "Not detected",
                                "location": extracted.get("location") or "Not detected",
                                "description": extracted.get("description") or raw_jd_val.strip(),
                                "url": extracted.get("apply_url") or "#",
                                "source": "manual-jd",
                                "posted_at": datetime.utcnow().isoformat(),
                                "experience_raw": extracted.get("experience_raw", "Not specified"),
                                "extracted_skills": extracted.get("skills", []),
                                "extracted_responsibilities": extracted.get("responsibilities", [])
                            }
                            st.session_state.quick_job = j_obj
                            st.session_state.quick_tailored = None
                            st.session_state.quick_run_tailor = True
                            st.session_state.instant_tailor_expanded = True
                            st.rerun()

        with q_tab_link:
            st.markdown("<p style='font-size:12px;color:#9ca3af;margin:0 0 6px 0;'>Paste any job URL from Indeed, LinkedIn, SmartRecruiters, Greenhouse, etc. <b>Indeed URLs auto-extract with 100% precision via GraphQL!</b></p>", unsafe_allow_html=True)
            cl1, cl2 = st.columns([3.5, 1])
            with cl1:
                inp_url = st.text_input("Job Link / URL", placeholder="https://in.indeed.com/viewjob?jk=... or any careers page", label_visibility="collapsed", key="quick_link_val")
            with cl2:
                btn_fetch = st.button("🔍 Fetch Job", use_container_width=True, key="btn_fetch_quick_link")

            if btn_fetch:
                if not inp_url.strip():
                    st.error("Please enter a valid job URL!")
                else:
                    with st.spinner("Extracting job details from link..."):
                        try:
                            fetched = fetch_job_from_url(inp_url.strip())
                            if fetched and (fetched.get("description") or fetched.get("title")):
                                st.session_state.quick_job = fetched
                                st.session_state.quick_tailored = None
                                st.session_state.quick_run_tailor = True
                                st.session_state.instant_tailor_expanded = True
                                st.toast(f"Found: {fetched.get('title')} at {fetched.get('company') or 'Company'}", icon="✓")
                                st.rerun()
                            else:
                                st.error("Could not auto-extract details. Please paste JD text in Tab 1.")
                        except Exception as err:
                            st.error(f"Error fetching URL: {err}")

            # Quick Launch Row for Major Platforms
            platforms = get_major_platforms(p, target_q)
            st.markdown("<div style='margin-top:14px;margin-bottom:8px;font-size:12px;font-weight:700;color:#cbd5e1;'>⚡ 1-Click Search on Major Platforms (Opens pre-filtered for your role; copy link & paste above):</div>", unsafe_allow_html=True)
            p_cols = st.columns(5)
            for i, plat in enumerate(platforms[:5]):
                with p_cols[i]:
                    card_html = (
                        f"<div class='platform-card'>"
                        f"<div class='platform-head'><span class='platform-name'>{plat['icon']} {plat['name']}</span>"
                        f"<span class='platform-badge' style='background:{plat['badge_bg']};color:{plat['badge_color']};border-color:{plat['badge_border']};'>{plat['badge']}</span></div>"
                        f"<div class='platform-desc'>{plat['desc']}</div>"
                        f"</div>"
                    )
                    st.markdown(card_html, unsafe_allow_html=True)
                    st.link_button(f"Search {plat['name'].split()[0]} ↗", plat["url"], use_container_width=True, key=f"q_plat_btn_{plat['id']}")

        with q_tab_platforms:
            platforms = get_major_platforms(p, target_q)
            st.markdown(f"<p style='font-size:12.5px;color:#94a3b8;margin-bottom:12px;'>One-click direct launchers pre-configured for <b>{html.escape(target_q)}</b> in <b>{html.escape(user_city)}</b>. Open any platform, find any job, copy the URL or description, and switch to <b>Tab 1 or Tab 2</b> above to tailor your resume in 5 seconds!</p>", unsafe_allow_html=True)

            row1_cols = st.columns(5)
            for i, plat in enumerate(platforms[:5]):
                with row1_cols[i]:
                    card_html = (
                        f"<div class='platform-card'>"
                        f"<div class='platform-head'><span class='platform-name'>{plat['icon']} {plat['name']}</span>"
                        f"<span class='platform-badge' style='background:{plat['badge_bg']};color:{plat['badge_color']};border-color:{plat['badge_border']};'>{plat['badge']}</span></div>"
                        f"<div class='platform-desc'>{plat['desc']}</div>"
                        f"</div>"
                    )
                    st.markdown(card_html, unsafe_allow_html=True)
                    st.link_button(f"Search {plat['name']} ↗", plat["url"], use_container_width=True, key=f"tab3_plat_{plat['id']}")

            st.write("")
            row2_cols = st.columns(5)
            for i, plat in enumerate(platforms[5:]):
                with row2_cols[i]:
                    card_html = (
                        f"<div class='platform-card'>"
                        f"<div class='platform-head'><span class='platform-name'>{plat['icon']} {plat['name']}</span>"
                        f"<span class='platform-badge' style='background:{plat['badge_bg']};color:{plat['badge_color']};border-color:{plat['badge_border']};'>{plat['badge']}</span></div>"
                        f"<div class='platform-desc'>{plat['desc']}</div>"
                        f"</div>"
                    )
                    st.markdown(card_html, unsafe_allow_html=True)
                    st.link_button(f"Search {plat['name']} ↗", plat["url"], use_container_width=True, key=f"tab3_plat_{plat['id']}")

        # Detected Job & Tailoring Output Area
        qj = st.session_state.get("quick_job")
        if qj:
            st.divider()
            qm = compute_match(p, qj)
            q_score = qm["match_score"]
            q_cat = qm["category"]
            matched_skills = qm["matched_skills"]
            missing_core = qm["missing_core_skills"]

            comp_display = qj.get("company") or "Not detected"
            loc_display = qj.get("location") or "Not detected"
            exp_display = qj.get("experience_raw") or "Not specified"
            missing_str = ", ".join(missing_core) if missing_core else "None"

            # Render display chips: extracted skills + matched skills
            display_skills = qj.get("extracted_skills", []) or matched_skills or top_chips(qj, p["skills"])
            chips_html = "".join([f"<span class='chip'>{html.escape(c)}</span>" for c in display_skills[:10]])

            card_html = f"""
            <div class="detected-card">
                <div class="detected-pill">✓ Job detected</div>
                <div class="detected-title">{html.escape(qj.get('title','Untitled Role'))}</div>
                <div class="detected-company">{html.escape(comp_display)}</div>
                <div class="detected-meta">📍 {html.escape(loc_display)} · ⏳ {html.escape(exp_display)} · 🌐 {html.escape(qj.get('source','manual').upper())}</div>
                <div>{chips_html}</div>
                <div class="detected-divider"></div>
                <div class="detected-match-row">
                    <span class="detected-score">Match: {q_score}% ({q_cat})</span>
                    <span class="detected-missing">Missing: {html.escape(missing_str)}</span>
                </div>
            </div>
            """
            st.markdown(card_html, unsafe_allow_html=True)

            # Trigger Gemini tailoring if requested
            if st.session_state.get("quick_run_tailor"):
                st.session_state.quick_run_tailor = False
                active_key = get_gemini_api_key()
                if not active_key:
                    st.error("⚠️ GEMINI_API_KEY is missing in your .env file! Please enter your key below or in Settings.")
                    quick_k1, quick_k2 = st.columns([3, 1])
                    with quick_k1:
                        inp_key = st.text_input("Gemini API Key", type="password", key="quick_inline_key", placeholder="Paste AQ.Ab8... or AIzaSy...")
                    with quick_k2:
                        if st.button("Save & Tailor", type="primary", use_container_width=True, key="btn_save_inline_tailor"):
                            if inp_key.strip():
                                set_gemini_api_key(inp_key.strip())
                                st.session_state.quick_run_tailor = True
                                st.rerun()
                else:
                    with st.spinner("🤖 Tailoring your resume summary, bullets & keywords to this JD..."):
                        try:
                            out = gemini_tailor(p["resume_text"], qj, p["skills"])
                            st.session_state.quick_tailored = out
                            con = ensure_db()
                            save(con, [qj])
                            con.close()
                            # Advance to template gallery on initial tailor run
                            st.session_state.tailor_step = 2
                        except Exception as e:
                            st.error(f"Tailoring failed: {e}")

            qt = st.session_state.get("quick_tailored")

            # Determine active flow step
            if "tailor_step" not in st.session_state:
                st.session_state["tailor_step"] = 2 if qt else 1
            cur_step = st.session_state.get("tailor_step", 1)

            # Stepper Navigation Header
            st.markdown("<div style='margin-top: 10px;'></div>", unsafe_allow_html=True)
            sn1, sn2, sn3 = st.columns([1, 1, 1])
            with sn1:
                b1_type = "primary" if cur_step == 1 else "secondary"
                if st.button("01  Job & Fit", type=b1_type, use_container_width=True, key="step_nav_1"):
                    st.session_state.tailor_step = 1
                    st.rerun()
            with sn2:
                b2_type = "primary" if cur_step == 2 else "secondary"
                if st.button("02  Template Gallery", type=b2_type, use_container_width=True, key="step_nav_2"):
                    st.session_state.tailor_step = 2
                    st.rerun()
            with sn3:
                b3_type = "primary" if cur_step == 3 else "secondary"
                if st.button("03  AI Resume Studio", type=b3_type, use_container_width=True, key="step_nav_3"):
                    st.session_state.tailor_step = 3
                    st.rerun()

            st.write("")

            # =========================================================================
            # STEP 1: JOB DETAILS & MATCH FIT
            # =========================================================================
            if cur_step == 1:
                btn_c1, btn_c2, btn_c3, btn_c4 = st.columns([1.6, 1.2, 1.2, 0.9])
                with btn_c1:
                    if qt:
                        if st.button("Choose Template (Step 2) →", type="primary", use_container_width=True, key="btn_q_go_step2"):
                            st.session_state.tailor_step = 2
                            st.rerun()
                    else:
                        if st.button("✨ Tailor & Pick Template", type="primary", use_container_width=True, key="btn_q_re_tailor"):
                            st.session_state.quick_run_tailor = True
                            st.rerun()
                with btn_c2:
                    with st.popover("📄 View Full JD", use_container_width=True):
                        st.markdown(f"#### {html.escape(qj.get('title',''))}")
                        st.caption(f"**Company:** {comp_display} · **Location:** {loc_display}")
                        st.text_area("Full Description", value=qj.get("description",""), height=300, disabled=True)
                with btn_c3:
                    with st.popover("✏️ Edit Details", use_container_width=True):
                        st.caption("Override any detected fields if you'd like:")
                        edit_title = st.text_input("Title", value=qj.get("title",""), key="edit_q_title")
                        edit_comp = st.text_input("Company", value=qj.get("company",""), key="edit_q_comp")
                        edit_loc = st.text_input("Location", value=qj.get("location",""), key="edit_q_loc")
                        edit_url = st.text_input("Apply Link / Email", value=qj.get("url",""), key="edit_q_url")
                        if st.button("💾 Update Detected Details", key="btn_save_edited_qj"):
                            qj["title"] = edit_title.strip()
                            qj["company"] = edit_comp.strip()
                            qj["location"] = edit_loc.strip()
                            qj["url"] = edit_url.strip()
                            st.session_state.quick_job = qj
                            st.rerun()
                with btn_c4:
                    if st.button("✕ Reset", use_container_width=True, key="btn_q_reset", help="Clear and paste another JD"):
                        st.session_state.quick_job = None
                        st.session_state.quick_tailored = None
                        st.session_state.tailor_step = 1
                        st.rerun()

            # =========================================================================
            # STEP 2: VISUAL TEMPLATE GALLERY (With Real In-Memory PDF Previews)
            # =========================================================================
            elif cur_step == 2:
                if not qt:
                    qt = heuristic_tailor(p["resume_text"], qj, p["skills"])
                    st.session_state.quick_tailored = qt

                st.markdown("### 🎨 Step 2: Choose Resume Template Style")
                st.caption(f"Pick a template. Your AI-tailored content for **{html.escape(qj.get('title','Role'))}** at **{html.escape(comp_display)}** is inserted automatically. Previews rendered live.")

                sel_template = st.session_state.get("sel_resume_template", "Modern Clean")

                # Category 1: ATS Safe
                st.markdown('<div class="gallery-cat-header">🛡️ ATS Safe Templates (Corporate & Enterprise Scanners)</div>', unsafe_allow_html=True)
                ats_tpls = ["Classic ATS", "Modern Clean", "Executive Slate"]
                cols_ats = st.columns(3, gap="medium")
                for idx, t_name in enumerate(ats_tpls):
                    t_info = RESUME_TEMPLATES[t_name]
                    is_sel = (t_name == sel_template)
                    card_cls = "template-card-box selected" if is_sel else "template-card-box"
                    with cols_ats[idx]:
                        tpl_pdf = build_tailored_resume_pdf(p, qt, template=t_name)
                        thumb_png = render_pdf_page_to_png(tpl_pdf, dpi=85)
                        badges_html = "".join([f"<span class='template-badge-pill safe'>{b}</span>" for b in t_info["badges"]])
                        sel_marker = " <span style='color:#10b981;font-weight:700;'>● ACTIVE</span>" if is_sel else ""

                        st.markdown(f"""
                        <div class="{card_cls}">
                            <div class="template-title-row">
                                <span class="template-name">{t_name}</span>{sel_marker}
                            </div>
                            <div class="template-desc">{t_info['description']}</div>
                            <div>{badges_html}</div>
                        </div>
                        """, unsafe_allow_html=True)

                        if thumb_png:
                            st.image(thumb_png, use_container_width=True)

                        btn_col1, btn_col2 = st.columns([1.5, 1])
                        with btn_col1:
                            btn_label = "✓ Using This" if is_sel else "Use Template →"
                            btn_t = "primary" if is_sel else "secondary"
                            if st.button(btn_label, key=f"btn_sel_ats_{idx}_{t_name.replace(' ','_')}", type=btn_t, use_container_width=True):
                                st.session_state["sel_resume_template"] = t_name
                                st.session_state["tailor_step"] = 3
                                st.rerun()
                        with btn_col2:
                            with st.popover("🔍 Zoom", use_container_width=True):
                                st.markdown(f"#### {t_name}")
                                full_zoom = render_pdf_page_to_png(tpl_pdf, dpi=140)
                                if full_zoom:
                                    st.image(full_zoom, use_container_width=True)

                st.write("")
                # Category 2: Developer
                st.markdown('<div class="gallery-cat-header">💻 Developer Templates (Modern Web & Engineering Portfolios)</div>', unsafe_allow_html=True)
                dev_tpls = ["Tech Emerald", "Minimal Dev", "Compact Dev"]
                cols_dev = st.columns(3, gap="medium")
                for idx, t_name in enumerate(dev_tpls):
                    t_info = RESUME_TEMPLATES[t_name]
                    is_sel = (t_name == sel_template)
                    card_cls = "template-card-box selected" if is_sel else "template-card-box"
                    with cols_dev[idx]:
                        tpl_pdf = build_tailored_resume_pdf(p, qt, template=t_name)
                        thumb_png = render_pdf_page_to_png(tpl_pdf, dpi=85)
                        badges_html = "".join([f"<span class='template-badge-pill safe'>{b}</span>" for b in t_info["badges"]])
                        sel_marker = " <span style='color:#10b981;font-weight:700;'>● ACTIVE</span>" if is_sel else ""

                        st.markdown(f"""
                        <div class="{card_cls}">
                            <div class="template-title-row">
                                <span class="template-name">{t_name}</span>{sel_marker}
                            </div>
                            <div class="template-desc">{t_info['description']}</div>
                            <div>{badges_html}</div>
                        </div>
                        """, unsafe_allow_html=True)

                        if thumb_png:
                            st.image(thumb_png, use_container_width=True)

                        btn_col1, btn_col2 = st.columns([1.5, 1])
                        with btn_col1:
                            btn_label = "✓ Using This" if is_sel else "Use Template →"
                            btn_t = "primary" if is_sel else "secondary"
                            if st.button(btn_label, key=f"btn_sel_dev_{idx}_{t_name.replace(' ','_')}", type=btn_t, use_container_width=True):
                                st.session_state["sel_resume_template"] = t_name
                                st.session_state["tailor_step"] = 3
                                st.rerun()
                        with btn_col2:
                            with st.popover("🔍 Zoom", use_container_width=True):
                                st.markdown(f"#### {t_name}")
                                full_zoom = render_pdf_page_to_png(tpl_pdf, dpi=140)
                                if full_zoom:
                                    st.image(full_zoom, use_container_width=True)

                st.write("")
                st.divider()
                bot_c1, bot_c2 = st.columns([1, 1.8])
                with bot_c1:
                    if st.button("← Back to Job Details", key="btn_tpl_back_job", use_container_width=True):
                        st.session_state.tailor_step = 1
                        st.rerun()
                with bot_c2:
                    if st.button(f"Continue to Resume Studio ({sel_template}) →", type="primary", key="btn_tpl_continue_studio", use_container_width=True):
                        st.session_state.tailor_step = 3
                        st.rerun()

            # =========================================================================
            # STEP 3: AI RESUME STUDIO (Live Content Editor + Live PDF Preview)
            # =========================================================================
            elif cur_step == 3:
                if not qt:
                    qt = heuristic_tailor(p["resume_text"], qj, p["skills"])
                    st.session_state.quick_tailored = qt

                sel_template = st.session_state.get("sel_resume_template", "Modern Clean")

                st.markdown(f"""
                <div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:10px;margin-bottom:12px;">
                    <div>
                        <div style="font-size:20px;font-weight:800;color:#f8fafc;">03 Your Tailored Resume</div>
                        <div style="font-size:13px;color:#94a3b8;"><b>{html.escape(qj.get('title','Role'))}</b> · {html.escape(comp_display)}</div>
                    </div>
                    <div style="background:rgba(16,185,129,0.12);border:1px solid rgba(16,185,129,0.3);border-radius:999px;padding:4px 14px;color:#10b981;font-weight:750;font-size:13.5px;">
                        ⚡ {q_score}% MATCH — Strong fit
                    </div>
                </div>
                """, unsafe_allow_html=True)

                # Two-Column Layout: Left = Editor & AI Audit, Right = Live PDF Preview & Export
                col_left, col_right = st.columns([1.1, 1.1], gap="large")

                with col_left:
                    nav_c1, nav_c2 = st.columns([1.2, 1.8], vertical_alignment="center")
                    with nav_c1:
                        if st.button("← Change Template", key="btn_s3_change_tpl", use_container_width=True):
                            st.session_state.tailor_step = 2
                            st.rerun()
                    with nav_c2:
                        st.markdown(f"<div style='text-align:right;font-size:12px;color:#94a3b8;'>Template: <b style='color:#10b981;'>{sel_template}</b></div>", unsafe_allow_html=True)

                    # AI Changes Audit & Missing Skills Card (The Authenticity Guarantee!)
                    matched_chips_html = "".join([f"<span class='chip' style='background:rgba(16,185,129,0.14);color:#10b981;border-color:rgba(16,185,129,0.3);'>✓ {html.escape(s)}</span>" for s in matched_skills[:8]])

                    missing_list = qt.get("missing_skills", []) or qm.get("missing_core_skills", [])
                    missing_chips_html = "".join([f"<span class='chip' style='background:rgba(239,68,68,0.14);color:#f87171;border-color:rgba(239,68,68,0.3);'>✕ {html.escape(s)}</span>" for s in missing_list[:6]])

                    missing_block = ""
                    if missing_chips_html:
                        missing_block = f"""
                        <div class="ai-warning-card">
                            <div class="ai-warning-title">⚠️ Missing From Your Profile:</div>
                            <div>{missing_chips_html}</div>
                            <div class="ai-warning-note">These were <b>NOT added</b> to your resume. <i>(Authenticity Guarantee: zero fabricated experience)</i></div>
                        </div>
                        """

                    st.markdown(f"""
                    <div class="ai-audit-card">
                        <div class="ai-audit-title">✨ AI Content Tailoring Highlights</div>
                        <div class="ai-audit-item">✓ Target Role Subtitle aligned to <b>{html.escape(qt.get('tailored_title') or qj.get('title',''))}</b></div>
                        <div class="ai-audit-item">✓ Professional summary tailored with high-intent keywords</div>
                        <div class="ai-audit-item">✓ Traction Shastra work bullets prioritized for target stack</div>
                        <div style="margin-top:6px;">{matched_chips_html}</div>
                        {missing_block}
                    </div>
                    """, unsafe_allow_html=True)

                    st.markdown("#### 📝 Edit Content Live")
                    st.caption("Any edit updates the resume preview on the right instantly:")

                    rev_tab1, rev_tab2, rev_tab3, rev_tab4 = st.tabs(["📝 Summary & Title", "💼 Work Experience", "🛠️ Core Skills", "📂 Projects & Edu"])

                    with rev_tab1:
                        edit_tailored_title = st.text_input("Resume Target Subtitle", value=qt.get("tailored_title") or f"PHP Developer - {qj.get('title')}", key="input_qt_role")
                        edit_tailored_summary = st.text_area("Tailored Professional Summary", value=qt.get("tailored_summary", ""), height=120, key="input_qt_summary")
                        if edit_tailored_title != qt.get("tailored_title") or edit_tailored_summary != qt.get("tailored_summary"):
                            qt["tailored_title"] = edit_tailored_title
                            qt["tailored_summary"] = edit_tailored_summary

                    with rev_tab2:
                        st.markdown("**Traction Shastra (Web Developer | Nov 2025 – Present)**")
                        st.caption("Tailored impact bullets aligned with target JD:")
                        ts_bullets_curr = qt.get("traction_shastra_bullets") or qt.get("tailored_bullets", [])
                        ts_text = "\n".join(ts_bullets_curr)
                        edit_ts_bullets = st.text_area("Traction Shastra Bullets (1 per line)", value=ts_text, height=160, key="input_qt_ts_bullets")
                        new_ts_list = [b.strip("- •") for b in edit_ts_bullets.splitlines() if b.strip()]
                        if new_ts_list and new_ts_list != ts_bullets_curr:
                            qt["traction_shastra_bullets"] = new_ts_list
                            qt["tailored_bullets"] = new_ts_list

                    with rev_tab3:
                        st.caption("Categorized technical skills matching JD priorities:")
                        c_skills = qt.get("categorized_skills") or {
                            "Backend & APIs:": "PHP, Laravel, Node.js, Express.js, REST APIs",
                            "Database & Storage:": "MySQL, SQL, MongoDB, phpMyAdmin",
                            "Frontend & UI:": "HTML5, CSS3, JavaScript, React.js, Bootstrap, Tailwind CSS",
                            "Web & Concepts:": "AJAX, jQuery, JSON, CRUD, MVC, OOP, Responsive Design",
                            "Tools & Libraries:": "Git, GitHub, Composer, XAMPP, PHPMailer, PhpOffice, Tiptap"
                        }
                        c_b = st.text_input("Backend & APIs", value=c_skills.get("Backend & APIs:", ""), key="input_sk_backend")
                        c_db = st.text_input("Database & Storage", value=c_skills.get("Database & Storage:", ""), key="input_sk_db")
                        c_fe = st.text_input("Frontend & UI", value=c_skills.get("Frontend & UI:", ""), key="input_sk_frontend")
                        c_cp = st.text_input("Web & Concepts", value=c_skills.get("Web & Concepts:", ""), key="input_sk_concepts")
                        c_tl = st.text_input("Tools & Libraries", value=c_skills.get("Tools & Libraries:", ""), key="input_sk_tools")
                        qt["categorized_skills"] = {
                            "Backend & APIs:": c_b,
                            "Database & Storage:": c_db,
                            "Frontend & UI:": c_fe,
                            "Web & Concepts:": c_cp,
                            "Tools & Libraries:": c_tl
                        }

                    with rev_tab4:
                        st.markdown("**Featured Projects:**")
                        st.markdown("• **Expense Tracker** (PHP & MySQL)")
                        st.markdown("• **NoteStack** (React / Tiptap)")
                        st.markdown("• **Hospital Management System** (PHP & MySQL)")
                        st.markdown("• **AI Resume Matcher & ATS Optimizer** (Python, Gemini API, Streamlit)")
                        st.markdown("**Education:**")
                        st.markdown("• **M.Sc. Data Science & AI** | Chandrabhan Sharma College, Mumbai")
                        st.markdown("• **BCA** | Chandrabhan Sharma College, Mumbai (2024)")

                with col_right:
                    st.markdown("#### 📄 Live Resume Preview")
                    st.caption("Live single-page A4 rendering — updates immediately as you edit:")

                    # Render actual live PDF
                    live_pdf = build_tailored_resume_pdf(p, qt, template=sel_template)
                    live_png = render_pdf_page_to_png(live_pdf, dpi=130)

                    if live_png:
                        st.image(live_png, use_container_width=True)

                    safe_slug = re.sub(r'[^a-z0-9]+', '_', (qj.get('company') or 'company').lower())
                    pdf_filename = f"Prathamesh_Jadhav_{safe_slug}_Resume.pdf"

                    st.markdown("<div style='margin-top: 10px;'></div>", unsafe_allow_html=True)
                    p_col1, p_col2 = st.columns([1.5, 1.2])
                    with p_col1:
                        st.download_button(
                            f"📥 Download PDF ({sel_template.split()[0]})",
                            live_pdf,
                            file_name=pdf_filename,
                            mime="application/pdf",
                            type="primary",
                            use_container_width=True,
                            key="btn_quick_pdf_download"
                        )
                    with p_col2:
                        apply_url = qj.get("url") or "#"
                        comp_name = qj.get('company', 'Company')
                        if apply_url.startswith("http"):
                            st.link_button(f"🚀 Apply on {comp_name[:16]} ↗", apply_url, use_container_width=True)
                        elif "@" in apply_url:
                            subj = urllib.parse.quote(f"Application for {qj.get('title')}")
                            st.link_button(f"✉️ Email {comp_name[:16]} ↗", f"mailto:{apply_url}?subject={subj}", use_container_width=True)
                        else:
                            st.info("Direct link in description")

                    if qt.get("cover_line"):
                        st.info(f"💌 **Suggested Cover Letter Hook:** \"{qt.get('cover_line')}\"")

    # Card Grid + Side Drawer
    drawer_open = bool(st.session_state.sel and any(j["url_hash"] == st.session_state.sel for j in scored))
    main, drawer = st.columns([1.7, 1], gap="large") if drawer_open else (st.container(), None)

    with main:
        if is_filtered_view:
            st.caption(f"Showing **{len(view)}** filtered out jobs sorted by highest profile match score first. Review and apply if open to location/stack stretch:")
        shown = view[:st.session_state.limit]
        for i in range(0, len(shown), 2):
            cols = st.columns(2, gap="medium")
            for k in range(2):
                if i + k >= len(shown):
                    continue
                j = shown[i + k]
                render_job_card(j, cols[k], is_filtered=is_filtered_view)

        if len(view) > st.session_state.limit:
            if st.button(f"Show more ({len(view) - st.session_state.limit} left)", use_container_width=True):
                st.session_state.limit += 12
                st.rerun()
        if not view:
            st.info("No jobs found in this filter.")

        if not is_filtered_view and filtered:
            st.write("")
            with st.expander(f"Filtered out / High Match Stretch ({len(filtered)}) — Review potential stretch roles", expanded=False):
                st.caption("Yeh jobs location, experience ya backend gate ki wajah se filter out hui hain. Lekin agar profile match strong hai (100%, 80%+), toh aap yahan se bhi 'View JD', 'Tailor' ya 'Apply' kar sakte hain:")
                top_filtered = filtered[:8]
                for i in range(0, len(top_filtered), 2):
                    fcols = st.columns(2, gap="medium")
                    for k in range(2):
                        if i + k < len(top_filtered):
                            render_job_card(top_filtered[i + k], fcols[k], is_filtered=True, key_prefix="flt_")
                if len(filtered) > 8:
                    if st.button(f"View All {len(filtered)} Filtered Jobs in Main Feed →", key="view_all_flt_exp"):
                        st.session_state.flt = "Filtered"
                        st.rerun()

    if drawer_open:
        j = next(x for x in scored if x["url_hash"] == st.session_state.sel)
        with drawer:
            st.markdown("<div class='drawer'>", unsafe_allow_html=True)
            dc1, dc2 = st.columns([5, 1])
            dc1.markdown(f"### {html.escape(j.get('title',''))}")
            if dc2.button("✕", key="close_drawer"):
                st.session_state.sel = None
                st.session_state.tailored = None
                st.rerun()
            st.caption(f"{j.get('company','')} · {j.get('location','')} · {j.get('source','')}")
            st.caption(f"{'✓ eligible' if j['_eligible'] else '✕ filtered out'} · "
                       f"📍 {j['_loc_reason']} · exp: {j['_exp']} · stack: {j['_core']}")
            st.metric("Match", f"{j['_score']}%", j["_cat"])
            if j["_rej"]:
                st.warning("**Why filtered:** " + " · ".join(j["_rej"]))
            tiers = j["_tiers"]
            if tiers["must_have"]:
                hit = set(j["_matched"])
                must_line = ", ".join([f"✓ {s}" if s in hit else f"✕ {s}" for s in tiers["must_have"]])
                st.write("**Must-have:**", must_line)
            if tiers["important"]:
                st.write("**Important:**", ", ".join(tiers["important"]))
            if tiers["nice_to_have"]:
                st.write("**Nice-to-have:**", ", ".join(tiers["nice_to_have"]))
            if j["_missing_core"]:
                st.write("**Missing core:**", ", ".join(j["_missing_core"]))
            with st.expander("Why this matches", expanded=False):
                for s in j["_matched"][:8]:
                    st.write(f"• {s}")
                if not j["_matched"]:
                    st.write("• No skill overlap — title-level fit only")
            with st.expander("Job description", expanded=False):
                st.write((j.get("description") or "No description")[:3000])
            a1, a2 = st.columns(2)
            if a1.button("✨ Tailor Resume", type="primary", use_container_width=True, key="drawer_tailor"):
                st.session_state.auto_tailor = True
            a2.link_button("Apply ↗", j["url"] or "#", use_container_width=True)
            s1, s2, s3 = st.columns([1, 1, 1])
            if s1.button("★ Shortlist" if not j.get("shortlisted") else "☆ Unshortlist", key="short_btn"):
                con = ensure_db()
                con.execute("UPDATE jobs SET shortlisted=? WHERE url_hash=?", (0 if j.get("shortlisted") else 1, j["url_hash"]))
                con.commit(); con.close()
                st.rerun()
            if s2.button("Mark applied ✓", key="applied_btn"):
                con = ensure_db()
                con.execute("UPDATE jobs SET applied=1 WHERE url_hash=?", (j["url_hash"],))
                con.commit(); con.close()
                st.rerun()
            is_closed = bool(j.get("closed"))
            if s3.button("Reopen ✓" if is_closed else "🚫 Closed", key="drawer_closed_btn"):
                con = ensure_db()
                con.execute("UPDATE jobs SET closed=? WHERE url_hash=?", (0 if is_closed else 1, j["url_hash"]))
                con.commit(); con.close()
                st.rerun()

            co_name = (j.get('company') or '').strip()
            if co_name and co_name.lower() not in ('unknown', 'tech startup', 'startup'):
                co_state = {"searchQuery": co_name, "sortBy": "date"}
                co_enc = urllib.parse.quote(json.dumps(co_state))
                st.link_button(f"☕ Search '{co_name[:16]}' on HiringCafe ↗", f"https://hiring.cafe/?searchState={co_enc}", use_container_width=True, help=f"Check all open ATS roles at {co_name}")

            if st.session_state.get("auto_tailor"):
                st.session_state.auto_tailor = False
                if not get_gemini_api_key():
                    st.error("⚠️ GEMINI_API_KEY missing in .env or Settings")
                else:
                    with st.spinner("Tailoring resume with AI..."):
                        try:
                            out = gemini_tailor(p["resume_text"], j, p["skills"])
                            st.session_state.tailored = out
                            st.session_state.tailored_for = j["url_hash"]
                        except Exception as e:
                            st.error(f"Tailoring fail: {e}")
            t = st.session_state.get("tailored") if st.session_state.get("tailored_for") == j["url_hash"] else None
            if t:
                st.markdown("<div style='margin-top:8px;'></div>", unsafe_allow_html=True)
                st.markdown(f"**ATS Fit:** `{t.get('ats_score', 85)}/100` · **Target:** {html.escape(t.get('tailored_title') or j['title'])}")
                
                # Live rasterized preview in drawer
                active_tpl = st.session_state.get("sel_resume_template", "Modern Clean")
                pdf_bytes = build_tailored_resume_pdf(p, t, template=active_tpl)
                thumb_png = render_pdf_page_to_png(pdf_bytes, dpi=90)
                if thumb_png:
                    st.image(thumb_png, use_container_width=True)

                d_col1, d_col2 = st.columns([1.2, 1.4])
                with d_col1:
                    safe_co = re.sub(r'[^a-z0-9]+','_',(j.get('company') or 'co').lower())
                    st.download_button("📥 Download PDF", pdf_bytes,
                                       file_name=f"resume_{safe_co}.pdf",
                                       mime="application/pdf", use_container_width=True,
                                       key=f"btn_dw_drawer_{j['url_hash']}")
                with d_col2:
                    if st.button("🎨 Open Studio →", key=f"btn_drawer_open_studio_{j['url_hash']}", use_container_width=True):
                        st.session_state.quick_job = j
                        st.session_state.quick_tailored = t
                        st.session_state.instant_tailor_expanded = True
                        st.session_state.tailor_step = 3
                        st.rerun()
            st.markdown("</div>", unsafe_allow_html=True)


# =========================================================================
# WORKSPACE 2: APPLICATIONS (Pipeline & Tracker)
# =========================================================================
elif active_nav == "Applications":
    st.markdown("""
    <div class="workspace-header">
        <div class="workspace-title">Applications & Pipeline Tracker</div>
        <div class="statusbar">Track your job applications, interviews, shortlisted roles and tailored resumes.</div>
    </div>
    """, unsafe_allow_html=True)

    app_jobs = [j for j in scored if j.get("applied") or j.get("shortlisted")]

    m1, m2, m3, m4 = st.columns(4)
    with m1:
        st.markdown(f'<div class="metric-box"><h3>{n_applied}</h3><p>Total Applied</p></div>', unsafe_allow_html=True)
    with m2:
        st.markdown(f'<div class="metric-box"><h3>{n_shortlisted}</h3><p>Shortlisted</p></div>', unsafe_allow_html=True)
    with m3:
        n_interview = len([j for j in app_jobs if j.get("app_status") == "Interview"])
        st.markdown(f'<div class="metric-box"><h3>{n_interview}</h3><p>Interview Stage</p></div>', unsafe_allow_html=True)
    with m4:
        st.markdown(f'<div class="metric-box"><h3>{len(app_jobs)}</h3><p>Total Tracked</p></div>', unsafe_allow_html=True)

    st.write("")

    if not app_jobs:
        st.info("No applications tracked yet! Head over to **Jobs**, find matching roles, and click **Mark applied ✓** or **★ Shortlist** to track them here.")
        if st.button("Browse Jobs →"):
            st.session_state["nav_tab"] = "Jobs"
            st.rerun()
    else:
        app_sub_flt = st.radio("Show", ["All Tracked", "Applied Only", "Shortlisted Only"], horizontal=True)
        if app_sub_flt == "Applied Only":
            filtered_apps = [j for j in app_jobs if j.get("applied")]
        elif app_sub_flt == "Shortlisted Only":
            filtered_apps = [j for j in app_jobs if j.get("shortlisted")]
        else:
            filtered_apps = app_jobs

        for aj in filtered_apps:
            with st.container():
                st.markdown("<div style='background:#111520;border:1px solid #1e2638;border-radius:10px;padding:12px;margin-bottom:10px;'>", unsafe_allow_html=True)
                ac1, ac2, ac3, ac4 = st.columns([2.5, 1.2, 1.2, 1.0])
                with ac1:
                    st.markdown(f"**{html.escape(aj.get('title','Untitled'))}** at **{html.escape(aj.get('company','Unknown'))}**")
                    st.caption(f"📍 {html.escape(aj.get('location','Remote'))} · 🕒 {job_time(aj)} · Source: {aj.get('source','web').upper()} · Match: {aj.get('_score',0)}%")
                with ac2:
                    current_status = aj.get("app_status") or ("Applied" if aj.get("applied") else "Shortlisted")
                    status_choices = ["Applied", "Screening", "Interview", "Offer", "Rejected", "Archived"]
                    status_idx = status_choices.index(current_status) if current_status in status_choices else 0
                    new_status = st.selectbox("Stage", status_choices, index=status_idx, key=f"app_st_{aj['url_hash']}", label_visibility="collapsed")
                    if new_status != current_status:
                        con = ensure_db()
                        con.execute("UPDATE jobs SET app_status=? WHERE url_hash=?", (new_status, aj["url_hash"]))
                        con.commit(); con.close()
                        st.rerun()
                with ac3:
                    st.link_button("Open Job ↗", aj.get("url") or "#", use_container_width=True)
                with ac4:
                    if st.button("✕ Remove", key=f"app_rm_{aj['url_hash']}", use_container_width=True, help="Remove from application tracker"):
                        con = ensure_db()
                        con.execute("UPDATE jobs SET applied=0, shortlisted=0 WHERE url_hash=?", (aj["url_hash"],))
                        con.commit(); con.close()
                        st.rerun()
                st.markdown("</div>", unsafe_allow_html=True)


# =========================================================================
# WORKSPACE 3: RESUME (Resume & ATS Skills Studio)
# =========================================================================
elif active_nav == "Resume":
    st.markdown("""
    <div class="workspace-header">
        <div class="workspace-title">Resume & ATS Profile Workspace</div>
        <div class="statusbar">Manage your base resume, verify extracted keywords, and inspect profile matching metrics.</div>
    </div>
    """, unsafe_allow_html=True)

    r_col1, r_col2 = st.columns([1.5, 2.5], gap="large")

    with r_col1:
        st.markdown("### 📄 Base Resume")
        if st.session_state.get("resume_name"):
            st.caption(f"Current File: **{st.session_state.resume_name}**")
        
        up_file = st.file_uploader("Upload New Resume (PDF)", type=["pdf"], key="res_tab_uploader")
        if up_file:
            extracted_txt = extract_pdf(up_file)
            p["resume_text"] = extracted_txt
            st.session_state.resume_name = up_file.name
            with open(RESUME_TXT, "w", encoding="utf-8") as f:
                f.write(extracted_txt)
            st.success(f"Uploaded & persisted! Extracted {len(extracted_txt)} characters.")

        st.markdown("#### 🎯 Active Profile")
        st.write(f"**Target Role:** {p.get('base_role','Full Stack Developer')}")
        st.write(f"**Location:** {get_location_label(p)}")
        st.write(f"**Experience:** {p.get('experience_years',2)} Years")
        st.write(f"**Search Terms:** {', '.join(p.get('search_terms', []))}")

        st.markdown("#### 🛠️ Skills & Competencies")
        skills_html = "".join([f"<span class='chip'>{html.escape(s)}</span>" for s in p.get("skills", [])])
        st.markdown(f"<div>{skills_html}</div>", unsafe_allow_html=True)

    with r_col2:
        st.markdown("### 📝 Resume Text Editor")
        st.caption("This text is matched against incoming job descriptions to compute ATS Match Scores and trigger Gemini tailoring.")
        current_res_text = p.get("resume_text", "")
        edited_text = st.text_area("Resume Content", value=current_res_text, height=450, key="res_text_editor")
        
        save_btn, test_btn = st.columns([1, 1.2])
        with save_btn:
            if st.button("💾 Save Resume Text", type="primary", use_container_width=True):
                p["resume_text"] = edited_text
                with open(RESUME_TXT, "w", encoding="utf-8") as f:
                    f.write(edited_text)
                st.success("Resume saved successfully!")
                st.rerun()
        with test_btn:
            if st.button("✨ Generate Master PDF", use_container_width=True):
                bullets = [line.strip("- ") for line in edited_text.splitlines() if line.strip().startswith(("-", "•"))][:6]
                if not bullets:
                    bullets = ["Full stack development across modern web technologies", "REST API design and database optimization"]
                master_pdf = make_pdf(p.get("name", "Developer"), p.get("base_role", "Engineer"), edited_text[:300], bullets, p.get("skills", []))
                st.download_button("📥 Download Master PDF", master_pdf, file_name="master_resume.pdf", mime="application/pdf", use_container_width=True)


# =========================================================================
# WORKSPACE 4: SETTINGS (Scheduler, Alerts, Scraper, Profile)
# =========================================================================
elif active_nav == "Settings":
    st.markdown("""
    <div class="workspace-header">
        <div class="workspace-title">Settings & System Controls</div>
        <div class="statusbar">Configure background job scrapers, search keywords, email alerts, and external API credentials.</div>
    </div>
    """, unsafe_allow_html=True)

    set_t1, set_t2, set_t3, set_t4 = st.tabs(["⚙️ Search & Profile", "🔄 Auto-Sync (15 Min)", "✉️ Email Job Alerts", "🔑 Gemini AI Key"])

    with set_t1:
        st.markdown("### 🎯 Profile & Role Settings")
        c_p1, c_p2 = st.columns(2)
        with c_p1:
            cfg_name = st.text_input("Full Name", value=p.get("name", "Developer"), key="cfg_inp_name")
            cfg_role = st.text_input("Base Role Title", value=p.get("base_role", "Full Stack Web Developer"), key="cfg_inp_role")
            cfg_exp = st.number_input("Experience (Years)", value=int(p.get("experience_years", 2)), min_value=0, max_value=30, key="cfg_inp_exp")
        with c_p2:
            loc_dict = p.get("location", {}) if isinstance(p.get("location"), dict) else {}
            cfg_city = st.text_input("Target City", value=loc_dict.get("city", "Mumbai"), key="cfg_inp_city")
            cfg_state = st.text_input("State", value=loc_dict.get("state", "Maharashtra"), key="cfg_inp_state")
            cfg_country = st.text_input("Country", value=loc_dict.get("country", "India"), key="cfg_inp_country")

        st.markdown("#### 🔍 Search Terms (Job Boards)")
        st.caption("Keywords passed directly to Indeed, LinkedIn, and JobSpy pipelines:")
        cur_terms = ", ".join(p.get("search_terms", []))
        cfg_terms = st.text_input("Search Terms (Comma separated)", value=cur_terms, key="cfg_inp_terms")

        if st.button("💾 Save Profile Settings", type="primary", key="btn_save_profile"):
            p["name"] = cfg_name.strip()
            p["base_role"] = cfg_role.strip()
            p["experience_years"] = int(cfg_exp)
            p["location"] = {"city": cfg_city.strip(), "state": cfg_state.strip(), "country": cfg_country.strip()}
            p["search_terms"] = [t.strip() for t in cfg_terms.split(",") if t.strip()]
            with open(PROFILE, "w", encoding="utf-8") as pf:
                json.dump(p, pf, indent=2)
            st.success("Profile saved successfully!")
            st.rerun()

    with set_t2:
        st.markdown("### 🔄 Automated Background Scraper (15 Min)")
        sched_info = get_scheduler_status()
        sched_enabled = sched_info.get("enabled", True)
        is_fetching = sched_info.get("is_fetching", False)
        last_run = sched_info.get("last_run")
        next_run = sched_info.get("next_run")

        col_sc1, col_sc2 = st.columns([1.5, 1])
        with col_sc1:
            toggle_auto = st.checkbox("Enable Automated Fetching (Every 15 minutes)", value=sched_enabled, key="cb_sched_enable")
            if toggle_auto != sched_enabled:
                set_scheduler_enabled(toggle_auto)
                st.rerun()

            status_str = "🔄 Fetching right now..." if is_fetching else ("Active" if sched_enabled else "Paused")
            st.write(f"**Scheduler Status:** {status_str}")
            st.write(f"**Last Sync:** {time_ago(last_run) if last_run else 'Pending'}")
            st.write(f"**Next Sync:** {format_time_remaining(next_run) if sched_enabled else 'Paused'}")
            st.write(f"**Indexed Jobs in DB:** {len(raw_jobs)} total records")

        with col_sc2:
            st.markdown("#### ⚡ Manual Triggers")
            if st.button("↻ Fetch Now (Indeed + LinkedIn)", use_container_width=True, key="btn_settings_fetch_now"):
                with st.spinner("Scraping active jobs..."):
                    res = trigger_immediate_fetch(include_jobspy=True, max_spy_wanted=20)
                    if res and res.get("status") == "success":
                        st.success(f"Added {res.get('new_rows', 0)} new jobs!")
                    st.rerun()

            if st.button("🔍 Clean Closed / Expired Jobs", use_container_width=True, key="btn_settings_clean_now"):
                with st.spinner("Checking live status..."):
                    to_check = [x for x in scored if x["_eligible"] and not x.get("closed")]
                    closed_cnt = 0
                    con = ensure_db()
                    for cj in to_check:
                        if is_job_closed(cj.get("url")):
                            con.execute("UPDATE jobs SET closed=1 WHERE url_hash=?", (cj["url_hash"],))
                            closed_cnt += 1
                    con.commit(); con.close()
                    if closed_cnt:
                        st.success(f"Cleaned {closed_cnt} closed jobs!")
                    else:
                        st.info("All eligible jobs are active!")
                    st.rerun()

    with set_t3:
        st.markdown("### ✉️ Email Job Alerts (Indeed-Style Digest)")
        smtp_ready = is_smtp_configured()
        smtp_cfg = get_smtp_config()
        recip_curr = smtp_cfg.get("recipient") or p.get("alert_email", "")

        status_color = "#10b981" if smtp_ready else "#f59e0b"
        status_label = "● Ready to Send" if smtp_ready else "● Setup Required"
        st.markdown(f"<p style='color:{status_color};font-weight:700;'>{status_label}</p>", unsafe_allow_html=True)
        st.caption("JobTool sends automated Indeed-style email notifications whenever high-match jobs (100%, 80%+) are discovered.")

        recip_inp = st.text_input("Recipient Email Address", value=recip_curr, placeholder="you@example.com", key="settings_recip_input")

        col_em1, col_em2 = st.columns([1, 1])
        with col_em1:
            if st.button("💾 Save Email Recipient", use_container_width=True, disabled=not bool(recip_inp)):
                p["alert_email"] = recip_inp.strip()
                with open(PROFILE, "w", encoding="utf-8") as pf:
                    json.dump(p, pf, indent=2)
                st.success("Recipient saved!")
                st.rerun()
        with col_em2:
            if st.button("📨 Send Test Email", use_container_width=True, disabled=not bool(recip_inp)):
                with st.spinner("Sending test email..."):
                    res = send_test_email(recip_inp.strip())
                    if res.get("success"):
                        st.success("Test email delivered! Check your inbox 📬")
                    else:
                        st.error(f"Delivery failed: {res.get('error')}")

        with st.expander("ℹ️ How to configure Gmail SMTP in .env", expanded=not smtp_ready):
            st.markdown("""
            To enable automated email alerts from your own email address:
            1. Open Google Account → **Security** → **2-Step Verification**.
            2. At the bottom, click **App Passwords**.
            3. Generate an App Password for **Mail** / **JobTool**.
            4. Add the following to your `.env` file:
            ```env
            SMTP_HOST=smtp.gmail.com
            SMTP_PORT=587
            SMTP_USER=your_email@gmail.com
            SMTP_PASSWORD=your_16_char_app_password
            ALERT_RECIPIENT_EMAIL=your_email@gmail.com
            ```
            """)

    with set_t4:
        st.markdown("### 🔑 Google Gemini AI Configuration")
        curr_key = get_gemini_api_key()
        has_key = bool(curr_key)

        status_color = "#10b981" if has_key else "#f59e0b"
        status_text = f"● Active Key ({curr_key[:6]}...{curr_key[-4:]})" if has_key else "● Missing Key"
        st.markdown(f"<p style='color:{status_color};font-weight:700;'>{status_text}</p>", unsafe_allow_html=True)
        st.caption("JobTool uses Google Gemini to automatically analyze copy-pasted JDs and generate ATS-tailored resumes & cover hooks.")

        key_inp = st.text_input("Gemini API Key", value=curr_key, type="password", key="settings_gemini_key_input", placeholder="Paste AQ.Ab8... or AIzaSy...")

        c_k1, c_k2 = st.columns([1, 1])
        with c_k1:
            if st.button("💾 Save API Key", type="primary", use_container_width=True, key="btn_save_settings_key"):
                set_gemini_api_key(key_inp.strip())
                st.success("Gemini API Key saved successfully to .env and active session!")
                st.rerun()
        with c_k2:
            if st.button("🧪 Test API Connection", use_container_width=True, key="btn_test_gemini_key", disabled=not bool(key_inp)):
                with st.spinner("Testing connection to Google Gemini API..."):
                    test_res = call_gemini_api("Reply 'API Connected' in 2 words", key_inp.strip())
                    if test_res:
                        st.success(f"Connection Successful! Response: {test_res.strip()}")
                    else:
                        st.info("Key is saved! Note: If you receive a rate limit notice on free tier, smart ATS fallback is automatically enabled so you can continue tailoring resumes without delay.")

        with st.expander("ℹ️ How to get a free Google Gemini API Key", expanded=not has_key):
            st.markdown("""
            1. Visit [Google AI Studio](https://aistudio.google.com/app/apikey).
            2. Sign in with your Google account.
            3. Click **Create API key** and select a project.
            4. Copy your key and paste it above, or paste it into `.env` as `GEMINI_API_KEY=your_key`.
            """)
