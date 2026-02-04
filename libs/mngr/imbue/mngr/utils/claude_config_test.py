"""Unit tests for claude_config.py."""

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from imbue.mngr.errors import ClaudeDirectoryNotTrustedError
from imbue.mngr.utils.claude_config import _find_project_config
from imbue.mngr.utils.claude_config import check_source_directory_trusted
from imbue.mngr.utils.claude_config import get_claude_config_path


def test_get_claude_config_path_returns_home_dot_claude_json() -> None:
    """Test that get_claude_config_path returns ~/.claude.json."""
    result = get_claude_config_path()
    assert result == Path.home() / ".claude.json"


def test_find_project_config_exact_match() -> None:
    """Test that _find_project_config finds exact match."""
    projects = {
        "/Users/test/project1": {"allowedTools": ["bash"], "hasTrustDialogAccepted": True},
        "/Users/test/project2": {"allowedTools": [], "hasTrustDialogAccepted": False},
    }
    result = _find_project_config(projects, Path("/Users/test/project1"))
    assert result == {"allowedTools": ["bash"], "hasTrustDialogAccepted": True}


def test_find_project_config_ancestor_match() -> None:
    """Test that _find_project_config finds closest ancestor."""
    projects = {
        "/Users/test/project": {"allowedTools": ["bash"], "hasTrustDialogAccepted": True},
    }
    # Search for a subdirectory
    result = _find_project_config(projects, Path("/Users/test/project/src/components"))
    assert result == {"allowedTools": ["bash"], "hasTrustDialogAccepted": True}


def test_find_project_config_no_match() -> None:
    """Test that _find_project_config returns None when no match."""
    projects = {
        "/Users/test/project1": {"allowedTools": ["bash"], "hasTrustDialogAccepted": True},
    }
    result = _find_project_config(projects, Path("/Users/other/project"))
    assert result is None


def test_find_project_config_empty_projects() -> None:
    """Test that _find_project_config returns None for empty projects."""
    result = _find_project_config({}, Path("/Users/test/project"))
    assert result is None


def test_check_source_directory_trusted_succeeds_when_trusted(tmp_path: Path) -> None:
    """Test that check_source_directory_trusted passes when directory is trusted."""
    config_file = tmp_path / ".claude.json"
    source_path = tmp_path / "source"
    source_path.mkdir()

    # Create config with trusted source
    config = {
        "projects": {
            str(source_path): {"allowedTools": ["bash"], "hasTrustDialogAccepted": True},
        }
    }
    config_file.write_text(json.dumps(config, indent=2))

    with patch("imbue.mngr.utils.claude_config.get_claude_config_path", return_value=config_file):
        # Should not raise
        check_source_directory_trusted(source_path)


def test_check_source_directory_trusted_succeeds_for_subdirectory(tmp_path: Path) -> None:
    """Test that check_source_directory_trusted passes for subdirectory of trusted path."""
    config_file = tmp_path / ".claude.json"
    project_root = tmp_path / "project"
    source_path = project_root / "src" / "components"
    project_root.mkdir()
    source_path.mkdir(parents=True)

    # Create config with trusted project root
    config = {
        "projects": {
            str(project_root): {"allowedTools": ["bash"], "hasTrustDialogAccepted": True},
        }
    }
    config_file.write_text(json.dumps(config, indent=2))

    with patch("imbue.mngr.utils.claude_config.get_claude_config_path", return_value=config_file):
        # Should not raise - subdirectory inherits trust from ancestor
        check_source_directory_trusted(source_path)


def test_check_source_directory_trusted_raises_when_not_trusted(tmp_path: Path) -> None:
    """Test that check_source_directory_trusted raises when hasTrustDialogAccepted=false."""
    config_file = tmp_path / ".claude.json"
    source_path = tmp_path / "source"
    source_path.mkdir()

    # Create config with hasTrustDialogAccepted=False
    config = {
        "projects": {
            str(source_path): {"allowedTools": ["bash"], "hasTrustDialogAccepted": False},
        }
    }
    config_file.write_text(json.dumps(config, indent=2))

    with patch("imbue.mngr.utils.claude_config.get_claude_config_path", return_value=config_file):
        with pytest.raises(ClaudeDirectoryNotTrustedError) as exc_info:
            check_source_directory_trusted(source_path)

    assert str(source_path) in str(exc_info.value)


def test_check_source_directory_trusted_raises_when_no_config_file(tmp_path: Path) -> None:
    """Test that check_source_directory_trusted raises when ~/.claude.json doesn't exist."""
    config_file = tmp_path / ".claude.json"
    source_path = tmp_path / "source"
    source_path.mkdir()

    # Don't create the config file

    with patch("imbue.mngr.utils.claude_config.get_claude_config_path", return_value=config_file):
        with pytest.raises(ClaudeDirectoryNotTrustedError):
            check_source_directory_trusted(source_path)


def test_check_source_directory_trusted_raises_when_empty_config(tmp_path: Path) -> None:
    """Test that check_source_directory_trusted raises when config file is empty."""
    config_file = tmp_path / ".claude.json"
    source_path = tmp_path / "source"
    source_path.mkdir()

    # Create empty config file
    config_file.write_text("")

    with patch("imbue.mngr.utils.claude_config.get_claude_config_path", return_value=config_file):
        with pytest.raises(ClaudeDirectoryNotTrustedError):
            check_source_directory_trusted(source_path)


def test_check_source_directory_trusted_raises_when_not_in_projects(tmp_path: Path) -> None:
    """Test that check_source_directory_trusted raises when source not in projects."""
    config_file = tmp_path / ".claude.json"
    source_path = tmp_path / "source"
    source_path.mkdir()

    # Create config without the source project
    config = {"projects": {"/other/project": {"allowedTools": [], "hasTrustDialogAccepted": True}}}
    config_file.write_text(json.dumps(config, indent=2))

    with patch("imbue.mngr.utils.claude_config.get_claude_config_path", return_value=config_file):
        with pytest.raises(ClaudeDirectoryNotTrustedError):
            check_source_directory_trusted(source_path)


def test_check_source_directory_trusted_raises_when_trust_field_missing(tmp_path: Path) -> None:
    """Test that check_source_directory_trusted raises when hasTrustDialogAccepted is missing."""
    config_file = tmp_path / ".claude.json"
    source_path = tmp_path / "source"
    source_path.mkdir()

    # Create config without hasTrustDialogAccepted field
    config = {
        "projects": {
            str(source_path): {"allowedTools": ["bash"]},
        }
    }
    config_file.write_text(json.dumps(config, indent=2))

    with patch("imbue.mngr.utils.claude_config.get_claude_config_path", return_value=config_file):
        with pytest.raises(ClaudeDirectoryNotTrustedError):
            check_source_directory_trusted(source_path)


def test_check_source_directory_trusted_handles_invalid_json(tmp_path: Path) -> None:
    """Test that check_source_directory_trusted raises for invalid JSON."""
    config_file = tmp_path / ".claude.json"
    source_path = tmp_path / "source"
    source_path.mkdir()

    # Create invalid JSON
    config_file.write_text("{ invalid json }")

    with patch("imbue.mngr.utils.claude_config.get_claude_config_path", return_value=config_file):
        with pytest.raises(ClaudeDirectoryNotTrustedError):
            check_source_directory_trusted(source_path)
