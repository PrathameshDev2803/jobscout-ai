"""Regression tests: heuristic education extraction.

Rules under test: section-gated, degree/institution/year/field capture, missing
fields stay empty (never invented), no-education-section yields [], merge
preservation via merge_profiles education rules.
"""
import copy
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import app as A


def edu(text):
    return A.extract_education_entries(text)


class TestEducationExtraction(unittest.TestCase):
    def test_single_line_degree(self):
        out = edu("EDUCATION\nBachelor of Computer Applications (BCA), Chandrabhan Sharma College, 2024\n\nSKILLS\nPHP")
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["degree"], "Bachelor of Computer Applications (BCA)")
        self.assertEqual(out[0]["institution"], "Chandrabhan Sharma College")
        self.assertEqual(out[0]["year"], "2024")

    def test_range_and_pursuing(self):
        out = edu("EDUCATION\nMSc Data Science & AI, Chandrabhan Sharma College, 2026 - 2028 | Currently pursuing")
        self.assertEqual(out[0]["degree"], "MSc Data Science & AI")
        self.assertEqual(out[0]["year"], "2026 - 2028")
        self.assertEqual(out[0]["institution"], "Chandrabhan Sharma College")

    def test_dash_separated_abbreviation(self):
        out = edu("EDUCATION\nBCA - SNDT College - 2022")
        self.assertEqual(out[0], {"degree": "BCA", "institution": "SNDT College",
                                  "year": "2022", "field": ""})

    def test_two_line_form(self):
        out = edu("EDUCATION\nMaster of Computer Applications\nPune University, 2021\n\nSKILLS\nX")
        self.assertEqual(out[0]["degree"], "Master of Computer Applications")
        self.assertEqual(out[0]["institution"], "Pune University")
        self.assertEqual(out[0]["year"], "2021")

    def test_incomplete_entry_no_invention(self):
        out = edu("EDUCATION\nDiploma in Graphic Design")
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["degree"], "Diploma")
        self.assertEqual(out[0]["field"], "Graphic Design")
        self.assertEqual(out[0]["institution"], "")
        self.assertEqual(out[0]["year"], "")

    def test_in_field_split(self):
        out = edu("EDUCATION\nBachelor of Technology in Computer Science, IIT Delhi, 2019")
        self.assertEqual(out[0]["degree"], "Bachelor of Technology")
        self.assertEqual(out[0]["field"], "Computer Science")
        self.assertEqual(out[0]["institution"], "IIT Delhi")

    def test_location_not_institution(self):
        out = edu("EDUCATION\nBCA, Mumbai, 2022")
        self.assertEqual(out[0]["degree"], "BCA")
        self.assertEqual(out[0]["institution"], "")
        self.assertEqual(out[0]["year"], "2022")

    def test_multiple_qualifications(self):
        out = edu("EDUCATION\nBCA, SNDT College, 2022\nMSc Data Science, NMIMS, 2024\n\nSKILLS\nX")
        self.assertEqual(len(out), 2)
        self.assertEqual(out[1]["degree"], "MSc Data Science")
        self.assertEqual(out[1]["institution"], "NMIMS")

    def test_no_section_no_entries(self):
        self.assertEqual(edu("SKILLS\nPHP, MySQL\nWORK EXPERIENCE\nAcme - Dev, 2020 - 2021"), [])
        self.assertEqual(edu(""), [])
        # degree-like prose outside a section must not fabricate rows
        self.assertEqual(edu("SUMMARY\nI hold a bachelor of patience and 5 years of trying."), [])

    def test_no_invention_garbage(self):
        out = edu("EDUCATION\nLooking for opportunities in tech.")
        self.assertEqual(out, [])

    def test_trailing_period_stripped_from_institution(self):
        out = edu("EDUCATION\nBCA, SNDT College.")
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["institution"], "SNDT College")
        self.assertEqual(out[0]["degree"], "BCA")

    def test_degree_abbreviation_dots_preserved(self):
        out = edu("EDUCATION\nB.Sc., St. Xavier's College, 2020")
        self.assertEqual(out[0]["degree"], "B.Sc.")
        self.assertEqual(out[0]["institution"], "St. Xavier's College")
        out = edu("EDUCATION\nM.Sc. Physics, Mumbai University, 2021")
        self.assertEqual(out[0]["degree"], "M.Sc. Physics")
        out = edu("EDUCATION\nB.Tech., IIT Delhi, 2019")
        self.assertEqual(out[0]["degree"], "B.Tech.")
        self.assertEqual(out[0]["institution"], "IIT Delhi")

    def test_field_trailing_period_stripped(self):
        out = edu("EDUCATION\nDiploma in Graphic Design.")
        self.assertEqual(out[0]["field"], "Graphic Design")
        self.assertEqual(out[0]["degree"], "Diploma")

    def test_parse_wires_education(self):
        text = ("Aarav Sharma\naarav@example.com\n\nEDUCATION\n"
                "BCA, SNDT College, 2022\n\nSKILLS\nPHP")
        p = A.parse_resume_heuristics(text)
        self.assertEqual(len(p.get("education", [])), 1)
        self.assertEqual(p["education"][0]["institution"], "SNDT College")

    def test_merge_preserves_education(self):
        existing = {"education": [{"degree": "BCA", "institution": "SNDT", "year": "2022", "field": ""}]}
        out = A.merge_profiles(copy.deepcopy(existing), {"education": []})
        self.assertEqual(out["education"], existing["education"])
        out2 = A.merge_profiles(copy.deepcopy(existing),
                                {"education": [{"degree": "BCA", "institution": "SNDT College",
                                                "year": "", "field": ""}]})
        self.assertEqual(out2["education"][0]["institution"], "SNDT College")
        self.assertEqual(out2["education"][0]["year"], "2022")  # empty never overwrites
        out3 = A.merge_profiles(copy.deepcopy(existing),
                                {"education": [{"degree": "MSc", "institution": "NMIMS", "year": "2024"}]})
        self.assertEqual(len(out3["education"]), 2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
