import hashlib
import html
import json
import os
import re
import sqlite3
import xml.etree.ElementTree as ET
from datetime import datetime

import requests
from dotenv import load_dotenv

from matcher import build_search_queries, compute_match

load_dotenv()
DB = os.path.join(os.path.dirname(__file__), "jobs.db")
PROFILE = os.path.join(os.path.dirname(__file__), "profile.json")


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


def profile_search_location(p):
    """Structured {city,state,country} or legacy 'Bangalore, India' string. Never hardcode a city."""
    loc = p.get("location", {})
    if isinstance(loc, dict):
        parts = [loc.get("city", ""), loc.get("state", ""), loc.get("country", "India")]
        return ", ".join(x for x in parts if x), loc.get("city", "") or "India"
    s = str(loc)
    return s, s.split(",")[0].strip() or "India"


def fetch_arbeitnow(limit=50):
    # ponytail: no key, CORS yes, best free source for quick daily pull
    try:
        d = requests.get("https://arbeitnow.com/api/job-board-api", timeout=20).json()
        jobs = d.get("data", d) if isinstance(d, dict) else d
        out = []
        for j in jobs[:limit]:
            out.append({"title": j.get("title",""), "company": j.get("company_name",""),
              "location": j.get("location",""), "description": " ".join(j.get("tags",[]) or []),
              "url": j.get("url",""), "source": "arbeitnow", "posted_at": str(j.get("created_at",""))})
        return out
    except Exception as e:
        print("arbeitnow fail:", e)
        return []


def fetch_remotive(search="full stack", limit=30):
    try:
        d = requests.get(f"https://remotive.com/api/remote-jobs?search={search}&limit={limit}", timeout=20).json()
        return [{"title": j.get("title",""), "company": j.get("company_name",""),
          "location": j.get("candidate_required_location","Remote"),
          "description": (j.get("description") or "")[:8000],
          "url": j.get("url",""), "source": "remotive",
          "posted_at": j.get("publication_date","")} for j in d.get("jobs", [])]
    except Exception as e:
        print("remotive fail:", e)
        return []


def fetch_adzuna(what="full stack developer", where="India", limit=20):
    aid, akey = os.getenv("ADZUNA_APP_ID"), os.getenv("ADZUNA_APP_KEY")
    if not aid or not akey:
        return []
    try:
        u = f"https://api.adzuna.com/v1/api/jobs/in/search/1?app_id={aid}&app_key={akey}&what={what}&where={where}&results_per_page={limit}&content-type=application/json"
        d = requests.get(u, timeout=20).json()
        return [{"title": j.get("title",""), "company": j.get("company",{}).get("display_name",""),
          "location": j.get("location",{}).get("display_name",""),
          "description": (j.get("description") or "")[:8000],
          "url": j.get("redirect_url",""), "source": "adzuna",
          "posted_at": j.get("created","")} for j in d.get("results", [])]
    except Exception as e:
        print("adzuna fail:", e)
        return []


def fetch_jobspy(search="full stack developer", location="India", wanted=20, is_remote=False, hours_old=None):
    # ponytail: Glassdoor consistently returns 400 'location not parsed' for Indian cities,
    # and Google blocks/captchas. Keeping indeed + linkedin gives 3x faster, rock-solid India scraping.
    # hours_old is optional; many active Indeed roles (like StarClinch) have older initial ATS dates.
    try:
        from jobspy import scrape_jobs
        clean_search = re.sub(r'["\']', '', search).strip()
        kwargs = {
            "site_name": ["indeed", "linkedin"],
            "search_term": clean_search,
            "location": location,
            "results_wanted": wanted,
            "country_indeed": "India",
            "verbose": 0,
            "is_remote": is_remote
        }
        if hours_old:
            kwargs["hours_old"] = hours_old
        df = scrape_jobs(**kwargs)
        out = []
        for _, r in df.iterrows():
            out.append({"title": str(r.get("title","")), "company": str(r.get("company","")),
              "location": str(r.get("location","")), "description": str(r.get("description",""))[:8000],
              "url": str(r.get("job_url","")), "source": str(r.get("site","jobspy")),
              "posted_at": str(r.get("date_posted",""))})
        return out
    except Exception as e:
        print("jobspy skip:", e)
        return []


def fetch_job_from_url(url):
    """Manual Indeed/LinkedIn/Any URL import:
    // ponytail: Indeed blocks plain HTTP with Cloudflare 401; GraphQL jobData endpoint
    // bypasses Cloudflare cleanly and returns 100% structured title, company, location & JD text.
    For non-Indeed URLs, falls back to clean HTML extraction.
    """
    url = (url or "").strip()
    if not url:
        return None

    # 1. Check if Indeed URL or contains jobKey (jk)
    jk_match = re.search(r'(?:[?&]|%26|/viewjob\?jk=)jk(?:=|%3D)([a-f0-9]+)', url, re.I)
    if not jk_match and re.fullmatch(r'[a-f0-9]{16}', url, re.I):
        jk_match = re.search(r'([a-f0-9]{16})', url)

    if jk_match:
        jk = jk_match.group(1)
        try:
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
                    title = j.get("title") or "Developer"
                    co = j.get("employer", {}).get("name") if j.get("employer") else "Company"
                    loc = "India"
                    if j.get("location"):
                        loc = j["location"].get("formatted", {}).get("short") or j["location"].get("formatted", {}).get("long") or "India"
                    desc = (j.get("description", {}).get("text") or j.get("description", {}).get("html") or "")[:8000]
                    canonical_url = f"https://in.indeed.com/viewjob?jk={jk}"
                    return {
                        "title": title[:300],
                        "company": co[:200],
                        "location": loc[:200],
                        "description": desc,
                        "url": canonical_url,
                        "source": "indeed",
                        "posted_at": datetime.utcnow().isoformat()
                    }
        except Exception as e:
            print("Indeed GraphQL fetch error:", e)

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
    r = requests.get(url, headers=headers, timeout=15, allow_redirects=True)
    r.raise_for_status()
    raw = r.text
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


def fetch_yc_hn(limit=35):
    """Fetch latest Ask HN: Who is hiring? top-level posts from YC/tech startup founders."""
    try:
        r = requests.get('https://hn.algolia.com/api/v1/search_by_date?tags=story,author_whoishiring', timeout=10).json()
        hits = r.get('hits', [])
        hiring_stories = [h for h in hits if 'who is hiring' in h.get('title', '').lower()]
        if not hiring_stories:
            return []
        story_id = hiring_stories[0]['objectID']
        item_data = requests.get(f'https://hn.algolia.com/api/v1/items/{story_id}', timeout=15).json()
        comments = item_data.get('children', [])
        
        out = []
        for c in comments:
            raw_html = c.get('text') or ''
            if not raw_html:
                continue
            clean_text = re.sub(r'<p>', '\n\n', raw_html)
            clean_text = re.sub(r'<br\s*/?>', '\n', clean_text)
            clean_text = re.sub(r'<[^>]+>', '', clean_text)
            clean_text = html.unescape(clean_text).strip()
            
            lines = [line.strip() for line in clean_text.split('\n') if line.strip()]
            if not lines:
                continue
            first_line = lines[0]
            parts = [p.strip() for p in first_line.split('|')]
            
            company = parts[0] if len(parts) >= 1 else "Startup"
            title = parts[1] if len(parts) >= 2 else "Software Engineer"
            loc = parts[2] if len(parts) >= 3 else "Remote"
            
            links = re.findall(r'href=[\'"]([^\'"]+)[\'"]', raw_html)
            app_url = links[0] if links else f"https://news.ycombinator.com/item?id={c.get('id')}"
            
            out.append({
                "title": title[:300],
                "company": company[:200],
                "location": loc[:200],
                "description": clean_text[:8000],
                "url": app_url,
                "source": "YC / HN",
                "posted_at": c.get("created_at", "")
            })
            if len(out) >= limit:
                break
        return out
    except Exception as e:
        print("yc_hn fail:", e)
        return []


def fetch_hasjob(limit=30):
    """Fetch premier Indian tech startup jobs from Hasjob (HasGeek) Atom feed."""
    try:
        r = requests.get('https://hasjob.co/feed', headers={'User-Agent': 'Mozilla/5.0'}, timeout=12)
        if r.status_code != 200:
            return []
        root = ET.fromstring(r.content)
        ns = {'a': 'http://www.w3.org/2005/Atom'}
        entries = root.findall('a:entry', ns)
        out = []
        for e in entries:
            t = e.find('a:title', ns)
            title = t.text if t is not None else "Developer"
            link_tag = e.find('a:link', ns)
            url = link_tag.attrib.get('href', '') if link_tag is not None else ""
            summary_tag = e.find('a:summary', ns) or e.find('a:content', ns)
            desc = ""
            if summary_tag is not None and summary_tag.text:
                desc = re.sub(r'<[^>]+>', ' ', summary_tag.text)
                desc = html.unescape(desc).strip()
            
            updated_tag = e.find('a:updated', ns)
            posted = updated_tag.text if updated_tag is not None else ""
            
            author_tag = e.find('a:author', ns)
            co = "Indian Tech Startup"
            if author_tag is not None:
                name_tag = author_tag.find('a:name', ns)
                if name_tag is not None and name_tag.text:
                    co = name_tag.text.strip()
            
            loc = "India (Remote / Hybrid)"
            desc_l = desc.lower()
            if "mumbai" in desc_l:
                loc = "Mumbai, India"
            elif "bangalore" in desc_l or "bengaluru" in desc_l:
                loc = "Bangalore, India"
            elif "delhi" in desc_l or "gurgaon" in desc_l or "noida" in desc_l:
                loc = "NCR, India"
            elif "remote" in desc_l:
                loc = "Remote, India"
            
            out.append({
                "title": title[:300],
                "company": co[:200],
                "location": loc[:200],
                "description": desc[:8000],
                "url": url,
                "source": "hasjob",
                "posted_at": posted
            })
            if len(out) >= limit:
                break
        return out
    except Exception as e:
        print("hasjob fail:", e)
        return []


def fetch_remoteok(tags=("react", "node", "javascript", "full-stack", "frontend"), limit=35):
    """Fetch tech startup jobs from RemoteOK API."""
    try:
        r = requests.get('https://remoteok.com/api', headers={'User-Agent': 'Mozilla/5.0'}, timeout=12)
        if r.status_code != 200:
            return []
        items = r.json()
        out = []
        for j in items:
            if not isinstance(j, dict) or not j.get("id"):
                continue
            job_tags = [t.lower() for t in j.get("tags", [])]
            if not any(tag in job_tags for tag in tags) and "developer" not in j.get("position", "").lower():
                continue
            
            loc = j.get("location") or "Worldwide Remote"
            out.append({
                "title": j.get("position", "")[:300],
                "company": j.get("company", "")[:200],
                "location": loc[:200],
                "description": (j.get("description") or "")[:8000],
                "url": j.get("url") or f"https://remoteok.com/remote-jobs/{j.get('id')}",
                "source": "remoteok",
                "posted_at": str(j.get("date", ""))
            })
            if len(out) >= limit:
                break
        return out
    except Exception as e:
        print("remoteok fail:", e)
        return []


def fetch_himalayas(limit=35):
    """Fetch modern tech startup jobs from Himalayas API."""
    try:
        r = requests.get('https://himalayas.app/jobs/api?limit=50', headers={'User-Agent': 'Mozilla/5.0'}, timeout=12)
        if r.status_code != 200:
            return []
        items = r.json().get('jobs', [])
        out = []
        for j in items:
            restr = j.get("locationRestrictions") or []
            if not restr:
                loc = "Worldwide Remote"
            else:
                loc = f"Remote ({', '.join(restr)})"
            
            raw_desc = j.get("description") or ""
            clean_desc = re.sub(r'<[^>]+>', ' ', raw_desc)
            clean_desc = html.unescape(clean_desc).strip()
            
            out.append({
                "title": j.get("title", "")[:300],
                "company": j.get("companyName", "")[:200],
                "location": loc[:200],
                "description": clean_desc[:8000],
                "url": j.get("applicationLink") or f"https://himalayas.app/companies/{j.get('companySlug')}/jobs/{j.get('guid')}",
                "source": "himalayas",
                "posted_at": str(j.get("pubDate", ""))
            })
            if len(out) >= limit:
                break
        return out
    except Exception as e:
        print("himalayas fail:", e)
        return []


def fetch_jobicy(limit=30):
    """Fetch engineering developer jobs from Jobicy API."""
    try:
        r = requests.get('https://jobicy.com/api/v2/remote-jobs?count=40&industry=engineering', headers={'User-Agent': 'Mozilla/5.0'}, timeout=12)
        if r.status_code != 200:
            return []
        items = r.json().get('jobs', [])
        out = []
        for j in items:
            loc = j.get("jobGeo") or "Remote"
            raw_desc = j.get("jobDescription") or ""
            clean_desc = re.sub(r'<[^>]+>', ' ', raw_desc)
            clean_desc = html.unescape(clean_desc).strip()
            
            out.append({
                "title": j.get("jobTitle", "")[:300],
                "company": j.get("companyName", "")[:200],
                "location": loc[:200],
                "description": clean_desc[:8000],
                "url": j.get("url", ""),
                "source": "jobicy",
                "posted_at": str(j.get("pubDate", ""))
            })
            if len(out) >= limit:
                break
        return out
    except Exception as e:
        print("jobicy fail:", e)
        return []


def fetch_wttj(search="full stack developer", limit=35):
    """Fetch startup & tech developer jobs from Welcome to the Jungle Algolia API."""
    try:
        app_id = "CSEKHVMS53"
        api_key = "4bd8f6215d0cc52b26430765769e65a0"
        url = f"https://{app_id.lower()}-dsn.algolia.net/1/indexes/*/queries"
        headers = {
            "x-algolia-application-id": app_id,
            "x-algolia-api-key": api_key,
            "Content-Type": "application/json",
            "Referer": "https://www.welcometothejungle.com/",
            "Origin": "https://www.welcometothejungle.com",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        payload = {
            "requests": [
                {
                    "indexName": "wttj_jobs_production_en",
                    "params": f"query={search}&hitsPerPage={limit}"
                }
            ]
        }
        r = requests.post(url, headers=headers, json=payload, timeout=15)
        if r.status_code != 200:
            print(f"wttj status {r.status_code}: {r.text[:200]}")
            return []
            
        data = r.json()
        results = data.get("results", [])
        if not results:
            return []
            
        hits = results[0].get("hits", [])
        out = []
        for h in hits:
            name = h.get("name") or h.get("title") or ""
            if not name:
                continue
                
            org = h.get("organization") or {}
            co = org.get("name") or "Tech Startup"
            org_slug = org.get("slug")
            job_slug = h.get("slug")
            
            if org_slug and job_slug:
                job_url = f"https://www.welcometothejungle.com/en/companies/{org_slug}/jobs/{job_slug}"
            else:
                job_url = f"https://www.welcometothejungle.com/en/jobs/{h.get('objectID', '')}"
                
            offices = h.get("offices") or []
            city = offices[0].get("city") if offices else ""
            country = offices[0].get("country") if offices else ""
            rem = str(h.get("remote") or "").lower()
            
            loc_parts = [p for p in (city, country) if p]
            loc_str = ", ".join(loc_parts)
            if rem == "fulltime":
                location = "Worldwide Remote" if not loc_str else f"Remote ({loc_str})"
            elif rem == "partial":
                location = f"Hybrid ({loc_str})" if loc_str else "Hybrid"
            else:
                location = loc_str or "Remote / Europe"
                
            desc_parts = []
            if h.get("summary"):
                desc_parts.append(h["summary"])
            if h.get("key_missions"):
                missions = h["key_missions"]
                if isinstance(missions, list):
                    desc_parts.append("\nKey Missions:\n" + "\n".join(f"- {m}" for m in missions))
                else:
                    desc_parts.append(str(missions))
            if h.get("profile"):
                clean_prof = re.sub(r"<[^>]+>", " ", h["profile"]).strip()
                clean_prof = html.unescape(clean_prof)
                if clean_prof:
                    desc_parts.append("\nProfile Requirements:\n" + clean_prof)
                    
            description = "\n\n".join(desc_parts)[:8000]
            
            out.append({
                "title": name[:300],
                "company": co[:200],
                "location": location[:200],
                "description": description,
                "url": job_url,
                "source": "wttj",
                "posted_at": str(h.get("published_at") or "")
            })
            if len(out) >= limit:
                break
        return out
    except Exception as e:
        print("wttj fail:", e)
        return []


def check_closed_jobs(con, p):
    """Auto-detect if any eligible jobs are closed / dead links."""
    import concurrent.futures
    from matcher import compute_match
    cur = con.execute("SELECT * FROM jobs WHERE closed=0")
    cols = [c[0] for c in cur.description]
    jobs = [dict(zip(cols, r)) for r in cur.fetchall()]
    eligible_jobs = [j for j in jobs if compute_match(p, j)["eligible"]]
    if not eligible_jobs:
        return 0

    closed_signals = [
        "no longer accepting applications",
        "closed-job__flavor--closed",
        "this job has expired",
        "job is no longer available",
        "this job is closed",
        "posting has expired",
        "position has been filled"
    ]
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }

    def check_url(j):
        url = j.get("url")
        if not url or url == "#":
            return None
        try:
            r = requests.get(url, headers=headers, timeout=6, allow_redirects=True)
            if r.status_code in (404, 410):
                return j["url_hash"]
            txt = r.text.lower()
            if any(sig in txt for sig in closed_signals):
                return j["url_hash"]
        except Exception:
            pass
        return None

    closed_hashes = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        for res in executor.map(check_url, eligible_jobs):
            if res:
                closed_hashes.append(res)

    if closed_hashes:
        for h in closed_hashes:
            con.execute("UPDATE jobs SET closed=1 WHERE url_hash=?", (h,))
        con.commit()
    return len(closed_hashes)


def stage_report(con, p, fetched_total=0, new_rows=0, dedup_skipped=0):
    """Pipeline counts: dedupe is at INSERT; gates via matcher on full pool."""
    from matcher import compute_match
    cur = con.execute("SELECT * FROM jobs")
    cols = [c[0] for c in cur.description]
    jobs = [dict(zip(cols, r)) for r in cur.fetchall()]
    res = [compute_match(p, j) for j in jobs]
    n_loc = sum(1 for m in res if not m["location_match"])
    n_exp = sum(1 for m in res if not m["experience_match"])
    n_stack = sum(1 for m in res if m["core_stack_match"] is False)
    n_title = sum(1 for m in res if any("engineering role" in r for r in m["rejection_reasons"]))
    n_closed = sum(1 for j in jobs if j.get("closed"))
    n_elig = sum(1 for j, m in zip(jobs, res) if m["eligible"] and not j.get("closed"))
    n_strong = sum(1 for j, m in zip(jobs, res) if m["eligible"] and not j.get("closed") and m["match_score"] >= 60)
    n_poss = sum(1 for j, m in zip(jobs, res) if m["eligible"] and not j.get("closed") and 35 <= m["match_score"] < 60)

    print("\n" + "="*45)
    print("PIPELINE STAGE METRICS")
    print("="*45)
    print(f"Fetched:             {fetched_total}")
    print(f"Deduplicated:        {dedup_skipped} skipped ({new_rows} new rows added)")
    print(f"Location rejected:   {n_loc}")
    print(f"Experience rejected: {n_exp}")
    print(f"Stack rejected:      {n_stack}")
    print(f"Title rejected:      {n_title}")
    print(f"Closed / Inactive:   {n_closed}")
    print(f"Eligible (Active):   {n_elig}")
    print(f"Strong:              {n_strong}")
    print(f"Possible:            {n_poss}")
    print("="*45 + "\n")
    return {
        "fetched": fetched_total, "new_rows": new_rows, "dedup_skipped": dedup_skipped,
        "location_rejected": n_loc, "experience_rejected": n_exp, "stack_rejected": n_stack,
        "title_rejected": n_title, "closed": n_closed, "eligible": n_elig, "strong": n_strong, "possible": n_poss
    }


def run_fetch_pipeline(include_jobspy=True, max_spy_wanted=20, check_closed=False):
    """Run full job ingestion pipeline across all tech sources and save to DB."""
    if not os.path.exists(PROFILE):
        example_p = os.path.join(os.path.dirname(__file__), "profile.example.json")
        if os.path.exists(example_p):
            try:
                import shutil
                shutil.copyfile(example_p, PROFILE)
            except Exception:
                pass
    target_prof = PROFILE if os.path.exists(PROFILE) else os.path.join(os.path.dirname(__file__), "profile.example.json")
    if not os.path.exists(target_prof):
        return {"status": "error", "message": "profile.json or profile.example.json not found", "new_rows": 0, "total_fetched": 0}
    with open(target_prof, encoding="utf-8") as f:
        p = json.load(f)
    term = p.get("search_terms", ["Full Stack Developer"])[0]
    search_loc, where_city = profile_search_location(p)
    queries = build_search_queries(p, n=6)
    
    con = db()
    try:
        before = con.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
        
        # 1. Fast API sources
        print("Fetching from Arbeitnow, Remotive, Adzuna...")
        api_base = fetch_arbeitnow() + fetch_remotive("React Node") + fetch_adzuna(term, where_city)
        print("Fetching from Hasjob (Indian Tech Startups)...")
        api_hasjob = fetch_hasjob(limit=30)
        print("Fetching from YC / Hacker News (Who is Hiring)...")
        api_yc = fetch_yc_hn(limit=35)
        print("Fetching from RemoteOK, Himalayas, Jobicy...")
        api_remote = fetch_remoteok(limit=35) + fetch_himalayas(limit=35) + fetch_jobicy(limit=30)
        print("Fetching from Welcome to the Jungle (WTTJ Tech Startups)...")
        api_wttj = fetch_wttj(search=term, limit=35)
        if len(api_wttj) < 20 and len(queries) > 1:
            api_wttj += fetch_wttj(search=queries[1], limit=25)
        
        rows = api_base + api_hasjob + api_yc + api_remote + api_wttj
        fetched_api = len(rows)
        save(con, rows)
        print(f"Total API & Startup jobs fetched: {fetched_api}")
        
        # 2. Scraped job sources via JobSpy (if requested)
        fetched_spy = 0
        if include_jobspy:
            print("Fetching from JobSpy (Indeed/LinkedIn)...")
            is_remote_pref = p.get("work_preferences", {}).get("remote", True)
            for qq in queries:
                try:
                    spy = fetch_jobspy(qq, search_loc, wanted=max_spy_wanted)
                    fetched_spy += len(spy)
                    save(con, spy)
                except Exception as e:
                    print(f"JobSpy local error for {qq}: {e}")

            # Also fetch India-wide remote postings for primary tech queries
            if is_remote_pref and queries:
                print("Fetching India-wide Remote roles from JobSpy...")
                for rq in queries[:3]:
                    try:
                        r_spy = fetch_jobspy(rq, "India", wanted=10, is_remote=True)
                        fetched_spy += len(r_spy)
                        save(con, r_spy)
                    except Exception as e:
                        print(f"JobSpy remote error for {rq}: {e}")
                    
        after = con.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
        total_fetched = fetched_api + fetched_spy
        new_rows = max(0, after - before)
        dedup_skipped = max(0, total_fetched - new_rows)
        
        newly_closed = 0
        if check_closed:
            newly_closed = check_closed_jobs(con, p)
            if newly_closed:
                print(f"Auto-detected {newly_closed} closed jobs and marked them inactive.")
                
        metrics = stage_report(con, p, fetched_total=total_fetched, new_rows=new_rows, dedup_skipped=dedup_skipped)

        # 3. Check for unalerted jobs & dispatch Indeed-style email digest
        alert_info = {"sent": False, "jobs_alerted": 0, "recipient": None}
        try:
            from notifier import is_smtp_configured, send_job_alert_email, get_smtp_config
            if is_smtp_configured():
                smtp_cfg = get_smtp_config()
                if smtp_cfg.get("enabled", True):
                    cur_unalerted = con.execute("SELECT * FROM jobs WHERE alert_sent = 0 AND closed = 0")
                    u_cols = [c[0] for c in cur_unalerted.description]
                    unalerted_jobs = [dict(zip(u_cols, r)) for r in cur_unalerted.fetchall()]
                    
                    if unalerted_jobs:
                        scored_unalerted = []
                        min_score = smtp_cfg.get("min_score", 50)
                        for uj in unalerted_jobs:
                            m = compute_match(p, uj)
                            if m["eligible"] and m["match_score"] >= min_score:
                                scored_unalerted.append({**uj, **m})
                        
                        scored_unalerted.sort(key=lambda x: x.get("match_score", 0), reverse=True)
                        
                        if scored_unalerted:
                            top_digest = scored_unalerted[:15]
                            email_res = send_job_alert_email(top_digest, p)
                            alert_info = {
                                "sent": email_res.get("success", False),
                                "jobs_alerted": len(top_digest),
                                "recipient": email_res.get("recipient"),
                                "error": email_res.get("error")
                            }
                            if email_res.get("success"):
                                print(f"Email alert sent to {email_res.get('recipient')} with {len(top_digest)} jobs!")
                            else:
                                print(f"Email alert failed: {email_res.get('error')}")
                        
                        # Mark all unalerted jobs as alert_sent = 1 so they are not processed again
                        hashes = [uj["url_hash"] for uj in unalerted_jobs]
                        con.executemany("UPDATE jobs SET alert_sent = 1 WHERE url_hash = ?", [(h,) for h in hashes])
                        con.commit()
            else:
                # Still mark unalerted jobs so DB doesn't accumulate backlog if alerts disabled
                con.execute("UPDATE jobs SET alert_sent = 1 WHERE alert_sent = 0")
                con.commit()
        except Exception as e:
            print(f"Error checking/sending job alerts: {e}")

        return {
            "status": "success",
            "total_fetched": total_fetched,
            "new_rows": new_rows,
            "dedup_skipped": dedup_skipped,
            "newly_closed": newly_closed,
            "total_in_db": after,
            "timestamp": datetime.utcnow().isoformat(),
            "metrics": metrics,
            "alert_info": alert_info
        }
    finally:
        con.close()


if __name__ == "__main__":
    res = run_fetch_pipeline(include_jobspy=True, max_spy_wanted=20, check_closed=True)
    print("Pipeline result:", res)

