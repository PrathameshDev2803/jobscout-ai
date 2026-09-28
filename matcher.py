"""Shared matching backend: DISCOVERY (eligible YES/NO) + MATCH (0-100).

Pipeline: profile -> hard filter (location, experience, core stack)
          -> tiered skill match (must_have > important > nice_to_have) -> score.
Fetching and matching are separate problems; this module is the matching half.
"""
import html
import re

# ---------- skill vocabulary: name -> regex (case-insensitive) ----------
SKILL_PATTERNS = [
    ("C#", r"c#"),
    ("ASP.NET", r"asp\.net"),
    (".NET", r"\.net\b|dotnet"),
    ("Entity Framework", r"entity framework|\bef core\b"),
    ("MS SQL", r"ms[\s-]?sql|sql server|\bt-?sql\b|stored procedures?|\btriggers\b"),
    ("MySQL", r"mysql"),
    ("PostgreSQL", r"postgres"),
    ("MongoDB", r"mongo"),
    ("React", r"\breact\b"),
    ("Next.js", r"next(\.js)?\b"),
    ("Angular", r"angular"),
    ("Vue", r"\bvue\b"),
    ("Redux", r"redux"),
    ("TypeScript", r"typescript"),
    ("JavaScript", r"javascript"),
    ("HTML", r"\bhtml\b"),
    ("CSS", r"\bcss\b"),
    ("Tailwind", r"tailwind"),
    ("Node.js", r"node(\.js)?\b"),
    ("Express", r"express"),
    ("NestJS", r"nestjs"),
    ("REST API", r"\brest(ful)?\b|web api"),
    ("GraphQL", r"graphql"),
    ("JWT/OAuth", r"\bjwt\b|oauth"),
    ("Microservices", r"microservices?"),
    ("Python", r"\bpython\b"),
    ("Django", r"django"),
    ("FastAPI", r"fastapi"),
    ("Flask", r"flask"),
    ("PHP", r"\bphp\b"),
    ("Laravel", r"laravel"),
    ("Java", r"\bjava(?!script)\b"),
    ("Spring", r"\bspring\b"),
    ("Ruby", r"\bruby\b"),
    ("Rails", r"\brails\b"),
    ("Go", r"\bgolang\b"),
    ("Docker", r"docker"),
    ("Git", r"\bgit\b"),
    ("AWS", r"\baws\b"),
    ("CI/CD", r"ci/cd|cicd"),
    ("Kubernetes", r"kubernetes|\bk8s\b"),
]
_PATTERNS = [(n, re.compile(p, re.I)) for n, p in SKILL_PATTERNS]

BACKEND_FAMILIES = {
    "dotnet": ["C#", ".NET", "ASP.NET", "Entity Framework"],
    "node": ["Node.js", "Express", "NestJS"],
    "python": ["Python", "Django", "FastAPI", "Flask"],
    "php": ["PHP", "Laravel"],
    "java": ["Java", "Spring"],
    "ruby": ["Ruby", "Rails"],
    "go": ["Go"],
}
FRONTEND_CORE = ["React", "Angular", "Vue", "Next.js"]

TIER_WEIGHTS = {"must_have": 3, "important": 2, "nice_to_have": 1}

OTHER_METROS = ["bangalore", "bengaluru", "delhi", "new delhi", "noida", "gurgaon", "gurugram",
                "hyderabad", "chennai", "pune", "kolkata", "ahmedabad", "kochi",
                "coimbatore", "jaipur", "lucknow", "indore", "surat", "nagpur",
                "chandigarh", "bhubaneswar", "visakhapatnam", "trivandrum", "thiruvananthapuram"]
MUMBAI_MMR = [
    "mumbai", "bombay", "navi mumbai", "thane", "kalyan", "dombivli",
    "mira bhayandar", "navi-mumbai", "airoli", "ghansoli", "rabale",
    "mahape", "vashi", "nerul", "andheri", "bkc", "kurla", "dadar",
    "borivali", "goregaon", "malad", "powai", "kanjurmarg", "bhandup", "mulund"
]
FOREIGN_HINTS = ["usa", "united states", "us", "u.s.", "uk", "united kingdom", "germany",
                 "deutschland", "canada", "singapore", "australia", "berlin",
                 "london", "paris", "europe", "argentina", "mexico", "peru",
                 "brazil", "poland", "netherlands", "switzerland", "ireland",
                 "spain", "france", "austria", "sweden", "japan", "new zealand",
                 "romania", "norway", "denmark", "finland", "italy", "portugal",
                 "czech", "hungary", "dach", "ontario", "colombia", "chile", "philippines"]
# state names: bare "Karnataka" (no city, no India ctx) must still reject
OTHER_STATES = ["karnataka", "tamil nadu", "telangana", "andhra pradesh", "kerala",
                "west bengal", "gujarat", "rajasthan", "punjab", "uttar pradesh",
                "madhya pradesh", "bihar", "odisha", "assam", "haryana",
                "uttarakhand", "chhattisgarh", "jharkhand", "himachal pradesh",
                "goa", "delhi"]
ALL_DBS = ["MS SQL", "MySQL", "PostgreSQL", "MongoDB"]
STATE_CODES = {"ka": "karnataka", "mh": "maharashtra", "tn": "tamil nadu",
               "ap": "andhra pradesh", "ts": "telangana", "kl": "kerala",
               "dl": "delhi", "wb": "west bengal", "gj": "gujarat",
               "rj": "rajasthan", "pb": "punjab", "up": "uttar pradesh",
               "mp": "madhya pradesh", "hr": "haryana", "uk": "uttarakhand",
               "ct": "chhattisgarh", "jh": "jharkhand", "hp": "himachal pradesh",
               "ga": "goa"}
SENIOR_TITLE = re.compile(r"\bsenior\b|\bsr\.?\b|lead|principal|staff|architect|manager|director|\bhead of\b|\bvp\b", re.I)
ROLE_TITLE = re.compile(r"develop|engineer|software|\bsde\b|\bdev\b|web|frontend|front.end|backend|back.end|full.?stack|programmer|technical staff|\bmts\b", re.I)
NON_DEV_TITLE = re.compile(r"\b(sales|account|marketing|recruiter|hr|talent|salesperson|sales engineer|business development|\bbda\b|writer|content writer|designer|graphic design|product designer)\b", re.I)
REMOTE_HINTS = ["remote", "work from home", "wfh", "anywhere", "work-from-home"]


def detect_skills(text):
    t = text or ""
    return [name for name, rx in _PATTERNS if rx.search(t)]


# ---------- profile helpers ----------
def profile_location(p):
    """Backward compat: dict {city,state,country} or legacy 'Bangalore, India' string."""
    loc = p.get("location", {})
    if isinstance(loc, dict):
        city = loc.get("city", "")
        state = loc.get("state", "")
        country = loc.get("country", "India")
    else:
        parts = [x.strip() for x in str(loc).split(",")]
        city, state, country = (parts + ["", "", "India"])[:3]
    prefs = p.get("work_preferences", {})
    if not isinstance(prefs, dict):
        prefs = {}
    prefs = {"remote": prefs.get("remote", True),
             "hybrid": prefs.get("hybrid", True),
             "onsite": prefs.get("onsite", True)}
    return city, state, country, prefs


def get_location_label(p):
    city, state, _, _ = profile_location(p)
    return f"{city}, {state}" if city and state else (city or state or "India")


def profile_families(p):
    """Backend stack families the profile actually works in, derived from skills list."""
    skills = [s.lower() for s in p.get("skills", [])]
    fams = set()
    for fam, members in BACKEND_FAMILIES.items():
        if any(m.lower() in skills for m in members):
            fams.add(fam)
    return fams


def profile_dbs(p):
    skills = [s.lower() for s in p.get("skills", [])]
    return {d for d in ALL_DBS if d.lower() in skills}


# ---------- hard filter 1: location ----------
def location_match(job_loc, p):
    city, state, country, prefs = profile_location(p)
    raw = (job_loc or "").strip()
    l = raw.lower()
    if not l:
        return True, "location unknown"
    is_remote = any(h in l for h in REMOTE_HINTS)
    is_hybrid = "hybrid" in l
    is_onsite = "on-site" in l or "onsite" in l or "on site" in l

    # 1. Genuine Remote check (Bangalore remote, India remote, Remote etc.)
    if is_remote:
        # Check if remote is restricted to a foreign country or foreign cities
        restricted = False
        all_foreign = FOREIGN_HINTS + ["us only", "usa only", "uk only", "canada only", "europe only"]
        for f in all_foreign:
            pattern = rf"\b{re.escape(f)}\b"
            if re.search(pattern, l) and "india" not in l and "worldwide" not in l and "anywhere" not in l and "global" not in l:
                restricted = True
                break
        if restricted:
            return False, "foreign restricted remote"
        if prefs["remote"]:
            return True, "remote ok"
        return False, "remote not preferred"

    # 2. Other Metros check (including Pune, Bangalore, Delhi, Hyderabad, etc.)
    # Critical: Pune is in Maharashtra, but for Mumbai candidate, Pune onsite MUST reject.
    has_other_metro = any(re.search(rf"\b{re.escape(m)}\b", l) for m in OTHER_METROS if m not in MUMBAI_MMR)
    if has_other_metro and not is_remote:
        return False, "other city onsite"

    # 3. Home city / MMR check
    home_hit = False
    if city.lower() in ("mumbai", "bombay"):
        home_hit = any(re.search(rf"\b{re.escape(c)}\b", l) for c in MUMBAI_MMR)
    elif city:
        home_hit = bool(re.search(rf"\b{re.escape(city.lower())}\b", l))

    if home_hit:
        if is_hybrid and not prefs["hybrid"]:
            return False, "hybrid not preferred"
        if is_onsite and not prefs["onsite"]:
            return False, "onsite not preferred"
        return True, "home city/state"

    # 4. Other states check (e.g. Karnataka, Tamil Nadu, Telangana, etc.)
    has_other_state = any(re.search(rf"\b{re.escape(s)}\b", l) for s in OTHER_STATES if s != (state or "").lower())
    if has_other_state and not is_remote:
        return False, "other state onsite"

    # 5. State codes in India context (e.g. "KA, IN")
    tokens = re.findall(r"[a-z]+", l)
    india_ctx = "india" in l or "bharat" in l or "in" in tokens
    if india_ctx and state:
        for tok in tokens:
            mapped = STATE_CODES.get(tok)
            if mapped and mapped != state.lower() and not is_remote:
                return False, f"other state onsite ({tok.upper()})"
            if mapped and mapped == state.lower():
                return True, "home state code"

    # 6. Foreign onsite check (e.g. New York, USA, Germany, Canada)
    has_foreign = any(re.search(rf"\b{re.escape(f)}\b", l) for f in FOREIGN_HINTS)
    if has_foreign and not india_ctx and not is_remote:
        return False, "foreign onsite"

    # 7. Country-level ("India", "India Hybrid")
    if (country.lower() in l or "india" in l or "bharat" in l) and not has_other_metro and not has_other_state:
        if is_hybrid and not prefs["hybrid"]:
            return False, "hybrid not preferred"
        if is_onsite and not prefs["onsite"]:
            return False, "onsite not preferred"
        return True, "country-level"

    if not india_ctx and not home_hit and not is_remote:
        return False, "other location onsite"

    return True, "no city conflict"


# ---------- hard filter 2: experience ----------
def extract_experience(jd_text):
    t = (jd_text or "").lower()
    mins, maxs = [], []
    for a, b in re.findall(r"(\d+)\s*(?:-|–|to)\s*(\d+)\s*(?:years|yrs)", t):
        mins.append(int(a))
        maxs.append(int(b))
    for a in re.findall(r"(\d+)\s*\+\s*(?:years|yrs)", t):
        mins.append(int(a))
    for a in re.findall(r"minimum\s*(?:of\s*)?(\d+)\s*(?:years|yrs|year)", t):
        mins.append(int(a))
    if not mins:
        # standalone "N years (of) experience" only counts when no range/minimum found,
        # else a range max like "3 to 6 years of experience" double-counts as a min
        for a in re.findall(r"(\d+)\s*(?:years|yrs)\s*(?:of\s*)?experience", t):
            mins.append(int(a))
    if not mins:
        return None
    return max(mins), max(maxs) if maxs else None


def experience_verdict(req_min, profile_yrs):
    if req_min is None:
        return True, 1.0, "not specified"
    gap = req_min - profile_yrs
    if gap <= 0:
        return True, 1.0, "fits"
    if gap == 1:
        return True, 0.85, "1 yr stretch"
    if gap <= 3:
        return True, 0.6, "experience gap"
    return False, 0.3, "senior role"


# ---------- JD skill tiers ----------
def extract_tiers(title, description):
    """must_have (requirements) > important (title/responsibilities) > nice_to_have (preferred)."""
    desc = description or ""
    # Strip HTML tags and entities so section headings & inline requirements are clean
    clean_desc = re.sub(r"<br\s*/?>|</p>|</li>|</div>", "\n", desc, flags=re.I)
    clean_desc = re.sub(r"<[^>]+>", " ", clean_desc)
    clean_desc = html.unescape(clean_desc)

    lines = [ln.strip() for ln in clean_desc.splitlines() if ln.strip()]
    must, imp, nice = [], [], []
    section = "body"

    req_rx = re.compile(r"\b(requirements?|required|must[\s-]have|what you.ll need|qualifications?|essential|mandatory|prerequisites?|key skills?)\b", re.I)
    nice_rx = re.compile(r"\b(preferred|nice[\s-]to[\s-]have|good[\s-]to[\s-]have|\bbonus\b|\bplus\b|optional|desired)\b", re.I)
    resp_rx = re.compile(r"\b(responsib|what you.ll do|role overview|about the role|you will)\b", re.I)

    for ln in lines:
        l = ln.lower()
        new_section = None
        if req_rx.search(l) and (len(l) < 100 or ":" in ln):
            new_section = "must"
        elif nice_rx.search(l) and (len(l) < 100 or ":" in ln):
            new_section = "nice"
        elif resp_rx.search(l) and (len(l) < 100 or ":" in ln):
            new_section = "resp"

        if new_section:
            section = new_section
            if ":" in ln:
                ln = ln.split(":", 1)[1].strip()
                l = ln.lower()
                if not ln:
                    continue
            else:
                continue

        found = detect_skills(ln)
        if not found:
            continue
        if nice_rx.search(l):
            nice.extend(found)
        elif req_rx.search(l):
            must.extend(found)
        elif section == "must":
            must.extend(found)
        elif section == "nice":
            nice.extend(found)
        else:
            imp.extend(found)

    for s in detect_skills(title):
        if s not in must and s not in nice:
            imp.append(s)

    def dedup(seq):
        out = []
        for x in seq:
            if x not in out:
                out.append(x)
        return out

    tiers = {"must_have": dedup(must), "important": dedup(imp), "nice_to_have": dedup(nice)}
    for s in tiers["must_have"]:
        tiers["important"] = [x for x in tiers["important"] if x != s]
        tiers["nice_to_have"] = [x for x in tiers["nice_to_have"] if x != s]
    for s in tiers["important"]:
        tiers["nice_to_have"] = [x for x in tiers["nice_to_have"] if x != s]
    return tiers


def jd_primary_family(tiers):
    """Backend family with most must+important hits. None = frontend-only / unrecognizable JD."""
    scored = {}
    pool = tiers["must_have"] + tiers["important"]
    for fam, members in BACKEND_FAMILIES.items():
        scored[fam] = sum(1 for m in members if m in pool)
    best = max(scored, key=scored.get)
    return best if scored[best] else None


# ---------- full pipeline: discovery + score ----------
def compute_match(profile, job):
    title = job.get("title", "") or ""
    desc = job.get("description", "") or ""
    jd_text = f"{title}\n{desc}"
    resume = (profile.get("resume_text") or "").lower()
    skills = set(s.lower() for s in profile.get("skills", []))

    def has(skill):
        return skill.lower() in resume or skill.lower() in skills

    tiers = extract_tiers(title, desc)
    loc_ok, loc_reason = location_match(job.get("location", ""), profile)
    exp_req = extract_experience(jd_text)
    if exp_req is None and SENIOR_TITLE.search(title):
        exp_req = (6, None)
    exp_ok, exp_factor, exp_detail = experience_verdict(
        exp_req[0] if exp_req else None, profile.get("experience_years", 2))

    fam = jd_primary_family(tiers)
    pfams = profile_families(profile)
    my_dbs = profile_dbs(profile)

    # All backend families present in the JD (must + important)
    pool = tiers["must_have"] + tiers["important"]
    jd_fams = {fam_name for fam_name, members in BACKEND_FAMILIES.items()
               if any(m in pool for m in members)}

    total_w = sum(len(tiers[t]) * TIER_WEIGHTS[t] for t in tiers)
    title_ok = bool(ROLE_TITLE.search(title)) and not bool(NON_DEV_TITLE.search(title))
    explicit_loc = loc_reason in ("home city/state", "home state code", "remote ok", "country-level")

    if total_w == 0:
        tskills = detect_skills(title)
        matched = [s for s in tskills if has(s)]
        is_senior = bool(SENIOR_TITLE.search(title))
        exp_for_thin = not (is_senior and profile.get("experience_years", 2) < 4)
        if tskills:
            score = round(100 * len(matched) / len(tskills))
            eligible = bool(loc_ok and title_ok and exp_for_thin and score > 0)
        else:
            score = 35 if (title_ok and exp_for_thin and explicit_loc) else 0
            eligible = bool(title_ok and exp_for_thin and explicit_loc and loc_ok)
        reasons = [] if loc_ok else [f"Onsite {job.get('location', '')}".strip()]
        if not title_ok:
            reasons.append(f"Not an engineering role ({title[:60]})")
        if not exp_for_thin:
            reasons.append(f"Senior/Staff role ({title[:60]})")
        elif not eligible:
            reasons.append("No skill overlap with profile")
        return {"eligible": eligible, "match_score": score, "location_match": loc_ok,
                "location_reason": loc_reason, "experience_match": exp_for_thin,
                "experience_detail": "no JD detail" if exp_for_thin else "senior role",
                "core_stack_match": None,
                "jd_primary_stack": None, "matched_skills": matched,
                "missing_core_skills": [], "tiers": tiers,
                "rejection_reasons": reasons,
                "category": ("Possible" if score >= 35 else "Weak match") if eligible else "Filtered out"}

    matched_w = sum(TIER_WEIGHTS[t] for t in tiers for s in tiers[t] if has(s))
    matched = [s for t in tiers for s in tiers[t] if has(s)]
    missing_core = [s for s in tiers["must_have"] if not has(s)]
    must_recall = (len(tiers["must_have"]) - len(missing_core)) / max(1, len(tiers["must_have"]))
    skill_score = 100 * matched_w / total_w

    # Core stack gating:
    # 1. Incompatible Backend Families (dotnet, java, ruby, go)
    incompatible_fams = {"dotnet", "java", "ruby", "go"}
    jd_incompatible_fams = jd_fams & incompatible_fams
    jd_compatible_fams = jd_fams & pfams

    reasons = []
    core_ok = True
    fam_label = fam or "frontend/general"

    if jd_incompatible_fams:
        # If JD requires an incompatible backend family (e.g. .NET or Java) and does NOT have a profile backend alternative
        if not jd_compatible_fams or fam in incompatible_fams:
            core_ok = False
            first_incomp = sorted(jd_incompatible_fams)[0]
            pretty_incomp = {"dotnet": ".NET/C#", "java": "Java/Spring", "go": "Go", "ruby": "Ruby/Rails"}.get(first_incomp, first_incomp)
            reasons.append(f"Primary backend stack is {pretty_incomp}")
            fam_label = first_incomp
    elif fam is not None:
        if fam not in pfams:
            core_ok = False
            reasons.append(f"Primary backend stack is {fam}")
            fam_label = fam
    else:
        # No backend family detected in pool: must have frontend core match or general dev
        if not bool(set(FRONTEND_CORE) & set(matched)) and tiers["must_have"]:
            core_ok = False
            reasons.append("Missing core frontend stack (React/Next.js)")

    # 2. Incompatible Database Gate
    # If JD specifies MS SQL (or incompatible DB) and candidate does not have it
    all_jd_dbs = [d for d in pool if d in ALL_DBS]
    required_dbs = [d for d in tiers["must_have"] if d in ALL_DBS]
    if "MS SQL" in pool and "MS SQL" not in my_dbs:
        # If MS SQL is in must_have OR it's the only database in the JD
        if "MS SQL" in required_dbs or len(all_jd_dbs) == 1:
            core_ok = False
            mine = ", ".join(sorted(my_dbs)) or "none"
            reasons.append(f"Requires MS SQL; profile has {mine}")

    score = skill_score
    if tiers["must_have"] and must_recall < 0.5:
        score *= 0.5
    if total_w <= 2:
        score = min(score, 49)
    if core_ok is False:
        score = min(score, 30)  # capped strictly at 30 for incompatible stack
    score = round(score * exp_factor)

    if not loc_ok:
        if loc_reason == "foreign restricted remote":
            reasons.insert(0, f"Restricted Remote: {job.get('location', '')}".strip())
        else:
            reasons.insert(0, f"Onsite {job.get('location', '')}".strip())
    if not exp_ok or exp_factor < 1.0:
        rng = f"{exp_req[0]}–{exp_req[1]}" if exp_req and exp_req[1] else f"{exp_req[0]}+" if exp_req else "?"
        reasons.append(f"Job requires {rng} years; profile has {profile.get('experience_years', 2)} years")
    if not title_ok:
        reasons.append(f"Not an engineering role ({title[:60]})")

    eligible = bool(loc_ok and exp_ok and core_ok and title_ok)
    if eligible:
        cat = "Strong match" if score >= 60 else "Possible" if score >= 35 else "Weak match"
    else:
        cat = "Filtered out"

    return {"eligible": eligible, "match_score": score, "location_match": loc_ok,
            "location_reason": loc_reason, "experience_match": exp_ok,
            "experience_detail": exp_detail, "core_stack_match": core_ok,
            "jd_primary_stack": fam_label, "matched_skills": matched,
            "missing_core_skills": missing_core, "tiers": tiers,
            "rejection_reasons": reasons, "category": cat}


# ---------- search query builder (fetch half) ----------
def build_search_queries(profile, n=7):
    """Stack-aware queries from user profile terms & detected tech stacks.
    // ponytail: Keep queries as clean role terms without hardcoded quotes or city names.
    // Location is passed separately as location=search_loc to JobSpy/Indeed; baking
    // city into query string severely restricts Indeed results (20 drops to 4).
    """
    queries = []
    # 1. Primary explicit search terms from profile
    for t in profile.get("search_terms", []):
        t_clean = re.sub(r'["\']', '', t).strip()
        if t_clean and t_clean not in queries:
            queries.append(t_clean)

    # 2. Tech-stack specific additions from detected profile families
    fams = profile_families(profile)
    if "php" in fams:
        for php_role in ["PHP Developer", "Laravel Developer", "PHP Full Stack Developer"]:
            if php_role not in queries:
                queries.append(php_role)
    if "node" in fams:
        for node_role in ["React Developer", "Node.js Developer"]:
            if node_role not in queries:
                queries.append(node_role)
    if "python" in fams:
        if "Python Developer" not in queries:
            queries.append("Python Developer")

    # 3. Clean defaults fallback
    defaults = ["Full Stack Developer", "Web Developer", "Frontend Developer"]
    for d in defaults:
        if d not in queries:
            queries.append(d)

    return queries[:n]

