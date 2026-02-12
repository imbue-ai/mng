"""Unit tests for api_server auth."""

from pathlib import Path

from imbue.mngr.plugins.api_server.auth import read_or_create_api_token


def test_read_or_create_api_token_creates_token(tmp_path: Path) -> None:
    token = read_or_create_api_token(tmp_path)
    assert len(token.get_secret_value()) > 0


def test_read_or_create_api_token_is_idempotent(tmp_path: Path) -> None:
    token1 = read_or_create_api_token(tmp_path)
    token2 = read_or_create_api_token(tmp_path)
    assert token1.get_secret_value() == token2.get_secret_value()


def test_read_or_create_api_token_creates_directory(tmp_path: Path) -> None:
    nested_dir = tmp_path / "nested" / "dir"
    token = read_or_create_api_token(nested_dir)
    assert len(token.get_secret_value()) > 0
    assert nested_dir.exists()
