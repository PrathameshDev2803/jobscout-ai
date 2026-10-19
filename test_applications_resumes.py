"""Focused tests for tracker + resume-library DB operations.

Covers: backward-compatible migrations, application create/update/remove,
days-since math, status validation, resume save/dedupe/delete isolation.

Run: python test_applications_resumes.py (no network, temp DB + temp dir).
"""
import os
import sqlite3
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import fetch
from fetch import (APP_STATUSES, days_since, delete_generated_resume,
                   get_applications, list_generated_resumes,
                   remove_application, save_generated_resume,
                   set_application_status, shortlist_job, upsert_application)


class _TmpDB(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dbp = os.path.join(self.tmp.name, "t.db")
        self.rdir = os.path.join(self.tmp.name, "resumes")
        con = sqlite3.connect(self.dbp)
        con.execute("""CREATE TABLE jobs(
          url_hash TEXT PRIMARY KEY, title TEXT, company TEXT, location TEXT,
          description TEXT, url TEXT, source TEXT, posted_at TEXT, created_at TEXT,
          applied INTEGER DEFAULT 0)""")
        con.execute("INSERT INTO jobs (url_hash,title,company,created_at,applied)"
                    " VALUES ('legacy1','Dev','Acme','2024-01-01T00:00:00',0)")
        con.commit()
        con.close()

    def tearDown(self):
        self.tmp.cleanup()


class TestMigrations(_TmpDB):
    def test_additive_migration_preserves_data(self):
        h = upsert_application("Beta", "QA Eng", url="https://x.test/j/1",
                               db_path=self.dbp)
        con = sqlite3.connect(self.dbp)
        cols = [r[1] for r in con.execute("PRAGMA table_info(jobs)")]
        con.close()
        for c in ("app_status", "app_notes", "applied_date", "resume_id",
                  "shortlisted", "closed", "alert_sent"):
            self.assertIn(c, cols)
        # legacy row untouched
        con = sqlite3.connect(self.dbp)
        row = con.execute("SELECT title, applied FROM jobs WHERE url_hash='legacy1'").fetchone()
        con.close()
        self.assertEqual(row, ("Dev", 0))
        self.assertTrue(h)


class TestApplications(_TmpDB):
    def test_create_and_list(self):
        h = upsert_application("Acme", "Backend Dev", url="https://x.test/j/2",
                               applied_date="2026-10-01", db_path=self.dbp)
        apps = get_applications(self.dbp)
        self.assertEqual(len(apps), 1)
        self.assertEqual(apps[0]["url_hash"], h)
        self.assertEqual(apps[0]["app_status"], "Applied")
        self.assertEqual(apps[0]["applied_date"], "2026-10-01")

    def test_manual_create_without_url(self):
        h = upsert_application("NoURL Inc", "Dev", applied_date="2026-10-10",
                               db_path=self.dbp)
        self.assertTrue(h)
        self.assertEqual(len(get_applications(self.dbp)), 1)

    def test_status_change_preserves_date(self):
        h = upsert_application("Acme", "Dev", url="https://x.test/j/3",
                               applied_date="2026-09-01", db_path=self.dbp)
        set_application_status(h, "Interview", db_path=self.dbp)
        apps = get_applications(self.dbp)
        self.assertEqual(apps[0]["app_status"], "Interview")
        self.assertEqual(apps[0]["applied_date"], "2026-09-01")

    def test_reapply_preserves_original_date(self):
        h = upsert_application("Acme", "Dev", url="https://x.test/j/4",
                               applied_date="2026-08-01", db_path=self.dbp)
        upsert_application("Acme", "Dev", url="https://x.test/j/4",
                           db_path=self.dbp)
        apps = get_applications(self.dbp)
        self.assertEqual(apps[0]["applied_date"], "2026-08-01")

    def test_invalid_status_rejected(self):
        with self.assertRaises(ValueError):
            upsert_application("A", "B", status="Hired", db_path=self.dbp)
        with self.assertRaises(ValueError):
            set_application_status("x", "Hired", db_path=self.dbp)

    def test_empty_company_rejected(self):
        with self.assertRaises(ValueError):
            upsert_application("", "Dev", db_path=self.dbp)

    def test_remove_keeps_row_and_resume(self):
        rid = save_generated_resume(b"%PDF-fake", "Dev", "Acme", 80,
                                    db_path=self.dbp, resume_dir=self.rdir)
        h = upsert_application("Acme", "Dev", url="https://x.test/j/5",
                               resume_id=rid, db_path=self.dbp)
        remove_application(h, db_path=self.dbp)
        self.assertEqual(get_applications(self.dbp), [])
        con = sqlite3.connect(self.dbp)
        row = con.execute("SELECT applied, resume_id FROM jobs WHERE url_hash=?",
                          (h,)).fetchone()
        lib = con.execute("SELECT COUNT(*) FROM generated_resumes").fetchone()[0]
        con.close()
        self.assertEqual(row[0], 0)
        self.assertEqual(lib, 1)  # resume survives application removal

    def test_shortlist_without_applied(self):
        h = shortlist_job("Acme", "Dev", url="https://x.test/j/6",
                          db_path=self.dbp)
        apps = get_applications(self.dbp)
        self.assertEqual(len(apps), 1)
        self.assertEqual(apps[0]["applied"], 0)
        self.assertEqual(apps[0]["shortlisted"], 1)

    def test_days_since(self):
        self.assertEqual(days_since("2026-10-10", today_iso="2026-10-15"), 5)
        self.assertEqual(days_since("2026-10-15", today_iso="2026-10-15"), 0)
        self.assertIsNone(days_since(""))
        self.assertIsNone(days_since("not-a-date"))
        self.assertIn("Interview", APP_STATUSES)
        self.assertIn("Withdrawn", APP_STATUSES)


class TestResumeLibrary(_TmpDB):
    def test_save_and_list_newest_first(self):
        a = save_generated_resume(b"%PDF-one", "Dev", "Acme", 70,
                                  db_path=self.dbp, resume_dir=self.rdir)
        b = save_generated_resume(b"%PDF-two", "QA", "Beta", 60,
                                  db_path=self.dbp, resume_dir=self.rdir)
        lib = list_generated_resumes(self.dbp)
        self.assertEqual([r["id"] for r in lib], [b, a])
        self.assertTrue(os.path.exists(lib[0]["file_path"]))
        self.assertTrue(lib[0]["filename"].endswith(".pdf"))

    def test_dedupe_identical_bytes(self):
        a = save_generated_resume(b"%PDF-same", "Dev", "Acme", 70,
                                  db_path=self.dbp, resume_dir=self.rdir)
        b = save_generated_resume(b"%PDF-same", "Dev", "Acme", 70,
                                  db_path=self.dbp, resume_dir=self.rdir)
        self.assertEqual(a, b)
        self.assertEqual(len(list_generated_resumes(self.dbp)), 1)

    def test_empty_bytes_rejected(self):
        with self.assertRaises(ValueError):
            save_generated_resume(b"", "Dev", "Acme", db_path=self.dbp,
                                  resume_dir=self.rdir)
        with self.assertRaises(ValueError):
            save_generated_resume(None, "Dev", "Acme", db_path=self.dbp,
                                  resume_dir=self.rdir)
        self.assertEqual(list_generated_resumes(self.dbp), [])

    def test_unique_filenames(self):
        save_generated_resume(b"%PDF-a", "Dev", "Acme", db_path=self.dbp,
                              resume_dir=self.rdir)
        save_generated_resume(b"%PDF-b", "Dev", "Acme", db_path=self.dbp,
                              resume_dir=self.rdir)
        names = [r["filename"] for r in list_generated_resumes(self.dbp)]
        self.assertEqual(len(set(names)), 2)

    def test_delete_removes_file_and_row_only(self):
        rid = save_generated_resume(b"%PDF-del", "Dev", "Acme",
                                    db_path=self.dbp, resume_dir=self.rdir)
        path = list_generated_resumes(self.dbp)[0]["file_path"]
        h = upsert_application("Acme", "Dev", url="https://x.test/j/7",
                               resume_id=rid, db_path=self.dbp)
        self.assertTrue(delete_generated_resume(rid, db_path=self.dbp))
        self.assertFalse(os.path.exists(path))
        self.assertEqual(list_generated_resumes(self.dbp), [])
        con = sqlite3.connect(self.dbp)
        job = con.execute("SELECT url_hash FROM jobs WHERE url_hash=?",
                          (h,)).fetchone()
        con.close()
        self.assertIsNotNone(job)  # application row survives resume delete

    def test_delete_missing_returns_false(self):
        self.assertFalse(delete_generated_resume(9999, db_path=self.dbp))


if __name__ == "__main__":
    unittest.main(verbosity=1)
