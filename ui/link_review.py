"""Link review and verification module for JobScout onboarding review.

Provides:
- build_link_rows: Flatten profile links into editable tabular rows.
- apply_link_rows: Safe write-back of edited link rows into the profile data structure.
- check_link_status: Non-intrusive HEAD/GET reachability check with blocked-domain safety.
- check_all_links: Bounded batch reachability checker for up to 20 links.
- render_link_review: Interactive Streamlit UI section with data editor and link preview.
"""
import copy
import html
import os
import sys
import urllib.parse
from concurrent.futures import ThreadPoolExecutor
import requests

try:
    from core.url_utils import normalize_url, sanitize_url
except (ImportError, ModuleNotFoundError):
    _BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if _BASE not in sys.path:
        sys.path.insert(0, _BASE)
    from core.url_utils import normalize_url, sanitize_url

BLOCKED_DOMAINS = (
    "linkedin.com", "instagram.com", "facebook.com", "twitter.com", "x.com"
)


def count_link_warnings(profile: dict) -> int:
    """Count missing core slots (linkedin, github, portfolio) and unassigned/unreviewed links."""
    if not isinstance(profile, dict):
        return 0
    warnings = 0
    for slot in ("linkedin", "github", "portfolio"):
        if not str(profile.get(slot) or "").strip():
            warnings += 1
    unreviewed = profile.get("unreviewed_links") or []
    if isinstance(unreviewed, list):
        warnings += len([u for u in unreviewed if u])
    return warnings


def get_links_tab_label(profile: dict) -> str:
    """Tab label showing warning badge when unassigned links exist or core links are missing."""
    count = count_link_warnings(profile)
    if count > 0:
        return f"Links ⚠ {count}"
    return "Links"


class ApplyResult(tuple):
    """Result tuple of (updated_profile, errors) supporting dict-like access for convenience."""
    def __new__(cls, profile, errors):
        return super().__new__(cls, (profile, errors))

    @property
    def profile(self):
        return self[0]

    @property
    def errors(self):
        return self[1]

    def __getitem__(self, key):
        if isinstance(key, int):
            return super().__getitem__(key)
        return self[0][key]

    def __contains__(self, key):
        return key in self[0]

    def get(self, key, default=None):
        return self[0].get(key, default)

    def keys(self):
        return self[0].keys()

    def values(self):
        return self[0].values()

    def items(self):
        return self[0].items()


def build_link_rows(profile: dict) -> list[dict]:
    """Extract and deduplicate all profile links into editable rows.

    Includes core slots (linkedin, github, portfolio), project links (repo_url, live_url,
    extra_live_urls), other_links, and unreviewed_links with reasons.
    Missing core slots produce an empty editable row. Deduplication is done by normalize_url.
    """
    if not isinstance(profile, dict):
        profile = {}

    rows = []
    seen_norm = set()

    def _add(url: str, link_type: str, belongs_to: str, source: str, reason: str = ""):
        raw = (url or "").strip()
        if raw:
            norm = normalize_url(raw)
            if norm:
                if norm in seen_norm:
                    return
                seen_norm.add(norm)
        rows.append({
            "url": raw,
            "type": link_type,
            "belongs_to": belongs_to,
            "source": source,
            "reason": reason,
            "keep": True,
        })

    # 1. Core Profile Slots (missing slots get an empty editable row)
    for slot in ("linkedin", "github", "portfolio"):
        val = str(profile.get(slot) or "").strip()
        _add(val, slot, "Profile", "Profile slot")

    # 2. Project Links
    for prj in profile.get("projects", []) or []:
        if not isinstance(prj, dict):
            continue
        p_name = (prj.get("name") or "Project").strip()
        repo = str(prj.get("repo_url") or "").strip()
        if repo:
            _add(repo, "repo", p_name, "Project")
        live = str(prj.get("live_url") or "").strip()
        if live:
            _add(live, "live", p_name, "Project")
        for extra in prj.get("extra_live_urls", []) or []:
            extra_s = str(extra or "").strip()
            if extra_s:
                _add(extra_s, "live", p_name, "Project")

    # 3. Other Links
    for o_url in profile.get("other_links", []) or []:
        o_s = str(o_url or "").strip()
        if o_s:
            _add(o_s, "other", "Profile", "Other")

    # 4. Unreviewed / Unassigned Links (with reasons)
    for unrev in profile.get("unreviewed_links", []) or []:
        if isinstance(unrev, dict):
            u = str(unrev.get("url") or "").strip()
            reason = str(unrev.get("reason") or "unassigned").strip()
        else:
            u = str(unrev or "").strip()
            reason = "unassigned"
        if u:
            _add(u, "unassigned", "Profile", reason, reason=reason)

    return rows


def apply_link_rows(profile: dict, rows: list[dict]) -> ApplyResult:
    """Write tabular edits back to profile links and collections.

    Validates all kept non-empty URLs with sanitize_url. If any URL is invalid,
    reports the error and returns the profile UNCHANGED.
    Writes edits to linkedin/github/portfolio slots, project repos and live URLs,
    other_links, and unreviewed_links. Drops rows where keep=False.
    """
    if not isinstance(profile, dict):
        profile = {}

    errors = []
    # 1. Validation pass
    for r in (rows or []):
        if not isinstance(r, dict):
            continue
        if not r.get("keep", True):
            continue
        raw_u = str(r.get("url") or "").strip()
        if not raw_u:
            continue
        clean = sanitize_url(raw_u)
        if not clean:
            errors.append(f"Invalid URL: {raw_u}")

    if errors:
        return ApplyResult(copy.deepcopy(profile), errors)

    # 2. Rebuild profile links
    updated = copy.deepcopy(profile)
    updated["linkedin"] = ""
    updated["github"] = ""
    updated["portfolio"] = ""

    for prj in updated.get("projects", []) or []:
        if isinstance(prj, dict):
            prj["repo_url"] = ""
            prj["live_url"] = ""
            prj["extra_live_urls"] = []

    new_other_links = []
    new_unreviewed = []

    for r in (rows or []):
        if not isinstance(r, dict):
            continue
        if not r.get("keep", True):
            continue
        raw_u = str(r.get("url") or "").strip()
        if not raw_u:
            continue
        clean = sanitize_url(raw_u)
        if not clean:
            continue

        l_type = str(r.get("type") or "").strip().lower()
        belongs = str(r.get("belongs_to") or "Profile").strip()
        reason = str(r.get("reason") or r.get("source") or "unassigned").strip()

        if l_type == "linkedin":
            updated["linkedin"] = clean
        elif l_type == "github":
            updated["github"] = clean
        elif l_type == "portfolio":
            updated["portfolio"] = clean
        elif l_type in ("repo", "live") or belongs in [p.get("name") for p in updated.get("projects", []) if isinstance(p, dict) and p.get("name")]:
            target_p = next((p for p in updated.get("projects", []) if isinstance(p, dict) and p.get("name") == belongs), None)
            if target_p is not None:
                if l_type == "repo":
                    target_p["repo_url"] = clean
                else:
                    if not target_p.get("live_url"):
                        target_p["live_url"] = clean
                    elif clean != target_p["live_url"] and clean not in target_p.get("extra_live_urls", []):
                        target_p.setdefault("extra_live_urls", []).append(clean)
            else:
                if clean not in new_other_links:
                    new_other_links.append(clean)
        elif l_type == "other":
            if clean not in new_other_links:
                new_other_links.append(clean)
        elif l_type == "unassigned":
            # Check if user reassigned belongs to a project
            target_p = next((p for p in updated.get("projects", []) if isinstance(p, dict) and p.get("name") == belongs), None)
            if target_p is not None:
                # Reassigned to project
                if "github.com" in clean.lower() and not target_p.get("repo_url"):
                    target_p["repo_url"] = clean
                elif not target_p.get("live_url"):
                    target_p["live_url"] = clean
                elif clean != target_p["live_url"] and clean not in target_p.get("extra_live_urls", []):
                    target_p.setdefault("extra_live_urls", []).append(clean)
            else:
                new_unreviewed.append({"url": clean, "reason": reason})
        else:
            if clean not in new_other_links:
                new_other_links.append(clean)

    updated["other_links"] = new_other_links
    updated["unreviewed_links"] = new_unreviewed
    return ApplyResult(updated, [])


def check_link_status(url: str, timeout: float = 4.0) -> str:
    """Send HEAD request (fallback to GET) with 4s timeout to test link reachability.

    Returns:
        "OK"            : HTTP 200-399.
        "Not reachable" : Connection error, timeout, or 400-599.
        "Couldn't check": Blocked domains (e.g. linkedin.com), 403, 429, 999.
    """
    if not url or not isinstance(url, str):
        return "Not reachable"
    u = url.strip()
    if not u.startswith(("http://", "https://")):
        u = "https://" + u

    try:
        parsed = urllib.parse.urlparse(u)
        domain = (parsed.netloc or "").lower()
    except Exception:
        return "Not reachable"

    if any(domain == b or domain.endswith("." + b) for b in BLOCKED_DOMAINS):
        return "Couldn't check"

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
    }

    try:
        resp = requests.head(u, timeout=timeout, headers=headers, allow_redirects=True)
        status_code = resp.status_code
        if status_code in (405, 501):
            resp = requests.get(u, timeout=timeout, headers=headers, stream=True, allow_redirects=True)
            status_code = resp.status_code
    except (requests.exceptions.Timeout, requests.exceptions.ConnectionError):
        return "Not reachable"
    except Exception:
        return "Couldn't check"

    if 200 <= status_code < 400:
        return "OK"
    elif status_code in (403, 429, 999):
        return "Couldn't check"
    elif 400 <= status_code < 600:
        return "Not reachable"
    return "Couldn't check"


def check_all_links(urls: list[str], timeout: float = 4.0, max_links: int = 20) -> dict[str, str]:
    """Check up to max_links concurrently with small thread pool. Network-free when called with empty list."""
    target_urls = [u for u in urls if u and isinstance(u, str)][:max_links]
    if not target_urls:
        return {}
    results = {}
    with ThreadPoolExecutor(max_workers=min(5, len(target_urls))) as executor:
        future_to_url = {executor.submit(check_link_status, u, timeout): u for u in target_urls}
        for future in future_to_url:
            u = future_to_url[future]
            try:
                results[u] = future.result()
            except Exception:
                results[u] = "Couldn't check"
    return results


def render_link_review(profile: dict) -> dict:
    """Render interactive 'Verify your links' section in Streamlit onboarding review."""
    import streamlit as st

    if not isinstance(profile, dict):
        return profile

    st.markdown("""
    <div class="confirm-card">
        <h3 class="confirm-sec-title">🔗 Verify your links</h3>
        <div class="confirm-exp-sub">
            Review, edit, or reassign links extracted from your resume. Uncheck <b>Keep</b> to remove unwanted links.
        </div>
    </div>
    """, unsafe_allow_html=True)

    # Initialize or fetch rows from session state
    cached_rows = st.session_state.get("link_review_rows")
    if not cached_rows or st.session_state.get("_link_review_profile_hash") != id(profile):
        cached_rows = build_link_rows(profile)
        st.session_state["link_review_rows"] = cached_rows
        st.session_state["_link_review_profile_hash"] = id(profile)

    # 1. Unassigned warning banner
    unassigned = [r for r in cached_rows if r.get("type") == "unassigned" and r.get("url") and r.get("keep", True)]
    if unassigned:
        bullet_lines = "\n".join(f"• `{r['url']}` — *Reason: {r.get('reason') or 'unassigned'}*" for r in unassigned)
        st.warning(
            f"⚠️ **Unassigned links detected:**\n\n{bullet_lines}\n\n"
            "Assign them to a project or slot below, or uncheck **Keep** to discard."
        )

    # 2. Check links button & status resolution
    chk_col, info_col = st.columns([1, 2.5], vertical_alignment="center")
    with chk_col:
        check_clicked = st.button("🔍 Check links", key="btn_check_links", help="Send HEAD request (4s timeout) to verify link reachability")
    with info_col:
        if st.session_state.get("link_status_summary"):
            st.caption(st.session_state["link_status_summary"])

    if check_clicked:
        kept_urls = [r["url"] for r in cached_rows if r.get("url") and r.get("keep", True)][:20]
        if kept_urls:
            with st.spinner(f"Checking {len(kept_urls)} links..."):
                statuses = check_all_links(kept_urls)
                st.session_state["link_statuses"] = statuses
                ok_count = sum(1 for s in statuses.values() if s == "OK")
                dead_count = sum(1 for s in statuses.values() if s == "Not reachable")
                skip_count = sum(1 for s in statuses.values() if s == "Couldn't check")
                st.session_state["link_status_summary"] = (
                    f"Result: {ok_count} OK · {dead_count} Not reachable · {skip_count} Couldn't check"
                )
                st.rerun()

    # Add status column to rows if check was executed
    display_rows = []
    link_statuses = st.session_state.get("link_statuses", {})
    for r in cached_rows:
        row_copy = dict(r)
        if link_statuses and r.get("url"):
            row_copy["status"] = link_statuses.get(r["url"], "—")
        else:
            row_copy["status"] = "—"
        display_rows.append(row_copy)

    type_options = ["linkedin", "github", "portfolio", "repo", "live", "other", "unassigned"]
    project_names = [p.get("name") for p in profile.get("projects", []) if isinstance(p, dict) and p.get("name")]
    belongs_options = ["Profile"] + project_names

    col_config = {
        "url": st.column_config.TextColumn("Link", help="Destination URL", width="large"),
        "type": st.column_config.SelectboxColumn("Type", options=type_options, required=True, width="medium"),
        "belongs_to": st.column_config.SelectboxColumn("Belongs to", options=belongs_options, required=True, width="medium"),
        "source": st.column_config.TextColumn("Source", disabled=True, width="medium"),
        "status": st.column_config.TextColumn("Status", disabled=True, width="small"),
        "keep": st.column_config.CheckboxColumn("Keep", default=True, width="small"),
    }

    # Hide reason internal key in editor
    editor_input = [{k: v for k, v in dr.items() if k != "reason"} for dr in display_rows]

    edited_rows = st.data_editor(
        editor_input,
        column_config=col_config,
        disabled=["source", "status"],
        use_container_width=True,
        key="data_editor_link_review",
        num_rows="dynamic"
    )

    # Re-attach reason from cached_rows
    cleaned_edited = []
    for idx, er in enumerate(edited_rows):
        orig_reason = cached_rows[idx].get("reason", "") if idx < len(cached_rows) else ""
        er["reason"] = orig_reason
        cleaned_edited.append(er)
    st.session_state["link_review_rows"] = cleaned_edited

    updated_profile, errors = apply_link_rows(profile, cleaned_edited)
    if errors:
        for err in errors:
            st.error(f"⚠️ {err}")

    # 3. Clickable Link List preview under the table
    st.markdown("<div class='confirm-exp-sub' style='margin-top: 10px;'><b>Clickable Links (open in new tab):</b></div>", unsafe_allow_html=True)
    link_html = []
    for r in cleaned_edited:
        u = str(r.get("url") or "").strip()
        if u and r.get("keep", True):
            t_label = str(r.get("type") or "Link").upper()
            b_label = str(r.get("belongs_to") or "Profile")
            clean_url = sanitize_url(u) or u
            link_html.append(
                f"<div style='margin-bottom: 4px;'>"
                f"<span class='chip' style='margin-right: 6px;'>{html.escape(t_label)}</span> "
                f"<a href='{html.escape(clean_url)}' target='_blank' rel='noopener noreferrer' style='color: #10b981; text-decoration: underline;'>"
                f"{html.escape(clean_url)}</a> "
                f"<span style='color: #94a3b8; font-size: 12px;'>({html.escape(b_label)})</span>"
                f"</div>"
            )
    if link_html:
        st.markdown(f"<div class='confirm-card'>{''.join(link_html)}</div>", unsafe_allow_html=True)
    else:
        st.caption("No active links selected.")

    return updated_profile
