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

