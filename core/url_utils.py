"""URL utility functions extracted from app.py."""
import re
import urllib.parse


def unwrap_text_urls(text: str) -> str:
    """Fix URLs broken across line breaks in PDF column layouts."""
    if not text:
        return ""
    # Pattern 1: URL ending with hyphen broken across lines (e.g., https://.../foo-\nbar)
    text = re.sub(r'((?:https?://|www\.|[a-zA-Z0-9_\-\.]+\.(?:com|in|io|dev|me|app)/)[^\s\n]*)-\s*\n\s*([a-zA-Z0-9_\-\./]+)', r'\1\2', text)
    # Pattern 2: URL ending with slash broken across line (e.g., https://linkedin.com/in/\nusername or github.com/\nuser)
    text = re.sub(r'((?:https?://|www\.|(?:linkedin\.com/in|github\.com)/)[^\s\n]*?/\s*)\n\s*([a-zA-Z0-9_\-]+)', r'\1\2', text)
    # Pattern 3: Domain broken across dot (e.g., https://github.\ncom/user)
    text = re.sub(r'((?:https?://|www\.)[a-zA-Z0-9_\-]+\.\s*)\n\s*([a-zA-Z0-9_\-\./]+)', r'\1\2', text)
    return text



def sanitize_url(raw_url: str) -> str | None:
    """Sanitize and validate extracted URL. Rejects dangerous schemes and prompt injection."""
    if not raw_url or not isinstance(raw_url, str):
        return None
    url = raw_url.strip()
    # Strip quotes, brackets, angle brackets, commas, trailing punctuation
    url = re.sub(r'^[\s"\'\(<\[]+|[\s"\'\)>\]\,\.]+$', '', url)

    # Reject dangerous schemes and control chars
    if any(ctrl in url for ctrl in ['\r', '\n', '\t', '\0', '`', '<', '>']):
        return None
    low = url.lower()
    if any(low.startswith(bad) for bad in ['javascript:', 'data:', 'file:', 'vbscript:', 'blob:', 'mailto:']):
        return None
    if len(url) > 250:
        return None

    # Auto-prepend https:// if missing
    if not (low.startswith("http://") or low.startswith("https://")):
        if re.match(r'^(?:[a-zA-Z0-9_\-]+\.)+[a-zA-Z]{2,}(?:/.*)?$', url):
            url = f"https://{url}"
        else:
            return None

    try:
        parsed = urllib.parse.urlparse(url)
        if parsed.scheme not in ('http', 'https'):
            return None
        netloc = parsed.netloc.lower()
        if not netloc or "." not in netloc or "localhost" in netloc or netloc.startswith("127."):
            return None

        # Clean tracking query parameters
        cleaned_query = []
        if parsed.query:
            qs = urllib.parse.parse_qsl(parsed.query, keep_blank_values=False)
            for k, v in qs:
                k_low = k.lower()
                if not any(k_low.startswith(prefix) for prefix in ['utm_', 'trk', 'ref', 'source', 'locale', 'fbclid', 'gclid']):
                    cleaned_query.append((k, v))
        new_query = urllib.parse.urlencode(cleaned_query)
        path = parsed.path.rstrip('/')

        clean_url = urllib.parse.urlunparse((
            parsed.scheme,
            parsed.netloc,
            path,
            parsed.params,
            new_query,
            ''
        ))
        return clean_url
    except Exception:
        return None


_GH_RESERVED = {
    "features", "pricing", "pulls", "issues", "explore", "settings",
    "topics", "marketplace", "orgs", "sponsors", "collections", "events",
    "discussions", "enterprise", "mobile", "search", "about", "security",
    "contact", "site", "blog", "developers"
}

EXCLUDED_PORTFOLIO_DOMAINS = {
    "github.com", "linkedin.com", "indeed.com", "naukri.com", "glassdoor.com",
    "wellfound.com", "angel.co", "hiring.cafe", "google.com", "facebook.com",
    "twitter.com", "x.com", "instagram.com", "youtube.com", "medium.com",
    "dev.to", "hashnode.dev", "hashnode.com", "substack.com", "notion.site",
    "notion.so", "drive.google.com", "docs.google.com", "dropbox.com",
    "leetcode.com", "hackerrank.com", "codechef.com", "codeforces.com",
    "geeksforgeeks.org", "coursera.org", "udemy.com", "edx.org",
    "w3schools.com", "stackoverflow.com", "gitlab.com", "bitbucket.org",
    "npm.js", "npmjs.com", "pypi.org", "packagist.org", "docker.com",
    "react.dev", "vuejs.org", "angular.io", "nextjs.org", "nodejs.org",
    "python.org", "php.net", "laravel.com", "tailwindcss.com",
    "streamlit.app", "streamlit.io", "whatsapp.com", "t.me", "telegram.org"
}


def normalize_url(raw_url: str) -> str:
    """Normalize URL for grounding comparison: lowercase host, strip 'www.', strip trailing slash, ignore scheme."""
    if not raw_url or not isinstance(raw_url, str):
        return ""
    clean = sanitize_url(raw_url)
    u = (clean or raw_url).strip()
    u = re.sub(r'^[\s"\'\(<\[]+|[\s"\'\)>\]\,\.]+$', '', u)
    if not u:
        return ""
    if not re.match(r"^[a-zA-Z][a-zA-Z0-9+\-.]*://", u):
        u = "https://" + u
    try:
        parsed = urllib.parse.urlparse(u)
        host = (parsed.netloc or "").lower()
        if host.startswith("www."):
            host = host[4:]
        path = (parsed.path or "").rstrip("/").lower()
        query = (parsed.query or "").lower()
        if query:
            return f"{host}{path}?{query}"
        return f"{host}{path}"
    except Exception:
        return ""


def is_valid_slot_shape(slot: str, url: str) -> bool:
    """Validate per-slot URL shape using existing classification regexes."""
    if not url or not isinstance(url, str):
        return False
    s_slot = (slot or "").strip().lower()
    if s_slot == "linkedin":
        m = re.search(r"linkedin\.com/in/([a-zA-Z0-9_\-\.]+)", url, re.I)
        if not m:
            return False
        handle = m.group(1).strip("/")
        return bool(handle)
    elif s_slot == "github":
        if "github.io" in url.lower():
            return False
        m = re.search(r"github\.com/([a-zA-Z0-9_\-]+)(?:/([a-zA-Z0-9_\-\.]+))?/?(?:[?#].*)?$", url, re.I)
        if not m:
            return False
        owner, repo = m.group(1), m.group(2)
        if owner.lower() in _GH_RESERVED:
            return False
        if repo:
            return False
        return bool(owner)
    elif s_slot == "portfolio":
        try:
            u = url if "://" in url else "https://" + url
            parsed = urllib.parse.urlparse(u)
            domain = (parsed.netloc or "").lower()
            if domain.startswith("www."):
                domain = domain[4:]
            if any(domain == exc or domain.endswith("." + exc) for exc in EXCLUDED_PORTFOLIO_DOMAINS):
                if not (domain.endswith(".github.io") and domain != "github.io"):
                    return False
            if any(ext in domain for ext in [".edu", ".ac.in", ".gov.", ".gov"]):
                return False
            return True
        except Exception:
            return False
    return True


def is_url_grounded(url: str, verified_links: list | None = None, resume_text: str = "", slot: str | None = None) -> bool:
    """Check if an LLM-returned URL is grounded in verified links or resume text."""
    if not url or not isinstance(url, str):
        return False
    clean = sanitize_url(url)
    if not clean:
        return False
    if slot and not is_valid_slot_shape(slot, clean):
        return False
    norm_target = normalize_url(clean)
    if not norm_target:
        return False

    # Check (a): verified_links pool
    if verified_links:
        for vl in verified_links:
            if vl and normalize_url(vl) == norm_target:
                return True

    # Check (b): resume text
    if resume_text and isinstance(resume_text, str):
        unwrapped = unwrap_text_urls(resume_text)
        url_patterns = [
            r"(?:https?:\/\/)?(?:www\.)?linkedin\.com\/in\/[a-zA-Z0-9_\-\.\/]+",
            r"(?:https?:\/\/)?(?:www\.)?github\.com\/[a-zA-Z0-9_\-]+(?:\/[a-zA-Z0-9_\-\.]+)?",
            r"(?:https?:\/\/)?(?:www\.)?[a-zA-Z0-9_\-]+\.(?:github\.io|vercel\.app|netlify\.app|pages\.dev|web\.app|firebaseapp\.com|dev|me|tech|site|bio)(?:\/[^\s\)\],<]*)?",
            r"https?:\/\/[a-zA-Z0-9_\-\.]+\.[a-zA-Z]{2,}(?:\/[^\s\)\],<]*)?",
        ]
        for pat in url_patterns:
            for match in re.findall(pat, unwrapped, re.I):
                if normalize_url(match) == norm_target:
                    return True

        pattern = rf"(?i)(?<![a-zA-Z0-9_\-])(?:https?://)?(?:www\.)?{re.escape(norm_target)}(?:/(?![a-zA-Z0-9_\-\.])|(?![a-zA-Z0-9_\-\.]))"
        if re.search(pattern, unwrapped):
            return True

    return False


