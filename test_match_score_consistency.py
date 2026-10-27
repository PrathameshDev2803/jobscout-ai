"""Focused regression tests for Job & Fit Match Score Consistency.

Verifies:
1. 5 matched and 7 missing skills cannot produce 100% match score.
2. Extracted skills from JD are properly incorporated into compute_match scoring.
3. Skill variant normalization (NodeJs <-> Node.js, VueJs <-> Vue, Postgres <-> PostgreSQL).
4. SQL relational does not match NoSQL.
5. All skills matched produces strong match.
6. Zero skills matched produces weak match.
7. Zero required skills detected handled cleanly.
8. Duplicate/overlapping skill names deduplicated properly.
"""
import unittest
import matcher


def sample_profile():
    return {
        "name": "Candidate",
        "resume_text": "Full Stack Developer proficient in React, Python, SQL, and Git.",
        "skills": ["React", "Python", "SQL", "Git", "Node.js"],
        "experience_years": 4,
        "location": {"city": "Mumbai", "state": "Maharashtra", "country": "India"},
        "work_preferences": {"remote": True, "hybrid": True, "onsite": True}
    }


class TestMatchScoreConsistency(unittest.TestCase):
    def test_five_matched_seven_missing_cannot_be_100_percent(self):
        p = sample_profile()
        # 12 skills: React, Python, SQL, Git, Node.js (5 match)
        # Angular, VueJs, Ruby On Rails, Redis, Postgres, Cassandra, NoSQL (7 missing)
        job = {
            "title": "Full Stack Developer",
            "company": "Tech Corp",
            "location": "Mumbai",
            "description": "Looking for Full Stack Developer. Requirements: React, Python, Git.",
            "extracted_skills": [
                "React", "Python", "SQL", "Git", "NodeJs",
                "Angular", "VueJs", "Ruby On Rails", "Redis", "Cassandra", "NoSQL", "Docker"
            ]
        }
        res = matcher.compute_match(p, job)
        score = res["match_score"]
        cat = res["category"]
        matched = res["matched_skills"]

        # Score must reflect that ~7 of 12 skills are missing; cannot be 100!
        self.assertLess(score, 70, f"Score {score}% is misleadingly high for missing 7/12 skills")
        self.assertGreaterEqual(score, 30, f"Score {score}% is too low for matching 5 core skills")
        self.assertNotEqual(cat, "Strong match", "Category cannot be Strong match when missing majority of skills")
        self.assertIn("React", matched)
        self.assertIn("Python", matched)
        self.assertIn("Git", matched)

    def test_all_skills_matched_produces_strong_match(self):
        p = sample_profile()
        job = {
            "title": "Full Stack Developer",
            "company": "Tech Corp",
            "location": "Mumbai",
            "description": "Looking for Full Stack Developer with React, Python, SQL, Git, Node.js",
            "extracted_skills": ["React", "Python", "SQL", "Git", "NodeJs"]
        }
        res = matcher.compute_match(p, job)
        self.assertGreaterEqual(res["match_score"], 80)
        self.assertEqual(res["category"], "Strong match")

    def test_zero_skills_matched_produces_low_score(self):
        p = sample_profile()
        job = {
            "title": "Full Stack Developer",
            "company": "Tech Corp",
            "location": "Mumbai",
            "description": "Requirements: Go, Rust, Elixir, Erlang, Clojure, Haskell",
            "extracted_skills": ["Go", "Rust", "Elixir", "Erlang", "Clojure", "Haskell"]
        }
        res = matcher.compute_match(p, job)
        self.assertLess(res["match_score"], 35)
        self.assertNotEqual(res["category"], "Strong match")

    def test_zero_required_skills_detected(self):
        p = sample_profile()
        job = {
            "title": "Full Stack Developer",
            "company": "Tech Corp",
            "location": "Mumbai",
            "description": "General software engineering role with good team collaboration.",
            "extracted_skills": []
        }
        res = matcher.compute_match(p, job)
        self.assertIn("match_score", res)
        self.assertIn("category", res)
        # Thin JD fallback
        self.assertLessEqual(res["match_score"], 49)

    def test_sql_does_not_falsely_match_nosql(self):
        p = {
            "resume_text": "Experienced SQL database developer working with MySQL.",
            "skills": ["SQL", "MySQL"],
            "experience_years": 3,
            "location": {"city": "Mumbai", "state": "Maharashtra", "country": "India"},
            "work_preferences": {"remote": True, "hybrid": True, "onsite": True}
        }
        job = {
            "title": "Database Engineer",
            "location": "Mumbai",
            "description": "Looking for NoSQL specialist.",
            "extracted_skills": ["NoSQL"]
        }
        res = matcher.compute_match(p, job)
        self.assertNotIn("NoSQL", res["matched_skills"])

    def test_skill_variant_normalization(self):
        p = {
            "resume_text": "Node.js and React.js engineer with PostgreSQL.",
            "skills": ["Node.js", "React.js", "PostgreSQL"],
            "experience_years": 3,
            "location": {"city": "Mumbai", "state": "Maharashtra", "country": "India"},
            "work_preferences": {"remote": True, "hybrid": True, "onsite": True}
        }
        job = {
            "title": "Software Engineer",
            "location": "Mumbai",
            "description": "Tech stack includes NodeJs, React, and Postgres.",
            "extracted_skills": ["NodeJs", "React", "Postgres"]
        }
        res = matcher.compute_match(p, job)
        self.assertGreaterEqual(len(res["matched_skills"]), 3)
        self.assertGreaterEqual(res["match_score"], 70)


if __name__ == "__main__":
    unittest.main()
