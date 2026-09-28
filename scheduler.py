"""Background job scheduler: automatically fetches latest jobs every 15 minutes.
Thread-safe singleton for Streamlit and CLI environments.
"""
import json
import os
import threading
import time
from datetime import datetime, timezone

from fetch import run_fetch_pipeline

STATUS_FILE = os.path.join(os.path.dirname(__file__), "scheduler_status.json")

_lock = threading.Lock()
_scheduler_thread = None
_stop_event = threading.Event()

# Default configuration
DEFAULT_INTERVAL_SECONDS = 15 * 60  # 15 minutes


def _read_status_from_disk():
    if os.path.exists(STATUS_FILE):
        try:
            with open(STATUS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {
        "enabled": True,
        "is_fetching": False,
        "last_run": None,
        "next_run": None,
        "interval_seconds": DEFAULT_INTERVAL_SECONDS,
        "last_result": None,
        "run_count": 0,
    }


def _write_status_to_disk(status):
    try:
        with open(STATUS_FILE, "w", encoding="utf-8") as f:
            json.dump(status, f, indent=2)
    except Exception as e:
        print(f"Error saving scheduler status: {e}")


def get_scheduler_status():
    """Retrieve current scheduler state and stats."""
    with _lock:
        return _read_status_from_disk()


def set_scheduler_enabled(enabled: bool):
    """Enable or disable periodic 15-minute background auto-fetching."""
    with _lock:
        st = _read_status_from_disk()
        st["enabled"] = enabled
        now = time.time()
        if enabled:
            st["next_run"] = now + st.get("interval_seconds", DEFAULT_INTERVAL_SECONDS)
        else:
            st["next_run"] = None
        _write_status_to_disk(st)
        return st


def _execute_fetch_task(include_jobspy=True, max_spy_wanted=20):
    """Worker task executing pipeline with status updates."""
    with _lock:
        st = _read_status_from_disk()
        if st.get("is_fetching"):
            print("Scheduler: Fetch already in progress, skipping.")
            return None
        st["is_fetching"] = True
        _write_status_to_disk(st)

    print(f"[{datetime.now().strftime('%H:%M:%S')}] Starting 15-minute job fetch pipeline...")
    result = None
    try:
        result = run_fetch_pipeline(include_jobspy=include_jobspy, max_spy_wanted=max_spy_wanted)
    except Exception as err:
        print(f"Scheduler execution error: {err}")
        result = {"status": "error", "message": str(err), "new_rows": 0, "total_fetched": 0}
    finally:
        with _lock:
            st = _read_status_from_disk()
            now = time.time()
            st["is_fetching"] = False
            st["last_run"] = datetime.now(timezone.utc).isoformat()
            st["last_result"] = result
            st["run_count"] = st.get("run_count", 0) + 1
            if st.get("enabled", True):
                st["next_run"] = now + st.get("interval_seconds", DEFAULT_INTERVAL_SECONDS)
            else:
                st["next_run"] = None
            _write_status_to_disk(st)

    print(f"[{datetime.now().strftime('%H:%M:%S')}] Fetch pipeline finished. Result: {result}")
    return result


def trigger_immediate_fetch(include_jobspy=True, max_spy_wanted=20):
    """Manually trigger a fetch right now."""
    return _execute_fetch_task(include_jobspy=include_jobspy, max_spy_wanted=max_spy_wanted)


def _scheduler_loop(interval_seconds):
    """Background loop that ticks and checks if 15 minutes have passed."""
    print(f"Scheduler daemon started. Interval: {interval_seconds // 60} minutes.")
    while not _stop_event.is_set():
        try:
            status = get_scheduler_status()
            now = time.time()

            if status.get("enabled", True) and not status.get("is_fetching", False):
                next_run = status.get("next_run")
                if next_run is None or now >= next_run:
                    # Run scheduled fetch
                    _execute_fetch_task(include_jobspy=True, max_spy_wanted=15)

        except Exception as e:
            print(f"Scheduler loop error: {e}")

        # Sleep in small slices so thread responds quickly to shutdown
        _stop_event.wait(timeout=5)


def start_background_scheduler(interval_minutes=15):
    """Start the singleton background worker thread if not already running."""
    global _scheduler_thread

    with _lock:
        if _scheduler_thread is not None and _scheduler_thread.is_alive():
            return _scheduler_thread

        interval_seconds = interval_minutes * 60
        st = _read_status_from_disk()
        st["interval_seconds"] = interval_seconds
        st["enabled"] = True
        if st.get("next_run") is None:
            # First run in 15 minutes or immediately if never run
            if not st.get("last_run"):
                st["next_run"] = time.time() + 10  # Run shortly after boot
            else:
                st["next_run"] = time.time() + interval_seconds
        _write_status_to_disk(st)

        _stop_event.clear()
        _scheduler_thread = threading.Thread(
            target=_scheduler_loop,
            args=(interval_seconds,),
            daemon=True,
            name="JobScraperScheduler"
        )
        _scheduler_thread.start()
        return _scheduler_thread
