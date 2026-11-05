"""Application static configuration, thresholds, templates, and UI option lists."""

# -----------------------------------------------------------------------------
# 1. Application Limits & Thresholds
# -----------------------------------------------------------------------------
MAX_UPLOAD_BYTES = 10 * 1024 * 1024
MAX_PDF_PAGES = 25
MAX_DOCX_UNCOMPRESSED_BYTES = 50 * 1024 * 1024
MAX_AI_RESUME_CHARS = 8000

# -----------------------------------------------------------------------------
# 2. Rate Limiting Configuration
# -----------------------------------------------------------------------------
PUBLIC_AI_SESSION_LIMIT = 5
PUBLIC_AI_WINDOW_SECONDS = 15 * 60
PUBLIC_AI_GLOBAL_LIMIT = 40

# -----------------------------------------------------------------------------
# 3. UI Configuration
# -----------------------------------------------------------------------------
ACCENT = "#10b981"

# -----------------------------------------------------------------------------
# 4. Onboarding Configuration
# -----------------------------------------------------------------------------
MANUAL_EXP_LEVELS = {
    "Fresher / Student": 0,
    "0-1 years": 1,
    "1-3 years": 2,
    "3-5 years": 4,
    "5+ years": 6,
}


ONB_PATHS = ["📄 Upload Resume", "✍️ Answer Questions"]

# -----------------------------------------------------------------------------
# 5. Welcome Screen HTML
# -----------------------------------------------------------------------------
WELCOME_PROP_HTML = """<div class="prop-container">
<div class="prop-eyebrow"><span class="eyebrow-dot">●</span><span>ATS APPLICATION WORKSPACE</span></div>
<h1 class="prop-headline">Target any role.<br/><span class="prop-highlight">Tailor with precision.</span></h1>
<p class="prop-desc">
Import any job description or posting link. Get deterministic 0–100 stack scoring, instant skill gap analysis, and verified ATS-tailored resumes in seconds.
</p>
<div class="preview-card-wrap">
<div class="preview-title-row">
<div>
<div class="preview-job-title">Senior Full Stack Developer</div>
<div class="preview-job-meta">
<span class="meta-item"><span class="meta-icon">🏢</span> TechNova</span>
<span class="meta-item"><span class="meta-icon">📍</span> Mumbai (Hybrid)</span>
<span class="meta-item"><span class="meta-icon">💼</span> ₹18–24 LPA</span>
</div>
</div>
<span class="preview-score-badge">87% FIT</span>
</div>
<div class="preview-chips-row">
<span class="pchip hit">React</span>
<span class="pchip hit">Node.js</span>
<span class="pchip hit">PostgreSQL</span>
<span class="pchip hit">REST APIs</span>
<span class="pchip gap">AWS</span>
</div>
<div class="preview-bar-track">
<div class="preview-bar-fill" style="width: 87%;"></div>
</div>
</div>
<div class="prop-benefits">
<div class="prop-benefit"><span class="tick-circle">✔</span><span>Deterministic stack-fit scoring on any pasted JD or link</span></div>
<div class="prop-benefit"><span class="tick-circle">✔</span><span>Project GitHub &amp; live links extracted with each role</span></div>
<div class="prop-benefit"><span class="tick-circle">✔</span><span>ATS resume tailor, verified before you apply</span></div>
</div>
</div>"""

# -----------------------------------------------------------------------------
# 6. Resume PDF Themes
# -----------------------------------------------------------------------------
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

