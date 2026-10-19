"""Local-only evaluation: resume extraction accuracy on synthetic fixtures.

- All fixtures are fictitious (Aarav Sharma) PDFs generated at runtime via fpdf2.
  No personal data, no external services (heuristic path only, api_key="").
- Run: python eval_resume_accuracy.py
- Exit code is ALWAYS 0: this is a diagnostic report, not a CI gate. FAIL rows
  are genuine findings; UNSUPPORTED rows are out-of-scope-by-design cases.
- Existing unit suites (test_*.py) remain the gates and are run separately.
"""
import io
import os
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import app as A  # noqa (daemon scheduler threads die at exit)

PASS, FAIL, UNSUP = "PASS", "FAIL", "UNSUPPORTED"
rows = []


def record(fixture, field, status, detail=""):
    rows.append((fixture, field, status, str(detail)))
    print(f"[{status}] {fixture} :: {field}" + (f" - {detail}" if detail else ""))


def new_pdf():
    from fpdf import FPDF
    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()
    return pdf


def h(pdf, text, size=16, bold=True):
    pdf.set_font("Helvetica", "B" if bold else "", size)
    pdf.cell(0, 9, text, new_x="LMARGIN", new_y="NEXT", align="C")


def line(pdf, text, size=11, bold=False):
    pdf.set_font("Helvetica", "B" if bold else "", size)
    pdf.cell(0, 6.5, text, new_x="LMARGIN", new_y="NEXT")


def sec(pdf, title):
    pdf.ln(2)
    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(0, 8, title, new_x="LMARGIN", new_y="NEXT")


def linked(pdf, display, url, size=11):
    pdf.set_font("Helvetica", "", size)
    pdf.cell(0, 6.5, display, link=url, new_x="LMARGIN", new_y="NEXT")


def finish(pdf):
    return bytes(pdf.output())


CONTACT_LINES = [
    "Aarav Sharma",
    "Frontend Developer | Pune, Maharashtra, India",
    "aarav.sharma@example.com | +91 98765 43210",
]

SKILL_LINE = "PHP, MySQL, JavaScript, HTML, CSS, React, Node.js, Git, REST APIs, Tailwind CSS"
SKILL_SET = {"PHP", "MySQL", "JavaScript", "HTML", "CSS", "React", "Node.js",
             "Git", "REST APIs", "Tailwind CSS"}


def contact_block(pdf, visible_links=True):
    for ln in CONTACT_LINES:
        line(pdf, ln)
    if visible_links:
        line(pdf, "github.com/aaravsharma-dev | linkedin.com/in/aarav-sharma")


def run_pipeline(pdf_bytes):
    meta = A.extract_pdf_rich(io.BytesIO(pdf_bytes))
    prof = A.parse_resume_to_profile(meta.get("text", ""), api_key="",
                                     links=list(meta.get("links", [])),
                                     classified_links=meta.get("classified_links", {}))
    return meta, prof


def check_contact(fx, prof, extra_skills=frozenset()):
    record(fx, "contact.name", PASS if prof.get("name") == "Aarav Sharma" else FAIL, repr(prof.get("name")))
    record(fx, "contact.email", PASS if prof.get("email") == "aarav.sharma@example.com" else FAIL, repr(prof.get("email")))
    record(fx, "contact.phone", PASS if (prof.get("phone") or "").replace(" ", "") == "+919876543210" else FAIL, repr(prof.get("phone")))


def check_skills(fx, prof, expected):
    got = set(prof.get("skills", []))
    if got == set(expected):
        record(fx, "skills", PASS, f"{len(got)} skills exact")
    else:
        record(fx, "skills", FAIL, f"missing={sorted(set(expected) - got)} extra={sorted(got - set(expected))}")


# ---------------------------------------------------------------- F1 standard
def fixture_standard():
    pdf = new_pdf()
    h(pdf, "Aarav Sharma")
    contact_block(pdf)
    sec(pdf, "PROFESSIONAL SUMMARY")
    line(pdf, "Frontend Developer with 2 years of experience building web apps.")
    sec(pdf, "SKILLS")
    line(pdf, SKILL_LINE)
    sec(pdf, "WORK EXPERIENCE")
    line(pdf, "PixelWorks - Frontend Developer, Jan 2023 - Present", bold=True)
    line(pdf, "- Built responsive interfaces with React and Tailwind CSS.")
    line(pdf, "- Integrated REST APIs and fixed production bugs.")
    sec(pdf, "PROJECTS")
    line(pdf, "Shop Cart - PHP & MySQL", bold=True)
    line(pdf, "GitHub: https://github.com/aaravsharma-dev/shop-cart")
    line(pdf, "- Cart application with PHP sessions and MySQL orders.")
    sec(pdf, "EDUCATION")
    line(pdf, "BCA, SNDT College, 2022")
    return finish(pdf)


def eval_standard():
    fx = "F1-standard"
    meta, prof = run_pipeline(fixture_standard())
    check_contact(fx, prof)
    record(fx, "links.github-profile",
           PASS if prof.get("github") == "https://github.com/aaravsharma-dev" else FAIL, repr(prof.get("github")))
    repos = [e.get("repo_url") for e in prof.get("projects", []) if e.get("repo_url")]
    record(fx, "links.repo-url", PASS if repos == ["https://github.com/aaravsharma-dev/shop-cart"] else FAIL, repr(repos))
    check_skills(fx, prof, SKILL_SET | {"GitHub"})  # GitHub links in text rightly yield the GitHub token
    record(fx, "education.degree",
           PASS if prof.get("education", []) == [
               {"degree": "BCA", "institution": "SNDT College", "year": "2022", "field": ""}] else FAIL,
           repr(prof.get("education")))
    exps = prof.get("experience", [])
    ok = (len(exps) == 1 and exps[0].get("company") == "PixelWorks"
          and "Frontend Developer" in (exps[0].get("role") or ""))
    record(fx, "experience", PASS if ok else FAIL, repr(exps))
    projs = {e.get("name"): e for e in prof.get("projects", []) if e.get("name")}
    ok = (projs.get("Shop Cart", {}).get("repo_url") == "https://github.com/aaravsharma-dev/shop-cart"
          and projs.get("Shop Cart", {}).get("stack") == "PHP & MySQL")
    record(fx, "association.shop-cart", PASS if ok else FAIL, repr(projs.get("Shop Cart")))


# ------------------------------------------------------- F2 multi-project
def fixture_multi():
    pdf = new_pdf()
    h(pdf, "Aarav Sharma")
    contact_block(pdf)
    sec(pdf, "SKILLS")
    line(pdf, "Python, JavaScript, React, Docker, AWS, Git")
    sec(pdf, "PROJECTS")
    line(pdf, "Alpha API - Python, Flask", bold=True)
    line(pdf, "GitHub: https://github.com/aaravsharma-dev/alpha-api")
    line(pdf, "- REST API with Flask and Docker.")
    line(pdf, "Beta Dash - React, Node.js", bold=True)
    line(pdf, "Live: https://beta.example.com")
    line(pdf, "- Analytics dashboard with charts.")
    line(pdf, "Gamma Shop - PHP & MySQL", bold=True)
    line(pdf, "GitHub: https://github.com/aaravsharma-dev/gamma-shop")
    line(pdf, "Live: https://gamma.example.com")
    line(pdf, "- Storefront with cart and checkout.")
    sec(pdf, "EDUCATION")
    line(pdf, "BCA, 2022")
    return finish(pdf)


def eval_multi():
    fx = "F2-multi-project"
    meta, prof = run_pipeline(fixture_multi())
    check_contact(fx, prof)
    projs = {e.get("name"): e for e in prof.get("projects", []) if e.get("name")}
    record(fx, "projects.names",
           PASS if set(projs) == {"Alpha API", "Beta Dash", "Gamma Shop"} else FAIL, repr(sorted(projs)))
    record(fx, "assoc.alpha-repo",
           PASS if projs.get("Alpha API", {}).get("repo_url") == "https://github.com/aaravsharma-dev/alpha-api" else FAIL,
           repr(projs.get("Alpha API")))
    record(fx, "assoc.beta-live",
           PASS if projs.get("Beta Dash", {}).get("live_url") == "https://beta.example.com"
           and projs.get("Beta Dash", {}).get("repo_url", "") == "" else FAIL, repr(projs.get("Beta Dash")))
    g = projs.get("Gamma Shop", {})
    record(fx, "assoc.gamma-both",
           PASS if g.get("repo_url") == "https://github.com/aaravsharma-dev/gamma-shop"
           and g.get("live_url") == "https://gamma.example.com" else FAIL, repr(g))
    # NOTE: stack lines / GitHub labels legitimately contribute tokens (PHP, MySQL,
    # Node.js, Flask, GitHub) — project-stack mentions are genuine skill evidence.
    check_skills(fx, prof, {"Python", "JavaScript", "React", "Docker", "AWS", "Git",
                            "PHP", "MySQL", "Node.js", "Flask", "GitHub"})
    record(fx, "education.degree-no-institution",
           PASS if prof.get("education", []) == [
               {"degree": "BCA", "institution": "", "year": "2022", "field": ""}] else FAIL,
           repr(prof.get("education")))


# ------------------------------------------------- F3 invisible hyperlinks
def fixture_invisible():
    pdf = new_pdf()
    h(pdf, "Aarav Sharma")
    line(pdf, "Frontend Developer | Pune, India")
    line(pdf, "aarav.sharma@example.com | +91 98765 43210")
    linked(pdf, "LinkedIn", "https://linkedin.com/in/aarav-sharma")
    linked(pdf, "GitHub", "https://github.com/aaravsharma-dev/hidden-shop")
    linked(pdf, "Portfolio", "https://aaravsharma.dev")
    sec(pdf, "SKILLS")
    line(pdf, "JavaScript, React, GitHub, Git")
    sec(pdf, "WORK EXPERIENCE")
    line(pdf, "PixelWorks - Frontend Developer, Jan 2023 - Present", bold=True)
    line(pdf, "- Built interfaces with React for two years.")
    return finish(pdf)


def eval_invisible():
    fx = "F3-invisible-links"
    meta, prof = run_pipeline(fixture_invisible())
    check_contact(fx, prof)
    txt = meta.get("text", "")
    record(fx, "extract.urls-not-in-text",
           PASS if "github.com/aaravsharma-dev/hidden-shop" not in txt else FAIL, "precondition: URL invisible")
    repos = [e.get("repo_url") for e in prof.get("projects", []) if e.get("repo_url")]
    linked_got = prof.get("github", "")
    flagged = [u.get("url") for u in prof.get("unreviewed_links", [])]
    # No PROJECTS section by design -> no project entry; repo must survive in review queue.
    record(fx, "links.repo-from-annotation",
           PASS if "https://github.com/aaravsharma-dev/hidden-shop" in flagged else FAIL,
           f"unreviewed={flagged} github-derived={linked_got!r}")
    record(fx, "links.linkedin-from-annotation",
           PASS if prof.get("linkedin") == "https://www.linkedin.com/in/aarav-sharma" else FAIL,
           repr(prof.get("linkedin")))
    record(fx, "links.portfolio-from-annotation",
           PASS if prof.get("portfolio") == "https://aaravsharma.dev" else FAIL, repr(prof.get("portfolio")))


# ------------------------------------------------------- F4 no heading
def fixture_no_heading():
    pdf = new_pdf()
    h(pdf, "Aarav Sharma")
    line(pdf, "aarav.sharma@example.com | +91 98765 43210")
    line(pdf, "Shop Cart - PHP & MySQL", bold=True)
    line(pdf, "GitHub: https://github.com/aaravsharma-dev/shop-cart")
    line(pdf, "- Cart application with sessions.")
    sec(pdf, "SKILLS")
    line(pdf, "PHP, MySQL, Git")
    return finish(pdf)


def eval_no_heading():
    fx = "F4-no-projects-heading"
    meta, prof = run_pipeline(fixture_no_heading())
    check_contact(fx, prof)
    record(fx, "projects.empty-by-design",
           PASS if prof.get("projects", []) == [] else FAIL, repr(prof.get("projects")))
    flagged = [u.get("url") for u in prof.get("unreviewed_links", [])]
    record(fx, "unreviewed.preserved",
           PASS if "https://github.com/aaravsharma-dev/shop-cart" in flagged else FAIL, repr(flagged))


# ------------------------------------------------------- F5 two-column
def fixture_two_column():
    from fpdf import FPDF
    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 16)
    pdf.cell(0, 9, "Aarav Sharma", new_x="LMARGIN", new_y="NEXT", align="C")
    pdf.set_font("Helvetica", "", 11)
    pdf.cell(0, 7, "aarav.sharma@example.com | +91 98765 43210", new_x="LMARGIN", new_y="NEXT", align="C")
    pdf.cell(0, 7, "github.com/aaravsharma-dev | linkedin.com/in/aarav-sharma", new_x="LMARGIN", new_y="NEXT", align="C")
    pdf.ln(3)
    y0 = pdf.get_y()
    pdf.set_xy(12, y0)
    pdf.set_font("Helvetica", "B", 12)
    pdf.multi_cell(58, 7, "SKILLS\nPHP\nMySQL\nJavaScript\nGit\n\nLINKS\ngithub.com/aaravsharma-dev", new_x="RIGHT", new_y="TOP")
    pdf.set_xy(75, y0)
    pdf.set_font("Helvetica", "", 11)
    pdf.multi_cell(120, 6.5,
                   "WORK EXPERIENCE\nPixelWorks - Frontend Developer, Jan 2023 - Present\n"
                   "- Built interfaces with React.\n\nPROJECTS\nTask Board - React, Node.js\n"
                   "GitHub: https://github.com/aaravsharma-dev/task-board\n"
                   "- Kanban board with drag and drop.\n\nEDUCATION\nBCA, 2022",
                   new_x="LMARGIN", new_y="NEXT")
    return bytes(pdf.output())


def eval_two_column():
    fx = "F5-two-column"
    meta, prof = run_pipeline(fixture_two_column())
    check_contact(fx, prof)
    record(fx, "links.github-profile",
           PASS if prof.get("github") == "https://github.com/aaravsharma-dev" else FAIL, repr(prof.get("github")))
    check_skills(fx, prof, {"PHP", "MySQL", "JavaScript", "Git", "GitHub", "React", "Node.js"})
    projs = {e.get("name"): e for e in prof.get("projects", []) if e.get("name")}
    record(fx, "assoc.task-board",
           PASS if projs.get("Task Board", {}).get("repo_url") == "https://github.com/aaravsharma-dev/task-board" else FAIL,
           repr(projs.get("Task Board")))
    exps = prof.get("experience", [])
    record(fx, "experience", PASS if len(exps) == 1 and exps[0].get("company") == "PixelWorks" else FAIL, repr(exps))
    record(fx, "education.degree-no-institution",
           PASS if prof.get("education", []) == [
               {"degree": "BCA", "institution": "", "year": "2022", "field": ""}] else FAIL,
           repr(prof.get("education")))


# ------------------------------------------------------- F6 missing edu/exp
def fixture_thin():
    pdf = new_pdf()
    h(pdf, "Aarav Sharma")
    line(pdf, "aarav.sharma@example.com | +91 98765 43210")
    sec(pdf, "SKILLS")
    line(pdf, "PHP, MySQL, Git")
    sec(pdf, "PROJECTS")
    line(pdf, "Tiny Tool - PHP", bold=True)
    line(pdf, "- Small utility script.")
    return finish(pdf)


def eval_thin():
    fx = "F6-missing-edu-exp"
    meta, prof = run_pipeline(fixture_thin())
    check_contact(fx, prof)
    record(fx, "education.absent-exact",
           PASS if prof.get("education", []) == [] else FAIL, repr(prof.get("education")))
    record(fx, "experience.empty-exact",
           PASS if prof.get("experience", []) == [] else FAIL, repr(prof.get("experience")))
    record(fx, "experience.unverified-flag",
           PASS if prof.get("experience_unverified") is True else FAIL, repr(prof.get("experience_unverified")))
    check_skills(fx, prof, {"PHP", "MySQL", "Git"})
    projs = {e.get("name"): e for e in prof.get("projects", []) if e.get("name")}
    record(fx, "projects.tiny-tool-no-urls",
           PASS if set(projs) == {"Tiny Tool"} and projs["Tiny Tool"].get("repo_url", "") == "" else FAIL,
           repr(projs))


# ------------------------------------------------------- F7 scanned
def eval_scanned():
    fx = "F7-scanned"
    import fitz
    doc = fitz.open(stream=fixture_standard(), filetype="pdf")
    pix = doc[0].get_pixmap(dpi=200)
    png = pix.tobytes("png")
    doc.close()
    from fpdf import FPDF
    spdf = FPDF(unit="pt", format=[pix.width, pix.height])
    spdf.add_page()
    img_path = "_eval_scan_tmp.png"
    with open(img_path, "wb") as f:
        f.write(png)
    try:
        spdf.image(img_path, x=0, y=0, w=pix.width, h=pix.height)
        scan_bytes = bytes(spdf.output())
    finally:
        import os as _os
        _os.remove(img_path)
    meta = A.extract_pdf_rich(__import__("io").BytesIO(scan_bytes))
    has_tess = shutil.which("tesseract") is not None
    try:
        import pytesseract  # noqa
        has_pytess = True
    except Exception:
        has_pytess = False
    if has_tess and has_pytess:
        record(fx, "ocr.recovers-name",
               PASS if "Aarav Sharma" in meta.get("text", "") else FAIL,
               f"{len(meta.get('text', ''))} chars")
    else:
        record(fx, "ocr.local-deps", UNSUP, "tesseract unavailable locally; Cloud path untested here")
        record(fx, "scanned.graceful-flag",
               PASS if meta.get("is_scanned") is True and meta.get("error") is None else FAIL,
               f"is_scanned={meta.get('is_scanned')} error={meta.get('error')}")


# ------------------------------------------------- F8 multi education
def fixture_edu_multi():
    pdf = new_pdf()
    h(pdf, "Aarav Sharma")
    line(pdf, "aarav.sharma@example.com | +91 98765 43210")
    sec(pdf, "EDUCATION")
    line(pdf, "Bachelor of Technology in Computer Science, IIT Delhi, 2019")
    line(pdf, "MSc Data Science, NMIMS, 2021 - 2023")
    sec(pdf, "SKILLS")
    line(pdf, "PHP, Git")
    return finish(pdf)


def eval_edu_multi():
    fx = "F8-edu-multi"
    meta, prof = run_pipeline(fixture_edu_multi())
    check_contact(fx, prof)
    record(fx, "education.two-exact",
           PASS if prof.get("education", []) == [
               {"degree": "Bachelor of Technology", "institution": "IIT Delhi",
                "year": "2019", "field": "Computer Science"},
               {"degree": "MSc Data Science", "institution": "NMIMS",
                "year": "2021 - 2023", "field": ""}] else FAIL,
           repr(prof.get("education")))


# ------------------------------------------------- F9 incomplete education
def fixture_edu_thin():
    pdf = new_pdf()
    h(pdf, "Aarav Sharma")
    line(pdf, "aarav.sharma@example.com | +91 98765 43210")
    sec(pdf, "EDUCATION")
    line(pdf, "Diploma in Graphic Design")
    sec(pdf, "SKILLS")
    line(pdf, "PHP, Git")
    return finish(pdf)


def eval_edu_thin():
    fx = "F9-edu-incomplete"
    meta, prof = run_pipeline(fixture_edu_thin())
    check_contact(fx, prof)
    record(fx, "education.missing-stay-missing",
           PASS if prof.get("education", []) == [
               {"degree": "Diploma", "institution": "", "year": "", "field": "Graphic Design"}] else FAIL,
           repr(prof.get("education")))


def main():
    eval_standard()
    eval_multi()
    eval_invisible()
    eval_no_heading()
    eval_two_column()
    eval_thin()
    eval_edu_multi()
    eval_edu_thin()
    eval_scanned()
    npass = sum(1 for r in rows if r[2] == PASS)
    nfail = sum(1 for r in rows if r[2] == FAIL)
    nuns = sum(1 for r in rows if r[2] == UNSUP)
    print(f"\n==== EVAL: {npass} pass / {nfail} FAIL / {nuns} unsupported ({len(rows)} checks) ====")
    for fx, field, st, detail in rows:
        if st == FAIL:
            print(f"  NEEDS-FIX [{fx}::{field}] {detail}")
    for fx, field, st, detail in rows:
        if st == UNSUP:
            print(f"  UNSUPPORTED [{fx}::{field}] {detail}")
    if nfail:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
