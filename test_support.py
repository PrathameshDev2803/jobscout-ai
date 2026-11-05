"""Test support utilities for JobScout codebase tests."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def app_source() -> str:
    """Concatenate app source files in fixed order for source-reading tests.

    Order:
      1. app.py
      2. Sorted *.py under ui/, core/, config/ (if they exist)
      3. Sorted assets/styles/*.css
      4. Sorted assets/js/*.js
    Precedes each file with a '# ---- <relative path> ----' marker line.
    """
    parts = []

    # 1. app.py
    app_py = ROOT / "app.py"
    if app_py.exists():
        rel = app_py.relative_to(ROOT).as_posix()
        parts.append(f"# ---- {rel} ----\n" + app_py.read_text(encoding="utf-8"))

    # 2. Sorted *.py under ui/, core/, config/
    for sub in ("ui", "core", "config"):
        sub_dir = ROOT / sub
        if sub_dir.is_dir():
            for p in sorted(sub_dir.rglob("*.py")):
                rel = p.relative_to(ROOT).as_posix()
                parts.append(f"# ---- {rel} ----\n" + p.read_text(encoding="utf-8"))

    # 3. Sorted assets/styles/*.css
    styles_dir = ROOT / "assets" / "styles"
    if styles_dir.is_dir():
        for p in sorted(styles_dir.glob("*.css")):
            rel = p.relative_to(ROOT).as_posix()
            parts.append(f"# ---- {rel} ----\n" + p.read_text(encoding="utf-8"))

    # 4. Sorted assets/js/*.js
    js_dir = ROOT / "assets" / "js"
    if js_dir.is_dir():
        for p in sorted(js_dir.glob("*.js")):
            rel = p.relative_to(ROOT).as_posix()
            parts.append(f"# ---- {rel} ----\n" + p.read_text(encoding="utf-8"))

    return "\n".join(parts)