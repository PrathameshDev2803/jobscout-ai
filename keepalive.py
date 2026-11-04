"""Keepalive pinger for Streamlit Cloud free tier.

Hits the app's health endpoint on a schedule so the container stays warm
and visitors never hit a >10s cold-start spinner. Run via cron / GitHub
Actions every 10-15 minutes.
"""
import os
import sys
import time
import urllib.request
import urllib.error

APP_URL = os.environ.get("JOBSKEEPALIVE_URL", "https://jobscout-dev.streamlit.app/")
HEALTH = APP_URL.rstrip("/") + "/_stcore/health"
TIMEOUT = 20
MAX_RETRIES = 3


def ping_once():
    req = urllib.request.Request(HEALTH, headers={"User-Agent": "JobScout-keepalive/1.0"})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        return resp.status, resp.read().decode("utf-8", errors="ignore")[:200]


def main():
    last_err = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            status, body = ping_once()
            print(f"[keepalive] OK HTTP {status} {HEALTH} ({body})")
            return 0
        except urllib.error.HTTPError as e:
            last_err = f"HTTP {e.code}"
            print(f"[keepalive] attempt {attempt}/{MAX_RETRIES} {last_err} for {HEALTH}")
        except urllib.error.URLError as e:
            last_err = str(e.reason)
            print(f"[keepalive] attempt {attempt}/{MAX_RETRIES} {last_err} for {HEALTH}")
        except Exception as e:  # noqa: BLE001
            last_err = repr(e)
            print(f"[keepalive] attempt {attempt}/{MAX_RETRIES} {last_err} for {HEALTH}")
        if attempt < MAX_RETRIES:
            time.sleep(3)
    print(f"[keepalive] FAILED after {MAX_RETRIES} attempts: {last_err}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
