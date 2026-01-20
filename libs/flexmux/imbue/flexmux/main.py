import json
from pathlib import Path
from typing import Final

from flask import Flask
from flask import Response
from flask import request
from flask import send_from_directory

LAYOUT_FILE: Final[Path] = Path.home() / ".flexmux" / "layout.json"

DEFAULT_INITIAL_URL: Final[str] = "https://example.com"

TERMINAL_URL: Final[str] = "http://localhost:7681"


def _get_default_layout() -> dict:
    """Return the default FlexLayout model with an initial URL tab."""
    return {
        "global": {"tabEnableClose": True, "tabEnableRename": False},
        "borders": [],
        "layout": {
            "type": "row",
            "weight": 100,
            "children": [
                {
                    "type": "tabset",
                    "weight": 100,
                    "children": [
                        {
                            "type": "tab",
                            "name": "Home",
                            "component": "url",
                            "config": {"url": DEFAULT_INITIAL_URL},
                        }
                    ],
                }
            ],
        },
    }


def _load_layout() -> dict:
    """Load layout from file or return default."""
    if LAYOUT_FILE.exists():
        try:
            raw = LAYOUT_FILE.read_text()
            return json.loads(raw)
        except (json.JSONDecodeError, OSError):
            pass
    return _get_default_layout()


def _save_layout(layout: dict) -> None:
    """Save layout to file."""
    LAYOUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    LAYOUT_FILE.write_text(json.dumps(layout, indent=2))


def create_app() -> Flask:
    """Create and configure the Flask application."""
    static_folder = Path(__file__).parent.parent.parent / "frontend" / "dist"
    app = Flask(__name__, static_folder=str(static_folder), static_url_path="")

    @app.route("/")
    def serve_index() -> Response:
        return send_from_directory(str(static_folder), "index.html")

    @app.route("/api/layout", methods=["GET"])
    def get_layout() -> Response:
        layout = _load_layout()
        return Response(json.dumps(layout), mimetype="application/json")

    @app.route("/api/layout", methods=["POST"])
    def save_layout() -> Response:
        data = request.get_json()
        if data is None:
            return Response(json.dumps({"error": "Invalid JSON"}), status=400, mimetype="application/json")
        _save_layout(data)
        return Response(json.dumps({"status": "ok"}), mimetype="application/json")

    @app.route("/api/config", methods=["GET"])
    def get_config() -> Response:
        config = {
            "terminalUrl": TERMINAL_URL,
            "defaultUrl": DEFAULT_INITIAL_URL,
        }
        return Response(json.dumps(config), mimetype="application/json")

    return app


def main() -> None:
    """Run the Flask development server."""
    app = create_app()
    app.run(host="127.0.0.1", port=5000, debug=True)


if __name__ == "__main__":
    main()
