# AGENTS.md — JobScout (project-specific)

Global rules already apply (modes, budgets, verification ladder, safety). This file adds only what is specific to JobScout.

## Stack and commands

- Streamlit app, Python 3.10, Windows, `.venv`. Use `.venv\Scripts\python`.
- Dev server: `http://localhost:8501`. Reuse it if it is already running.
- Tier 0: `python -m py_compile <changed .py files>`
- Tier 1: `python -m unittest test_<module> -v` (only the module covering the change)
- Tier 3: `python -m unittest discover`. Baseline: 146 tests, 1 skip (`python-jobspy` not installed). Any new failure must be explained.

## Project map (update after each restructure step)

- `app.py` — main app, still large (≈6,400 lines). Never open whole; search, then read ±40 lines.
- `assets/styles/` — 9 CSS files extracted from the old inline string. All styling changes go here.
- `assets/js/` — 3 JS files.
- `ui/theme.py` — loads CSS/JS assets.
- `test_support.py` — `app_source()` helper used by tests.
- `test_*.py` (repo root) — unittest suite.
- `core/resume/` — planned home for pure resume-parsing code (in progress).

## Protected — do not modify unless the task says so

- Upload processing, file validation, 200MB limit, accepted formats (PDF, DOCX, TXT)
- Session state keys and logic; widget `key=` values and call order
- Resume parsing, profile load/save, backend processing
- Gemini integration and the privacy disclaimer text
- Existing remove-file handler

## Streamlit rules

- Native widgets (e.g. `st.file_uploader`) can't be conditionally removed without resetting state. Prefer restyling with CSS (`[data-testid="..."]`, `:has()`) over replacing the widget.
- Don't rely on `.st-emotion-cache-*` class names. Use `data-testid` or stable wrappers.
- Assume a rerun on every interaction; don't add heavy work to the main script path.
- No new large inline CSS/JS strings in `app.py`.

## Design

- Dark theme with green accents. Reuse the existing CSS variables/tokens.
- Visual checks (Tier 2): 320px and 1440px, empty → filled → remove → empty restored.
