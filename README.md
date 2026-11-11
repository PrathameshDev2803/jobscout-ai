# ⚡ JobScout AI — Tech Job Copilot

**An AI-assisted job application workspace that helps you evaluate job descriptions, tailor your resume, generate ATS-friendly PDFs, and track applications.**

[![Live Demo](https://img.shields.io/badge/Live_Demo-jobscout--dev.streamlit.app-10b981?style=for-the-badge&logo=streamlit&logoColor=white)](https://jobscout-dev.streamlit.app/)
[![Python](https://img.shields.io/badge/Python-3.10%2B-blue?style=for-the-badge&logo=python&logoColor=white)](https://python.org)
[![Streamlit](https://img.shields.io/badge/Streamlit-1.30%2B-FF4B4B?style=for-the-badge&logo=streamlit&logoColor=white)](https://streamlit.io)
[![Google Gemini](https://img.shields.io/badge/Google_Gemini-AI-4285F4?style=for-the-badge&logo=google&logoColor=white)](https://ai.google.dev/)
[![SQLite](https://img.shields.io/badge/SQLite-Database-003B57?style=for-the-badge&logo=sqlite&logoColor=white)](https://sqlite.org)

## Live Demo

**[Open JobScout AI](https://jobscout-dev.streamlit.app/)**

## Overview

JobScout AI is a Python and Streamlit application designed to make the job application workflow more focused and structured. Instead of manually rewriting a resume for every opportunity, users can bring a job description into the workspace, evaluate role fit, tailor resume content with Google Gemini, export an ATS-friendly PDF, and track application progress.

**Product note:** Job discovery happens on external portals. JobScout AI focuses on the workflow after you find a role: paste a job description or link, assess fit, prepare a tailored resume, and manage the application. It does not run background scraping or operate as a job board.

## Core Capabilities

### 1. Job Description Import
- Paste a job description directly into the workspace.
- Import a job posting from a URL when supported.
- Extract key details such as role, company, location, experience, and skills.
- Fall back to manual JD entry when a page cannot be imported.

### 2. Multi-Factor Job Fit Scoring
- Compare a role's technical stack with a personalized profile.
- Check experience requirements against the candidate's level.
- Consider location, commute preferences, and remote roles.
- Categorize results as **Strong Match**, **Possible**, or **Not Eligible**.

### 3. Gemini-Powered Resume Tailoring
- Analyze a target job description against a master resume.
- Generate tailored summaries and project bullet points.
- Emphasize relevant skills and role-specific keywords while retaining the candidate's experience.
- Export a clean, machine-readable PDF designed for ATS compatibility.

### 4. Resume Onboarding and Profile Extraction
- Upload PDF, DOCX, or TXT resumes.
- Extract resume text locally and use Gemini to categorize profile information when configured.
- Review and edit extracted details before using them.
- Use a local extraction fallback when public AI configuration is unavailable.

### 5. Application Workspace
- Track opportunities through statuses such as Applied, Interview, Offer, and Rejected.
- Keep job details and application progress organized in one place.
- Use quick actions to paste a JD, import a link, or open external job platforms.

## Tech Stack

- **Language:** Python 3.10+
- **Application UI:** Streamlit
- **AI integration:** Google Gemini API
- **Data storage:** SQLite
- **Matching:** Custom deterministic scoring logic
- **PDF generation and processing:** fpdf2, PyMuPDF
- **Data and utilities:** pandas, requests

## Architecture

The application combines a Streamlit workspace, a deterministic job-fit scoring engine, local SQLite-backed application tracking, Gemini-powered resume customization, and PDF export utilities.

## Run Locally

### Prerequisites
- Python 3.10+
- pip

### Installation

```bash
git clone https://github.com/PrathameshDev2803/jobscout-ai.git
cd jobscout-ai

python -m venv .venv

# Windows
.venv\Scripts\activate

# macOS / Linux
source .venv/bin/activate

pip install -r requirements.txt
```

### Configure environment

Copy `.env.example` to `.env` and configure the keys you intend to use:

```env
GEMINI_API_KEY=your_owner_gemini_key
GEMINI_PUBLIC_API_KEY=your_public_gemini_key
OWNER_PASSWORD=your_owner_password
```

Use separate Google AI Studio keys for owner and public workflows. Never commit real API keys, passwords, personal profiles, resume files, or database files.

### Start the application

```bash
streamlit run app.py
```

## Security and Privacy

- Sensitive profile, resume, database, and environment files are excluded from Git.
- API keys are read from environment variables or Streamlit secrets.
- Public onboarding uses a separate Gemini key from the owner workspace.
- Resume text may be sent to Google Gemini for categorization when AI features are enabled; users should review the application's privacy notice before uploading personal documents.

## Why I Built It

I built JobScout AI to make the repetitive parts of applying for technical roles more manageable. The project brought together practical Python application development, deterministic matching logic, LLM integration, document processing, PDF generation, and application-state management in one usable workflow.

## What This Project Demonstrates

- Building a multi-page Python application with Streamlit.
- Integrating Google Gemini into a structured workflow.
- Designing explainable, deterministic matching logic.
- Processing resume documents and generating PDFs.
- Managing application data with SQLite.
- Separating public-facing AI usage from owner configuration.
- Writing tests around core application workflows.

## Roadmap

Potential future improvements include deeper resume version management, expanded application analytics, richer job-fit explanations, and additional supported job-link import sources.

## Author

**Prathamesh Jadhav**  
Full-Stack Developer

---

*Built with Python, Streamlit, Google Gemini, and a focus on making job applications more intentional.*
