<div align="center">

# ⚡ JOBSCOUT AI • TECH JOB COPILOT
### *Autonomous Tech Job Aggregator • Multi-Factor Match Engine • Gemini-Powered ATS Tailor*

[![Live Demo](https://img.shields.io/badge/Live_Demo-jobscout--dev.streamlit.app-10b981?style=for-the-badge&logo=streamlit&logoColor=white)](https://jobscout-dev.streamlit.app/)
[![Python](https://img.shields.io/badge/Python-3.10%2B-blue?style=for-the-badge&logo=python&logoColor=white)](https://python.org)
[![Streamlit](https://img.shields.io/badge/Streamlit-1.30%2B-FF4B4B?style=for-the-badge&logo=streamlit&logoColor=white)](https://streamlit.io)
[![Gemini](https://img.shields.io/badge/Google%20Gemini-2.5%20Flash-4285F4?style=for-the-badge&logo=google&logoColor=white)](https://ai.google.dev/)
[![SQLite](https://img.shields.io/badge/SQLite-Zero--Config-003B57?style=for-the-badge&logo=sqlite&logoColor=white)](https://sqlite.org)
[![License](https://img.shields.io/badge/License-MIT-green?style=for-the-badge)](LICENSE)

<br/>

**Tired of manually tuning your resume for every ATS?**
JobScout AI takes a job description you found on any portal — via pasted text or a job link — scores it with deterministic heuristic filters, and uses Google Gemini to tailor your resume & generate ATS-proof PDFs in seconds.

> **Product note:** multi-platform job aggregation and background scraping were intentionally removed. You discover jobs on the portals directly (Naukri, Indeed, LinkedIn, company career sites), then use **Paste JD** or **Paste Link** in JobTool to tailor and track. The Jobs page is an application workspace, not a job board.

[Live Demo](https://jobscout-dev.streamlit.app/) • [Features](#-core-capabilities) • [Architecture](#-architecture-flow) • [Quick Start](#-quick-start) • [Configuration](#-configuration) • [Security](#-security--privacy-first)

---

</div>

## 💥 Core Capabilities

### 1. 📄 Paste JD / Paste Link Workflow
Bring a job you found on any portal:
- **Paste JD**: paste raw job-description text — Gemini extracts title, company, location, experience, and skills.
- **Paste Link**: import a posting URL (SmartRecruiters, Greenhouse, Lever, Indeed, generic career pages with HTML fallback).
- **10-platform launcher**: static outbound links to browse portals manually — zero scraping, zero background fetching.
- If a URL can't be extracted, the app falls back to manual JD paste. No CAPTCHA/proxy bypass, ever.

### 2. 🎯 Multi-Factor Scoring Engine
No generic keyword searching. Every job is evaluated against your personalized `profile.json`:
- **Stack Score**: Matches backend, frontend, database, and tooling keywords.
- **Experience Sanity Check**: Discards jobs demanding 5–10+ years of seniority if you're early in your career.
- **Commute & Region Routing**: Filters jobs by transit lines (e.g., Western/Central Lines in Mumbai) or fully Remote tags.
- **Relevance Index**: Classifies each opening into **STRONG MATCH**, **POSSIBLE**, or **NOT ELIGIBLE**.

### 3. 🤖 Gemini ATS Resume Tailor & PDF Engine
- **Live JD Breakdown**: Inspects the target job description against your master resume.
- **AI Customization**: Reframes technical summaries and project bullet points with action verbs and target keywords.
- **1-Click PDF Compilation**: Uses `fpdf2` and `PyMuPDF` to export an ultra-clean, machine-readable ATS-compliant PDF.

### 4. 🗂️ Application Workspace & Tracker
- Jobs page answers one question: *"Have you found a job? Let's tailor your resume for it."*
- Quick Actions command bar: **Paste JD** / **Paste Link** / **10 Platforms**.
- Built-in Application Tracker with status states (`Applied`, `Interview`, `Offer`, `Rejected`).

### 5. 📄 Onboarding Resume Autofill
- Upload **PDF, DOCX, or TXT** on Step 2 and stay on Step 2.
- Text is extracted locally, then categorized by Gemini into name, contact, links, city, role, skills, experience, education, and projects.
- Full extracted profile preview appears immediately; fields are prefilled and editable.
- One bounded AI call per new file, cached by hash. **Analyze** reuses the cache and never calls Gemini again.
- If the public AI key is missing or quota is exhausted, local extraction still fills the preview and the UI shows a **local fallback** badge.
- Public uploads use `GEMINI_PUBLIC_API_KEY`; the owner workspace key is never exposed to guests.

---

## 🏗️ Architecture Flow

```mermaid
graph TD
    subgraph Input [Manual Job Input]
        JD[Paste JD text]
        Link[Paste Link - ATS APIs + HTML fallback]
        Portals[10-platform static launcher - outbound only]
    end

    subgraph Core [Engine & Matching Core]
        Store[(jobs.db SQLite - tracker store)]
        Matcher[matcher.py - Stack, Location & YOE Scoring]
    end

    subgraph Output [User Interfaces]
        UI[app.py - Streamlit Workspace: Jobs / Applications / Resume / Settings]
        AI[Google Gemini - ATS Resume Tailor]
        PDF[fpdf2 + PyMuPDF - ATS PDF + Download]
    end

    JD & Link --> Matcher
    Matcher --> UI
    UI --> AI
    AI --> PDF
```

---

## ⚡ Quick Start

### 1. Clone & Set Up Environment
```bash
# Clone the repository
git clone https://github.com/PrathameshDev2803/jobscout-ai.git
cd jobscout-ai

# Create virtual environment
python -m venv .venv

# Activate virtual environment
# Windows:
.venv\Scripts\activate
# Linux/macOS:
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### 2. Configure Environment (`.env`)
```bash
cp .env.example .env
```
Open `.env` and fill in your keys:
```env
# Owner/workspace Gemini key (https://aistudio.google.com/app/apikey)
GEMINI_API_KEY=your_owner_gemini_key_here

# Separate low-quota key for public onboarding categorization
GEMINI_PUBLIC_API_KEY=your_public_gemini_key_here

# Password that unlocks owner mode; leave blank for demo-only deployment
OWNER_PASSWORD=your_owner_password_here
```

Use a separate Google AI Studio project/key for `GEMINI_PUBLIC_API_KEY`. Public uploads
must not spend the owner workspace quota. If it is empty, public onboarding falls back
to local extraction.

### 3. Launch App
```bash
streamlit run app.py
```

Windows detached launcher with health check:
```powershell
.\start_streamlit.ps1
```
> The app will automatically initialize `profile.json` and `resume.txt` on first launch from safe templates. You can customize them directly in the **Settings** tab.

---

## 📂 Repository Structure

```text
├── app.py                 # Streamlit workspace (Jobs / Applications / Resume / Settings), ATS Tailor & Studio
├── fetch.py               # Tracker store + single-URL job import (Paste Link)
├── matcher.py             # Deterministic scoring (Stack, Location, Seniority)
├── profile.example.json   # Base configuration profile template
├── resume.example.txt     # Clean plain-text master resume template
├── requirements.txt       # Production dependencies
├── start_streamlit.ps1    # Windows detached launcher + health check
├── .env.example           # Environment template
└── .gitignore             # Airtight protection for PII, keys, and DBs
```

---

## 🛡️ Security & Privacy First

- **Zero PII in Git**: `profile.json`, `resume.txt`, `jobs.db`, and `demo.db` are strictly git-ignored.
- **No Hardcoded Secrets**: All keys load from `.env` or Streamlit secrets. Gemini keys travel in request headers, never URLs.
- **Public/Owner Key Isolation**: public onboarding uses `GEMINI_PUBLIC_API_KEY`; guests never receive or spend `GEMINI_API_KEY`.
- **Resume Privacy Notice**: onboarding tells users that extracted resume text is sent to Google Gemini for categorization when AI is available.
- **Session-Only Upload Cache**: parsed profiles are cached by file hash in the browser session, not written to disk.
- **Sanitized Templates**: cloned instances start with mock profiles that won't break on a fresh clone.

---

## 🤝 Contributing

Contributions, issues, and feature requests are welcome!  
Feel free to check [issues page](https://github.com/PrathameshDev2803/jobscout-ai/issues).

---

## 📄 License

Distributed under the **MIT License**. See `LICENSE` for more information.

<div align="center">
  <sub>Built with ☕, Python, and relentless automation. Star ⭐ this repo if it saved you time!</sub>
</div>
