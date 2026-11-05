"""Theme and stylesheet asset loader."""
from pathlib import Path


def load_css() -> str:
    """Load and concatenate all stylesheet assets in alphabetical cascade order."""
    styles_dir = Path(__file__).resolve().parent.parent / "assets" / "styles"
    css_files = sorted(styles_dir.glob("*.css"))
    parts = []
    for f in css_files:
        with open(f, "r", encoding="utf-8") as fp:
            parts.append(fp.read())
    return "\n<style>\n" + "".join(parts) + "</style>\n"
