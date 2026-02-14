"""Unit tests for shared auth utilities."""

from pathlib import Path

from imbue.mngr.utils.auth import generate_secure_token
from imbue.mngr.utils.auth import read_or_create_token_file


def test_generate_secure_token_is_nonempty() -> None:
    token = generate_secure_token()
    assert isinstance(token, str)
    assert len(token) > 0


def test_generate_secure_token_is_unique() -> None:
    tokens = {generate_secure_token() for _ in range(10)}
    assert len(tokens) == 10


def test_read_or_create_token_file_creates_token(tmp_path: Path) -> None:
    token = read_or_create_token_file(tmp_path, "test_token")
    assert len(token.get_secret_value()) > 0


def test_read_or_create_token_file_is_idempotent(tmp_path: Path) -> None:
    first = read_or_create_token_file(tmp_path, "test_token")
    second = read_or_create_token_file(tmp_path, "test_token")
    assert first.get_secret_value() == second.get_secret_value()


def test_read_or_create_token_file_creates_directory(tmp_path: Path) -> None:
    nested_dir = tmp_path / "nested" / "dir"
    token = read_or_create_token_file(nested_dir, "test_token")
    assert len(token.get_secret_value()) > 0
    assert nested_dir.exists()


def test_read_or_create_token_file_sets_permissions(tmp_path: Path) -> None:
    read_or_create_token_file(tmp_path, "test_token")
    token_path = tmp_path / "test_token"
    assert token_path.stat().st_mode & 0o777 == 0o600


def test_read_or_create_token_file_persists_to_disk(tmp_path: Path) -> None:
    token = read_or_create_token_file(tmp_path, "test_token")
    token_path = tmp_path / "test_token"
    assert token_path.read_text() == token.get_secret_value()
