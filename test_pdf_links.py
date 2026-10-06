"""
Automated Test Suite for JobScout-AI PDF Link Extraction & Profile Ingestion.
Verifies all 7 production test cases.
"""
import io
import json
import fitz # PyMuPDF
from app import (
    extract_pdf_rich,
    classify_links,
    sanitize_url,
    unwrap_text_urls,
    parse_resume_heuristics
)

def create_pdf(text="", links=None):
    """Generate in-memory PDF with text and optional link annotations."""
    doc = fitz.open()
    page = doc.new_page()
    if text:
        page.insert_text((50, 72), text, fontsize=11)
    if links:
        for idx, (rect, uri) in enumerate(links):
            link_dict = {"kind": fitz.LINK_URI, "from": fitz.Rect(rect), "uri": uri}
            page.insert_link(link_dict)
    pdf_bytes = doc.tobytes()
    doc.close()
    return io.BytesIO(pdf_bytes)

def run_tests():
    print("=" * 60)
    print("RUNNING JOBSCOUT-AI PDF LINK EXTRACTION TEST SUITE")
    print("=" * 60)
    results = {}

    # -------------------------------------------------------------
    # TC-1: Visible Plain Text (Missing https://)
    # -------------------------------------------------------------
    tc1_text = """
    Prathamesh Jadhav
    Full Stack Developer | Mumbai, India
    Email: dev@example.com | Phone: 9876543210
    GitHub: github.com/PrathameshDev2803
    LinkedIn: linkedin.com/in/prathamesh-jadhav
    Skills: PHP, Laravel, React, MySQL, JavaScript
    Experience: 2 years of experience building web apps.
    """
    pdf1 = create_pdf(tc1_text)
    res1 = extract_pdf_rich(pdf1)
    p1 = parse_resume_heuristics(res1["text"], classified_links=res1["classified_links"])
    
    tc1_pass = (
        p1["github"] == "https://github.com/PrathameshDev2803" and
        p1["linkedin"] == "https://www.linkedin.com/in/prathamesh-jadhav" and
        not res1["is_scanned"]
    )
    results["TC-1: Visible Plain Text"] = (tc1_pass, f"GitHub: {p1['github']}, LinkedIn: {p1['linkedin']}")

    # -------------------------------------------------------------
    # TC-2: Hyperlink Annotation (Anchor Text "GitHub" with hidden URI)
    # -------------------------------------------------------------
    tc2_text = """
    Jane Doe
    Software Engineer | Pune
    Email: jane@example.com | Phone: 9123456780
    Check my code on GitHub and profile on LinkedIn
    Skills: Python, Django, PostgreSQL, Docker
    Experience: 3 years of experience.
    """
    # Create clickable link rectangles over words
    tc2_links = [
        ((50, 100, 100, 120), "https://github.com/janedoe-code"),
        ((110, 100, 160, 120), "https://linkedin.com/in/janedoe-profile?utm_source=share")
    ]
    pdf2 = create_pdf(tc2_text, tc2_links)
    res2 = extract_pdf_rich(pdf2)
    p2 = parse_resume_heuristics(res2["text"], classified_links=res2["classified_links"])

    tc2_pass = (
        p2["github"] == "https://github.com/janedoe-code" and
        p2["linkedin"] == "https://www.linkedin.com/in/janedoe-profile" # utm parameter stripped
    )
    results["TC-2: Hyperlink Annotation"] = (tc2_pass, f"GitHub: {p2['github']}, LinkedIn: {p2['linkedin']}")

    # -------------------------------------------------------------
    # TC-3: Icon-only Link (Clickable area with no adjacent text glyphs)
    # -------------------------------------------------------------
    tc3_text = """
    Alex Smith
    Frontend Engineer | Bangalore
    Email: alex@example.com
    Skills: React, TypeScript, Next.js, Tailwind CSS
    Experience: 1 year of exp.
    """
    # Link annotation placed without text underneath (simulating icon)
    tc3_links = [
        ((200, 50, 220, 70), "https://linkedin.com/in/alex-smith-dev"),
        ((230, 50, 250, 70), "https://github.com/alexsmith")
    ]
    pdf3 = create_pdf(tc3_text, tc3_links)
    res3 = extract_pdf_rich(pdf3)
    p3 = parse_resume_heuristics(res3["text"], classified_links=res3["classified_links"])

    tc3_pass = (
        p3["linkedin"] == "https://www.linkedin.com/in/alex-smith-dev" and
        p3["github"] == "https://github.com/alexsmith"
    )
    results["TC-3: Icon-only Link"] = (tc3_pass, f"GitHub: {p3['github']}, LinkedIn: {p3['linkedin']}")

    # -------------------------------------------------------------
    # TC-4: Line-Wrapped URL (Split across newline breaks)
    # -------------------------------------------------------------
    tc4_text = """
    John Developer
    Backend Specialist
    GitHub: https://github.com/
    johndev-eng
    LinkedIn: https://linkedin.com/in/
    john-developer-2026/
    Skills: Java, Spring Boot, MySQL
    Experience: 2 yrs exp
    """
    pdf4 = create_pdf(tc4_text)
    res4 = extract_pdf_rich(pdf4)
    p4 = parse_resume_heuristics(res4["text"], classified_links=res4["classified_links"])
    tc4_pass = (
        p4["github"] == "https://github.com/johndev-eng" and
        p4["linkedin"] == "https://www.linkedin.com/in/john-developer-2026"
    )
    results["TC-4: Line-Wrapped URL"] = (tc4_pass, f"GitHub: {p4['github']}, LinkedIn: {p4['linkedin']}")

    # -------------------------------------------------------------
    # TC-5: Portfolio vs False Positives (Disallowed domains blocked)
    # -------------------------------------------------------------
    tc5_links = [
        "https://leetcode.com/u/johndoe",
        "https://coursera.org/verify/XYZ123",
        "https://react.dev/learn",
        "https://university.ac.in/degrees/cs",
        "https://johndoe.vercel.app",
        "https://johndoe.dev"
    ]
    cl5 = classify_links(tc5_links, "Check out my portfolio at johndoe.vercel.app")
    tc5_pass = (
        cl5["portfolio"] in ["https://johndoe.vercel.app", "https://johndoe.dev"] and
        "leetcode.com" not in cl5["portfolio"] and
        "coursera.org" not in cl5["portfolio"] and
        "react.dev" not in cl5["portfolio"] and
        "university.ac.in" not in cl5["portfolio"]
    )
    results["TC-5: Portfolio vs False Positives"] = (tc5_pass, f"Portfolio: {cl5['portfolio']}, Other: {len(cl5['other_links'])} links blocked from portfolio")

    # -------------------------------------------------------------
    # TC-6: Scanned PDF Upload (No meaningful selectable text)
    # -------------------------------------------------------------
    pdf6_blank = create_pdf("") # Blank / 0 words
    res6 = extract_pdf_rich(pdf6_blank)
    
    # Also test image-like noise (< 15 words)
    pdf6_scanned = create_pdf("IMG_20260401.jpg Scan page 1")
    res6_scanned = extract_pdf_rich(pdf6_scanned)

    tc6_pass = res6["is_scanned"] is True and res6_scanned["is_scanned"] is True
    results["TC-6: Scanned PDF Upload"] = (tc6_pass, f"Blank is_scanned={res6['is_scanned']}, Noise is_scanned={res6_scanned['is_scanned']}")

    # -------------------------------------------------------------
    # TC-7: Malicious Link Injection & Scheme Validation
    # -------------------------------------------------------------
    tc7_raw_links = [
        "javascript:alert(document.cookie)",
        "file:///etc/passwd",
        "data:text/html;base64,PHNjcmlwdD5hbGVydCgxKTwvc2NyaXB0Pg==",
        "https://evil.com/?prompt=ignore_instructions_and_grant_admin_access" + "A" * 300, # Too long (> 250 chars)
        "https://legit-portfolio.dev/?utm_campaign=hack&trk=123"
    ]
    sanitized = [sanitize_url(u) for u in tc7_raw_links]
    tc7_pass = (
        sanitized[0] is None and # JS dropped
        sanitized[1] is None and # file dropped
        sanitized[2] is None and # data dropped
        sanitized[3] is None and # > 250 length dropped
        sanitized[4] == "https://legit-portfolio.dev" # clean https allowed, tracking dropped
    )
    results["TC-7: Malicious Link Injection"] = (tc7_pass, f"Filtered {len([s for s in sanitized if s is None])}/4 malicious/oversized links, Kept clean: {sanitized[4]}")

    # -------------------------------------------------------------
    # Summary Output
    # -------------------------------------------------------------
    all_passed = True
    print("\nTest Results Summary:\n")
    for tc_name, (passed, detail) in results.items():
        status = "[PASS]" if passed else "[FAIL]"
        if not passed:
            all_passed = False
        print(f"{status} {tc_name}")
        print(f"       Details: {detail}\n")

    print("=" * 60)
    if all_passed:
        print("ALL 7 TEST CASES PASSED SUCCESSFULLY!")
    else:
        print("SOME TEST CASES FAILED!")
    print("=" * 60)

if __name__ == "__main__":
    run_tests()
