"""Unit tests for web UI generation."""

from imbue.mngr.plugins.api_server.web_ui import generate_web_ui_html


def test_generate_web_ui_html_returns_html() -> None:
    html = generate_web_ui_html()
    assert "<!DOCTYPE html>" in html
    assert "<title>mngr</title>" in html


def test_generate_web_ui_html_has_auth_screen() -> None:
    html = generate_web_ui_html()
    assert "auth-screen" in html
    assert "token-input" in html


def test_generate_web_ui_html_has_agent_list() -> None:
    html = generate_web_ui_html()
    assert "agent-list" in html
    assert "filter-input" in html


def test_generate_web_ui_html_has_polling() -> None:
    html = generate_web_ui_html()
    assert "setInterval" in html
    assert "refreshAgents" in html


def test_generate_web_ui_html_has_mobile_viewport() -> None:
    html = generate_web_ui_html()
    assert "viewport" in html
    assert "user-scalable=no" in html
