"""
Streamlit Community Cloud Keep-Alive Script.
Launches headless browser via Playwright, navigates to live app,
and automatically clicks the 'Wake up' button if hibernated.
"""
import os
import sys
from datetime import datetime, timezone
from playwright.sync_api import sync_playwright

DEFAULT_APP_URL = "https://jobscout-dev.streamlit.app/"
APP_URL = os.environ.get("STREAMLIT_APP_URL", DEFAULT_APP_URL).strip()

def keep_alive():
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    print(f"[{timestamp}] Starting keep-alive ping for: {APP_URL}")

    with sync_playwright() as p:
        # Launch Chromium with realistic viewport and user-agent
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 800}
        )
        page = context.new_page()

        try:
            print(f"[{timestamp}] Navigating to {APP_URL}...")
            page.goto(APP_URL, timeout=60000, wait_until="networkidle")
            page.wait_for_timeout(5000)

            # Check if sleeping screen is displayed
            wake_button = page.get_by_role("button", name="Yes, get this app back up!")
            if wake_button.is_visible(timeout=3000):
                print(f"[{timestamp}] Sleeping screen detected! Clicking 'Yes, get this app back up!'...")
                wake_button.click()
                # Give it 15 seconds to spin up the container
                page.wait_for_timeout(15000)
                print(f"[{timestamp}] Wake up button clicked successfully.")
            else:
                print(f"[{timestamp}] App is already awake and responsive.")

            print(f"[{timestamp}] Keep-alive check completed.")
        except Exception as err:
            print(f"[{timestamp}] Warning or error during ping: {err}")
            # Ensure browser closes before re-raising
            browser.close()
            sys.exit(1)
        finally:
            browser.close()

if __name__ == "__main__":
    keep_alive()
