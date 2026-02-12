"""Unit tests for auth token management."""

from pathlib import Path

from imbue.mngr.plugins.port_forwarding.auth import AUTH_COOKIE_NAME
from imbue.mngr.plugins.port_forwarding.auth import generate_auth_page_html
from imbue.mngr.plugins.port_forwarding.auth import read_or_create_auth_token


def test_read_or_create_auth_token_creates_new_token(tmp_path: Path) -> None:
    config_dir = tmp_path / "config"
    token = read_or_create_auth_token(config_dir)
    assert len(token.get_secret_value()) > 0


def test_read_or_create_auth_token_persists_to_disk(tmp_path: Path) -> None:
    config_dir = tmp_path / "config"
    token = read_or_create_auth_token(config_dir)
    token_path = config_dir / "auth_token"
    assert token_path.exists()
    assert token_path.read_text() == token.get_secret_value()


def test_read_or_create_auth_token_reuses_existing(tmp_path: Path) -> None:
    config_dir = tmp_path / "config"
    first_token = read_or_create_auth_token(config_dir)
    second_token = read_or_create_auth_token(config_dir)
    assert first_token.get_secret_value() == second_token.get_secret_value()


def test_generate_auth_page_html_contains_cookie_setting() -> None:
    html = generate_auth_page_html(
        auth_token="test-token-123",
        domain_suffix="mngr.localhost",
        vhost_port=8080,
    )
    assert AUTH_COOKIE_NAME in html
    assert "test-token-123" in html
    assert "mngr.localhost" in html
    assert "Authenticated" in html
