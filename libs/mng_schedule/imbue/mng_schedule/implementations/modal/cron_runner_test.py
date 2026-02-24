"""Unit tests for the env file parser used by cron_runner."""

import os
from pathlib import Path

import pytest

from imbue.mng_schedule.implementations.modal.env_file import load_env_file


def test_load_env_file_sets_env_vars(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """load_env_file should set environment variables from a .env file."""
    env_file = tmp_path / ".env"
    env_file.write_text("MY_KEY=my_value\nOTHER_KEY=other_value\n")

    monkeypatch.delenv("MY_KEY", raising=False)
    monkeypatch.delenv("OTHER_KEY", raising=False)

    load_env_file(env_file)

    assert os.environ["MY_KEY"] == "my_value"
    assert os.environ["OTHER_KEY"] == "other_value"


def test_load_env_file_skips_comments(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """load_env_file should skip lines starting with '#'."""
    env_file = tmp_path / ".env"
    env_file.write_text("# This is a comment\nACTUAL_KEY=value\n")

    monkeypatch.delenv("ACTUAL_KEY", raising=False)

    load_env_file(env_file)

    assert os.environ["ACTUAL_KEY"] == "value"


def test_load_env_file_skips_blank_lines(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """load_env_file should skip empty and whitespace-only lines."""
    env_file = tmp_path / ".env"
    env_file.write_text("FIRST=1\n\n   \nSECOND=2\n")

    monkeypatch.delenv("FIRST", raising=False)
    monkeypatch.delenv("SECOND", raising=False)

    load_env_file(env_file)

    assert os.environ["FIRST"] == "1"
    assert os.environ["SECOND"] == "2"


def test_load_env_file_strips_export_prefix(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """load_env_file should strip the 'export ' prefix from lines."""
    env_file = tmp_path / ".env"
    env_file.write_text("export API_KEY=abc123\n")

    monkeypatch.delenv("API_KEY", raising=False)

    load_env_file(env_file)

    assert os.environ["API_KEY"] == "abc123"


def test_load_env_file_handles_values_with_equals(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """load_env_file should handle values containing '=' characters."""
    env_file = tmp_path / ".env"
    env_file.write_text("CONNECTION=postgres://user:pass@host/db?opt=1\n")

    monkeypatch.delenv("CONNECTION", raising=False)

    load_env_file(env_file)

    assert os.environ["CONNECTION"] == "postgres://user:pass@host/db?opt=1"


def test_load_env_file_noop_when_file_missing(tmp_path: Path) -> None:
    """load_env_file should do nothing when the file does not exist."""
    env_file = tmp_path / "nonexistent.env"

    load_env_file(env_file)
