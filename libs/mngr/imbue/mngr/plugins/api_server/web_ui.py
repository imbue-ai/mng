from pathlib import Path


_WEB_UI_HTML_PATH = Path(__file__).parent / "web_ui.html"


def generate_web_ui_html() -> str:
    """Load and return the single-page mobile-first web UI HTML."""
    return _WEB_UI_HTML_PATH.read_text()
