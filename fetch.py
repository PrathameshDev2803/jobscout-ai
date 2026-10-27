"""JobTool persistence + single-URL job import.

Aggregation (multi-platform scrapers, dedup pipeline, scheduler) was removed:
this module keeps only the SQLite store used by the tracker and
fetch_job_from_url(), which powers Paste Link (ATS APIs + generic fallback).
"""
import hashlib
import html
import ipaddress
import os
import re
import socket
import sqlite3
from datetime import datetime
from urllib.parse import urljoin, urlparse

import requests
from dotenv import load_dotenv

load_dotenv()
DB = os.path.join(os.path.dirname(__file__), "jobs.db")
RESUME_DIR = os.path.join(os.path.dirname(__file__), "generated_resumes")

# ponytail: tracker statuses are a closed set; keep in one place so the
# Applications UI and any future importer share the same vocabulary.
APP_STATUSES = ["Applied", "Interview", "Assessment", "Offer",
                "Rejected", "Withdrawn"]


def db():
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
    if "applied_date" not in cols:
        con.execute("ALTER TABLE jobs ADD COLUMN applied_date TEXT DEFAULT ''")
    if "resume_id" not in cols:
        con.execute("ALTER TABLE jobs ADD COLUMN resume_id INTEGER DEFAULT NULL")
    con.execute("""CREATE TABLE IF NOT EXISTS generated_resumes(
      id INTEGER PRIMARY KEY AUTOINCREMENT, filename TEXT, job_title TEXT,
      company TEXT, created_at TEXT, match_score INTEGER DEFAULT NULL,
      file_path TEXT, pdf_hash TEXT UNIQUE, application_url TEXT DEFAULT '')""")
    con.commit()
    return con


def save(con, rows):
    now = datetime.utcnow().isoformat()
    n = 0
    for r in rows:
        if not r.get("url"):
            continue
        h = hashlib.sha256(r["url"].encode()).hexdigest()[:32]
        posted = str(r.get("posted_at", "") or "").strip()
        if posted.lower() in ("nan", "none", "null"):
            posted = ""
        try:
            con.execute("""INSERT OR IGNORE INTO jobs
              (url_hash,title,company,location,description,url,source,posted_at,created_at,alert_sent)
              VALUES(?,?,?,?,?,?,?,?,?,0)""",
              (h, r.get("title","")[:300], r.get("company","")[:200],
               r.get("location","")[:200], r.get("description","")[:8000],
               r["url"], r.get("source",""), posted, now))
            n += con.total_changes
        except Exception:
            pass
    con.commit()
    return n


def _ensure_tracker_cols(con):
    """Additive-only guard so helpers work on legacy jobs tables."""
    cols = [r[1] for r in con.execute("PRAGMA table_info(jobs)")]
    for name, ddl in (
            ("shortlisted", "ALTER TABLE jobs ADD COLUMN shortlisted INTEGER DEFAULT 0"),
            ("closed", "ALTER TABLE jobs ADD COLUMN closed INTEGER DEFAULT 0"),
            ("alert_sent", "ALTER TABLE jobs ADD COLUMN alert_sent INTEGER DEFAULT 1"),
            ("app_status", "ALTER TABLE jobs ADD COLUMN app_status TEXT DEFAULT 'Applied'"),
            ("app_notes", "ALTER TABLE jobs ADD COLUMN app_notes TEXT DEFAULT ''"),
            ("applied_date", "ALTER TABLE jobs ADD COLUMN applied_date TEXT DEFAULT ''"),
            ("resume_id", "ALTER TABLE jobs ADD COLUMN resume_id INTEGER DEFAULT NULL")):
        if name not in cols:
            con.execute(ddl)
    con.commit()


def _today_iso():
    return datetime.utcnow().date().isoformat()


def _synthetic_hash(company, title, stamp):
    raw = "|".join([(company or "").strip().lower(),
                    (title or "").strip().lower(), (stamp or "").strip()])
    return hashlib.sha256(raw.encode()).hexdigest()[:32]


def days_since(date_iso, today_iso=None):
    """Full days between date_iso and today. None when unparseable."""
    if not date_iso or not isinstance(date_iso, str):
        return None
    try:
        day = datetime.fromisoformat(date_iso.strip()[:10]).date()
        ref = (datetime.fromisoformat((today_iso or _today_iso())[:10]).date()
               if today_iso else datetime.utcnow().date())
        return max(0, (ref - day).days)
    except Exception:
        return None


def upsert_application(company, title, url="", status="Applied",
                       applied_date=None, notes="", resume_id=None,
                       source="manual", preserve_date=True, db_path=DB):
    """Create or update a tracker entry. Returns url_hash.

    Never auto-marks: call only from explicit user actions.
    With preserve_date, an existing applied_date is never overwritten.
    """
    if status not in APP_STATUSES:
        raise ValueError("Unknown status: %r" % (status,))
    if not (company or "").strip() or not (title or "").strip():
        raise ValueError("Company and title are required.")
    url = (url or "").strip()
    h = (hashlib.sha256(url.encode()).hexdigest()[:32] if url
         else _synthetic_hash(company, title, applied_date or _today_iso()))
    now = datetime.utcnow().isoformat()
    con = sqlite3.connect(db_path, timeout=30.0)
    try:
        _ensure_tracker_cols(con)
        row = con.execute("SELECT applied_date, resume_id FROM jobs WHERE url_hash=?",
                          (h,)).fetchone()
        if row is None:
            con.execute("""INSERT INTO jobs
              (url_hash,title,company,location,description,url,source,posted_at,
               created_at,applied,app_status,app_notes,applied_date,resume_id)
              VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
              (h, title.strip()[:300], company.strip()[:200], "", "",
               url, source, "", now, 1, status, notes.strip(),
               (applied_date or _today_iso()),
               resume_id))
        else:
            keep_date = (row[0] or "") if preserve_date and (row[0] or "") else (applied_date or _today_iso())
            keep_resume = resume_id if resume_id is not None else row[1]
            con.execute("""UPDATE jobs SET applied=1, app_status=?, app_notes=?,
              applied_date=?, resume_id=?,
              title=CASE WHEN title='' THEN ? ELSE title END,
              company=CASE WHEN company='' THEN ? ELSE company END,
              url=CASE WHEN url='' THEN ? ELSE url END
              WHERE url_hash=?""",
              (status, notes.strip(), keep_date, keep_resume,
               title.strip()[:300], company.strip()[:200], url, h))
        con.commit()
    finally:
        con.close()
    return h


def shortlist_job(company, title, url="", db_path=DB):
    """Flag a job as shortlisted without marking it applied."""
    url = (url or "").strip()
    h = (hashlib.sha256(url.encode()).hexdigest()[:32] if url
         else _synthetic_hash(company, title, "shortlist"))
    now = datetime.utcnow().isoformat()
    con = sqlite3.connect(db_path, timeout=30.0)
    try:
        _ensure_tracker_cols(con)
        row = con.execute("SELECT url_hash FROM jobs WHERE url_hash=?",
                          (h,)).fetchone()
        if row is None:
            con.execute("""INSERT INTO jobs
              (url_hash,title,company,location,description,url,source,posted_at,
               created_at,applied,shortlisted,app_status)
              VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
              (h, (title or "Role").strip()[:300],
               (company or "Unknown").strip()[:200], "", "", url,
               "manual", "", now, 0, 1, "Applied"))
        else:
            con.execute("UPDATE jobs SET shortlisted=1 WHERE url_hash=?", (h,))
        con.commit()
    finally:
        con.close()
    return h


def set_application_status(url_hash, status, db_path=DB):
    """Status-only update; applied_date is never touched."""
    if status not in APP_STATUSES:
        raise ValueError("Unknown status: %r" % (status,))
    con = sqlite3.connect(db_path, timeout=30.0)
    try:
        _ensure_tracker_cols(con)
        con.execute("UPDATE jobs SET app_status=? WHERE url_hash=?",
                    (status, url_hash))
        con.commit()
        return con.total_changes
    finally:
        con.close()


def remove_application(url_hash, db_path=DB):
    """Untrack only: clears flags, keeps the job row and any linked resume."""
    con = sqlite3.connect(db_path, timeout=30.0)
    try:
        _ensure_tracker_cols(con)
        con.execute("UPDATE jobs SET applied=0, shortlisted=0 WHERE url_hash=?",
                    (url_hash,))
        con.commit()
        return con.total_changes
    finally:
        con.close()


def get_applications(db_path=DB):
    """Tracked rows (applied or shortlisted), newest activity first."""
    con = sqlite3.connect(db_path, timeout=30.0)
    con.row_factory = sqlite3.Row
    try:
        _ensure_tracker_cols(con)
        rows = [dict(r) for r in con.execute(
            """SELECT * FROM jobs WHERE applied=1 OR shortlisted=1
               ORDER BY CASE WHEN applied_date='' THEN created_at ELSE applied_date END DESC,
               created_at DESC""")]
        return rows
    finally:
        con.close()


def _unique_filename(company, title, resume_dir=RESUME_DIR):
    os.makedirs(resume_dir, exist_ok=True)
    slug = lambda s: (re.sub(r"[^a-z0-9]+", "_", (s or "anon").lower()).strip("_") or "anon")[:40]
    stamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    base = "Resume_%s_%s_%s.pdf" % (slug(company), slug(title), stamp)
    path = os.path.join(resume_dir, base)
    i = 2
    while os.path.exists(path):
        path = os.path.join(resume_dir, base[:-4] + "-%d.pdf" % i)
        i += 1
    return path


def save_generated_resume(pdf_bytes, job_title="", company="", match_score=None,
                          application_url="", db_path=DB, resume_dir=RESUME_DIR):
    """Persist a successfully generated PDF. Idempotent on content hash.

    Returns the row id (existing id when identical bytes were saved before).
    Raises on empty bytes so failures never create phantom library entries.
    """
    if not pdf_bytes or not isinstance(pdf_bytes, (bytes, bytearray)):
        raise ValueError("Refusing to library an empty/failed PDF.")
    pdf_hash = hashlib.sha256(bytes(pdf_bytes)).hexdigest()
    con = sqlite3.connect(db_path, timeout=30.0)
    try:
        con.execute("""CREATE TABLE IF NOT EXISTS generated_resumes(
          id INTEGER PRIMARY KEY AUTOINCREMENT, filename TEXT, job_title TEXT,
          company TEXT, created_at TEXT, match_score INTEGER DEFAULT NULL,
          file_path TEXT, pdf_hash TEXT UNIQUE, application_url TEXT DEFAULT '')""")
        dup = con.execute("SELECT id FROM generated_resumes WHERE pdf_hash=?",
                          (pdf_hash,)).fetchone()
        if dup:
            return dup[0]
        path = _unique_filename(company, job_title, resume_dir)
        with open(path, "wb") as f:
            f.write(bytes(pdf_bytes))
        cur = con.execute("""INSERT INTO generated_resumes
          (filename,job_title,company,created_at,match_score,file_path,pdf_hash,application_url)
          VALUES(?,?,?,?,?,?,?,?)""",
          (os.path.basename(path), (job_title or "")[:300],
           (company or "")[:200], datetime.utcnow().isoformat(),
           match_score, path, pdf_hash, application_url or ""))
        con.commit()
        return cur.lastrowid
    finally:
        con.close()


def list_generated_resumes(db_path=DB):
    con = sqlite3.connect(db_path, timeout=30.0)
    con.row_factory = sqlite3.Row
    try:
        try:
            rows = [dict(r) for r in con.execute(
                "SELECT * FROM generated_resumes ORDER BY created_at DESC")]
            return rows
        except sqlite3.OperationalError:
            return []
    finally:
        con.close()


def delete_generated_resume(resume_id, db_path=DB):
    """Delete library entry + file. Never touches jobs/applications."""
    con = sqlite3.connect(db_path, timeout=30.0)
    try:
        con.execute("""CREATE TABLE IF NOT EXISTS generated_resumes(
          id INTEGER PRIMARY KEY AUTOINCREMENT, filename TEXT, job_title TEXT,
          company TEXT, created_at TEXT, match_score INTEGER DEFAULT NULL,
          file_path TEXT, pdf_hash TEXT UNIQUE, application_url TEXT DEFAULT '')""")
        row = con.execute("SELECT file_path FROM generated_resumes WHERE id=?",
                          (resume_id,)).fetchone()
        if not row:
            return False
        try:
            if row[0] and os.path.exists(row[0]):
                os.remove(row[0])
        except Exception:
            pass
        con.execute("DELETE FROM generated_resumes WHERE id=?", (resume_id,))
        con.execute("UPDATE jobs SET resume_id=NULL WHERE resume_id=?",
                    (resume_id,))
        con.commit()
        return True
    finally:
        con.close()


_BLOCKED_HOST_SUFFIXES = (".local", ".internal", ".localhost", ".home.arpa")
_MAX_FETCH_BYTES = 2 * 1024 * 1024


def _host_is_public(host):
    host = (host or "").strip().strip("[]").lower().rstrip(".")
    if not host or host == "localhost" or host.endswith(_BLOCKED_HOST_SUFFIXES):
        return False
    try:
        infos = socket.getaddrinfo(host, None)
    except Exception:
        return False
    if not infos:
        return False
    for info in infos:
        try:
            ip = ipaddress.ip_address(info[4][0])
        except ValueError:
            return False
        if (ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_multicast
                or ip.is_reserved or ip.is_unspecified):
            return False
    return True


def _assert_safe_public_url(url):
    """Reject non-HTTP(S), credential-bearing, and private/internal targets (SSRF guard)."""
    if not isinstance(url, str) or not url.strip() or len(url) > 2048:
        raise RuntimeError("Invalid job URL.")
    try:
        parsed = urlparse(url.strip())
    except Exception:
        raise RuntimeError("Invalid job URL.")
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise RuntimeError("Only http/https job links are supported.")
    if parsed.username or parsed.password:
        raise RuntimeError("Job URL must not contain credentials.")
    if not _host_is_public(parsed.hostname):
        raise RuntimeError("This URL points to a private or internal address and is blocked.")
    return url.strip()


def _safe_get(url, headers, timeout=15, max_redirects=3):
    """GET with manual redirect validation, size cap, and content-type check."""
    current = _assert_safe_public_url(url)
    for _ in range(max_redirects + 1):
        resp = requests.get(current, headers=headers, timeout=timeout,
                            allow_redirects=False, stream=True)
        if getattr(resp, "is_redirect", False):
            location = (getattr(resp, "headers", {}) or {}).get("Location", "")
            if hasattr(resp, "close"):
                resp.close()
            if not location:
                raise RuntimeError("Job link redirect is missing a destination.")
            current = _assert_safe_public_url(urljoin(current, location))
            continue
        resp.raise_for_status()
        ctype = ((getattr(resp, "headers", {}) or {}).get("Content-Type") or "").lower()
        if ctype and not any(t in ctype for t in ("text/html", "text/plain",
                                                  "application/xhtml", "application/json")):
            if hasattr(resp, "close"):
                resp.close()
            raise RuntimeError("Job link did not return a readable HTML/text page.")
        if not hasattr(resp, "iter_content"):
            body_text = getattr(resp, "text", "") or ""
            if len(body_text) > _MAX_FETCH_BYTES:
                raise RuntimeError("Job page is too large to import.")
            return resp, body_text
        chunks = []
        total = 0
        for chunk in resp.iter_content(64 * 1024):
            total += len(chunk)
            if total > _MAX_FETCH_BYTES:
                resp.close()
                raise RuntimeError("Job page is too large to import.")
            chunks.append(chunk)
        resp.close()
        body = b"".join(chunks)
        return resp, body.decode(getattr(resp, "encoding", None) or "utf-8", errors="ignore")
    raise RuntimeError("Too many redirects while fetching the job link.")


def fetch_job_from_url(url):
    """Manual Indeed/LinkedIn/Any URL import:
    // ponytail: Indeed blocks plain HTTP with Cloudflare 401/403; GraphQL jobData endpoint
    // returns 100% structured title, company, location & JD text when jobKey (jk or vjk) is present.
    For non-Indeed URLs, falls back to clean HTML extraction.
    """
    url = (url or "").strip()
    if not url:
        return None
    if "://" in url:
        url = _assert_safe_public_url(url)

    is_indeed = bool(re.search(r'indeed\.[a-z.]+', url, re.I))

    # 1. Check if Indeed URL or contains jobKey (jk or vjk)
    jk_match = re.search(r'(?:[?&]|%26|/viewjob\?jk=)(?:vjk|jk)(?:=|%3D)([a-f0-9]+)', url, re.I)
    if not jk_match and re.fullmatch(r'[a-f0-9]{16}', url, re.I):
        jk_match = re.search(r'([a-f0-9]{16})', url)

    if jk_match:
        jk = jk_match.group(1)
        try:
            # ponytail: optional jobspy import — if unavailable, this falls through
            # to the SmartRecruiters/Greenhouse/Lever APIs and generic fallback below.
            from jobspy.indeed.constant import api_headers
            h = api_headers.copy()
            h["indeed-co"] = "IN"
            q = f"""
            {{
              jobData(input: {{ jobKeys: ["{jk}"] }}) {{
                results {{
                  job {{
                    key
                    title
                    employer {{ name }}
                    location {{ formatted {{ short long }} }}
                    description {{ text html }}
                    recruit {{ viewJobUrl }}
                  }}
                }}
              }}
            }}
            """
            r = requests.post("https://apis.indeed.com/graphql", headers=h, json={"query": q}, timeout=10)
            if r.status_code == 200:
                results = r.json().get("data", {}).get("jobData", {}).get("results", [])
                if results:
                    j = results[0].get("job", {})
                    desc = (j.get("description", {}).get("text") or j.get("description", {}).get("html") or "").strip()
                    title = (j.get("title") or "Developer").strip()
                    if desc or title:
                        co = j.get("employer", {}).get("name") if j.get("employer") else "Company"
                        loc = "India"
                        if j.get("location"):
                            loc = j["location"].get("formatted", {}).get("short") or j["location"].get("formatted", {}).get("long") or "India"
                        canonical_url = f"https://in.indeed.com/viewjob?jk={jk}"
                        return {
                            "title": title[:300],
                            "company": co[:200],
                            "location": loc[:200],
                            "description": desc[:8000],
                            "url": canonical_url,
                            "source": "indeed",
                            "posted_at": datetime.utcnow().isoformat()
                        }
        except Exception as e:
            # If GraphQL had an unexpected exception on an Indeed URL, don't silently fall through
            # to plain requests.get() which is guaranteed to fail with Cloudflare 403.
            if is_indeed:
                raise RuntimeError(
                    "Indeed blocked automated access for this link (access restricted). "
                    "Please copy the job description directly from the job page and paste it into the 'Paste Job Description' tab."
                ) from e
            print("Indeed GraphQL fetch error:", e)

        # If it was an Indeed URL and GraphQL returned no job results (e.g. invalid or expired jobKey)
        if is_indeed:
            raise RuntimeError(
                "Could not extract job posting from Indeed (posting may have expired or is unavailable). "
                "Please copy the job description from the page and paste it into the 'Paste Job Description' tab."
            )

    # 1b. Indeed URL provided without any job key (search results or category page)
    if is_indeed:
        raise ValueError(
            "This Indeed link is a search or category page, not an individual job posting. "
            "Please click into an individual job and copy its direct link, or copy and paste the job description text into 'Paste Job Description'."
        )

    # 2. SmartRecruiters direct API lookup
    sr_match = re.search(r'smartrecruiters\.com/([^/]+)/([0-9a-zA-Z]+)', url)
    if sr_match:
        try:
            co_slug, post_id = sr_match.groups()
            sr_res = requests.get(f"https://api.smartrecruiters.com/v1/companies/{co_slug}/postings/{post_id}", timeout=10)
            if sr_res.status_code == 200:
                d = sr_res.json()
                title = d.get("name") or "Developer"
                co = d.get("company", {}).get("name") or co_slug.replace("-", " ").title()
                loc_d = d.get("location", {})
                loc = loc_d.get("city") or loc_d.get("country") or "India"
                job_desc = d.get("jobAd", {}).get("sections", {})
                desc_parts = []
                for _, sec_val in job_desc.items():
                    if isinstance(sec_val, dict) and sec_val.get("text"):
                        c_txt = re.sub(r"<[^>]+>", " ", sec_val["text"])
                        desc_parts.append(html.unescape(c_txt).strip())
                return {
                    "title": title[:300],
                    "company": co[:200],
                    "location": loc[:200],
                    "description": "\n\n".join(desc_parts)[:8000],
                    "url": url,
                    "source": "smartrecruiters",
                    "posted_at": datetime.utcnow().isoformat()
                }
        except Exception as e:
            print("SmartRecruiters fetch error:", e)

    # 3. Greenhouse direct API lookup
    gh_match = re.search(r'greenhouse\.io/([^/]+)/jobs/([0-9]+)', url)
    if gh_match:
        try:
            co_slug, job_id = gh_match.groups()
            gh_res = requests.get(f"https://boards-api.greenhouse.io/v1/boards/{co_slug}/jobs/{job_id}", timeout=10)
            if gh_res.status_code == 200:
                d = gh_res.json()
                title = d.get("title") or "Developer"
                loc = d.get("location", {}).get("name") or "Remote"
                content = d.get("content") or ""
                clean_content = html.unescape(re.sub(r"<[^>]+>", " ", content)).strip()
                return {
                    "title": title[:300],
                    "company": co_slug.replace("-", " ").title()[:200],
                    "location": loc[:200],
                    "description": clean_content[:8000],
                    "url": url,
                    "source": "greenhouse",
                    "posted_at": datetime.utcnow().isoformat()
                }
        except Exception as e:
            print("Greenhouse fetch error:", e)

    # 4. Lever direct API lookup
    lever_match = re.search(r'jobs\.lever\.co/([^/]+)/([a-f0-9\-]+)', url)
    if lever_match:
        try:
            co_slug, job_id = lever_match.groups()
            lev_res = requests.get(f"https://api.lever.co/v0/postings/{co_slug}/{job_id}", timeout=10)
            if lev_res.status_code == 200:
                d = lev_res.json()
                title = d.get("text") or "Developer"
                cats = d.get("categories", {})
                loc = cats.get("location") or "Remote"
                desc = d.get("descriptionPlain") or ""
                return {
                    "title": title[:300],
                    "company": co_slug.replace("-", " ").title()[:200],
                    "location": loc[:200],
                    "description": desc[:8000],
                    "url": url,
                    "source": "lever",
                    "posted_at": datetime.utcnow().isoformat()
                }
        except Exception as e:
            print("Lever fetch error:", e)

    # 5. General URL fetch for all other websites (LinkedIn, Naukri, Cutshort, etc.)
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    try:
        _resp, raw = _safe_get(url, headers, timeout=15)
    except requests.exceptions.HTTPError as e:
        status = getattr(e.response, "status_code", None)
        if status in (401, 403):
            raise RuntimeError(
                f"Access restricted by host (HTTP {status}): This website prevents automated scraping. "
                "Please copy the job description text and use the 'Paste Job Description' tab."
            ) from e
        raise RuntimeError(f"Could not fetch job link (HTTP {status}): {e}") from e
    except requests.exceptions.RequestException as e:
        raise RuntimeError(f"Network error while connecting to job link: {e}") from e

    clean = re.sub(r"<script.*?</script>|<style.*?</style>", " ", raw, flags=re.I | re.S)
    clean = re.sub(r"<[^>]+>", " ", clean)
    clean = html.unescape(re.sub(r"\s+", " ", clean)).strip()
    m = re.search(r"<title>(.*?)</title>", raw, re.I | re.S)
    title = html.unescape(m.group(1).strip())[:300] if m else url[:80]
    title = re.sub(r"\s*[-|]\s*(Indeed|LinkedIn|Glassdoor).*$", "", title, flags=re.I).strip() or title
    return {
        "title": title[:300],
        "company": "",
        "location": "India",
        "description": clean[:8000],
        "url": url,
        "source": "manual",
        "posted_at": datetime.utcnow().isoformat()
    }

