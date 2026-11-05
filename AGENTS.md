# Rules
- **Git**: Run add/commit/push origin main ONLY when message says "push" or "deploy"; otherwise leave changes uncommitted and report. Never commit `.env`, session keys, API secrets, or private data.
- **Verification**: After editing `app.py`, run `python -m py_compile app.py` once and `git diff --stat` once. No repeated git status calls. Run unit tests (`.venv\Scripts\python.exe -m unittest`) only when requested or when logic (not markup/CSS) changes.
- **CRLF & Editing**: `app.py` uses CRLF line endings. `edit_file` fails on multi-line matches, so use single-line anchors or one scripted replace on the first attempt. Never retry `edit_file` after a whitespace failure. Do not convert line endings.
- **Investigation Limit**: For UI requests, limit investigation to 3 searches. If a stray element is not found by then, ask. Exclude `.venv`, `.git`, and `__pycache__`.
- **Execution & Scope**: Edit only files named. Changes under ~50 lines: edit directly, summarize in 3 lines. Match existing styles/tokens without adding dependencies. Avoid `<` or `&` in `python -c`. Commands >60s stop.

CSS lives in assets/styles/, loaded by ui/theme.py. Line numbers in app.py are not tracked.
