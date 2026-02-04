"""Unit tests for claude_config.py."""

import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from imbue.mngr.errors import ClaudeDirectoryNotTrustedError
from imbue.mngr.errors import ClaudeTrustNotFoundError
from imbue.mngr.utils.claude_config import _find_project_config
from imbue.mngr.utils.claude_config import extend_claude_trust_to_worktree
from imbue.mngr.utils.claude_config import get_claude_config_backup_path
from imbue.mngr.utils.claude_config import get_claude_config_path


def test_get_claude_config_path_returns_home_dot_claude_json() -> None:
    """Test that get_claude_config_path returns ~/.claude.json."""
    result = get_claude_config_path()
    assert result == Path.home() / ".claude.json"


def test_get_claude_config_backup_path_returns_home_dot_claude_json_bak() -> None:
    """Test that get_claude_config_backup_path returns ~/.claude.json.bak."""
    result = get_claude_config_backup_path()
    assert result == Path.home() / ".claude.json.bak"


def test_find_project_config_exact_match() -> None:
    """Test that _find_project_config finds exact match."""
    projects = {
        "/Users/test/project1": {"allowedTools": ["bash"], "hasTrustDialogAccepted": True},
        "/Users/test/project2": {"allowedTools": [], "hasTrustDialogAccepted": False},
    }
    result = _find_project_config(projects, Path("/Users/test/project1"))
    assert result is not None
    assert result.allowedTools == ["bash"]
    assert result.hasTrustDialogAccepted is True


def test_find_project_config_ancestor_match() -> None:
    """Test that _find_project_config finds closest ancestor."""
    projects = {
        "/Users/test/project": {"allowedTools": ["bash"], "hasTrustDialogAccepted": True},
    }
    # Search for a subdirectory
    result = _find_project_config(projects, Path("/Users/test/project/src/components"))
    assert result is not None
    assert result.allowedTools == ["bash"]
    assert result.hasTrustDialogAccepted is True


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


def test_extend_claude_trust_to_worktree_creates_entry(tmp_path: Path) -> None:
    """Test that extend_claude_trust_to_worktree copies config to target path."""
    config_file = tmp_path / ".claude.json"
    source_path = tmp_path / "source"
    target_path = tmp_path / "target"
    source_path.mkdir()
    target_path.mkdir()

    # Create initial config
    config = {
        "projects": {
            str(source_path): {"allowedTools": ["bash", "edit"], "hasTrustDialogAccepted": True},
        }
    }
    config_file.write_text(json.dumps(config, indent=2))

    with patch("imbue.mngr.utils.claude_config.get_claude_config_path", return_value=config_file):
        extend_claude_trust_to_worktree(source_path, target_path)

    # Read the updated config
    updated_config = json.loads(config_file.read_text())
    assert str(target_path) in updated_config["projects"]
    assert updated_config["projects"][str(target_path)] == {
        "allowedTools": ["bash", "edit"],
        "hasTrustDialogAccepted": True,
    }
    # Original entry should still exist
    assert str(source_path) in updated_config["projects"]


def test_extend_claude_trust_to_worktree_creates_backup(tmp_path: Path) -> None:
    """Test that extend_claude_trust_to_worktree creates a backup before modifying."""
    config_file = tmp_path / ".claude.json"
    backup_file = tmp_path / ".claude.json.bak"
    source_path = tmp_path / "source"
    target_path = tmp_path / "target"
    source_path.mkdir()
    target_path.mkdir()

    # Create initial config
    config = {
        "projects": {
            str(source_path): {"allowedTools": ["bash"], "hasTrustDialogAccepted": True},
        }
    }
    original_content = json.dumps(config, indent=2)
    config_file.write_text(original_content)

    with patch("imbue.mngr.utils.claude_config.get_claude_config_path", return_value=config_file):
        with patch("imbue.mngr.utils.claude_config.get_claude_config_backup_path", return_value=backup_file):
            extend_claude_trust_to_worktree(source_path, target_path)

    # Backup should exist with original content
    assert backup_file.exists()
    assert backup_file.read_text() == original_content


def test_extend_claude_trust_to_worktree_no_backup_when_no_change(tmp_path: Path) -> None:
    """Test that no backup is created when target already exists (no modification)."""
    config_file = tmp_path / ".claude.json"
    backup_file = tmp_path / ".claude.json.bak"
    source_path = tmp_path / "source"
    target_path = tmp_path / "target"
    source_path.mkdir()
    target_path.mkdir()

    # Create config with both source and target already present
    config = {
        "projects": {
            str(source_path): {"allowedTools": ["bash"], "hasTrustDialogAccepted": True},
            str(target_path): {"allowedTools": ["bash"], "hasTrustDialogAccepted": True},
        }
    }
    config_file.write_text(json.dumps(config, indent=2))

    with patch("imbue.mngr.utils.claude_config.get_claude_config_path", return_value=config_file):
        with patch("imbue.mngr.utils.claude_config.get_claude_config_backup_path", return_value=backup_file):
            extend_claude_trust_to_worktree(source_path, target_path)

    # Backup should NOT exist since no modification was made
    assert not backup_file.exists()


def test_extend_claude_trust_to_worktree_no_source_config(tmp_path: Path) -> None:
    """Test that extend_claude_trust_to_worktree raises if source has no config."""
    config_file = tmp_path / ".claude.json"
    source_path = tmp_path / "source"
    target_path = tmp_path / "target"
    source_path.mkdir()
    target_path.mkdir()

    # Create config without the source project
    config = {"projects": {"/other/project": {"allowedTools": [], "hasTrustDialogAccepted": True}}}
    config_file.write_text(json.dumps(config, indent=2))
    original_content = config_file.read_text()

    with patch("imbue.mngr.utils.claude_config.get_claude_config_path", return_value=config_file):
        with pytest.raises(ClaudeDirectoryNotTrustedError):
            extend_claude_trust_to_worktree(source_path, target_path)

    # File should be unchanged after error
    assert config_file.read_text() == original_content


def test_extend_claude_trust_to_worktree_target_already_exists(tmp_path: Path) -> None:
    """Test that extend_claude_trust_to_worktree does not overwrite existing target config."""
    config_file = tmp_path / ".claude.json"
    source_path = tmp_path / "source"
    target_path = tmp_path / "target"
    source_path.mkdir()
    target_path.mkdir()

    # Create config with both source and target
    config = {
        "projects": {
            str(source_path): {"allowedTools": ["bash"], "hasTrustDialogAccepted": True},
            str(target_path): {"allowedTools": ["different"], "hasTrustDialogAccepted": False},
        }
    }
    config_file.write_text(json.dumps(config, indent=2))

    with patch("imbue.mngr.utils.claude_config.get_claude_config_path", return_value=config_file):
        extend_claude_trust_to_worktree(source_path, target_path)

    # Target should not be overwritten
    updated_config = json.loads(config_file.read_text())
    assert updated_config["projects"][str(target_path)] == {
        "allowedTools": ["different"],
        "hasTrustDialogAccepted": False,
    }


def test_extend_claude_trust_to_worktree_no_config_file(tmp_path: Path) -> None:
    """Test that extend_claude_trust_to_worktree raises if ~/.claude.json doesn't exist."""
    config_file = tmp_path / ".claude.json"
    source_path = tmp_path / "source"
    target_path = tmp_path / "target"
    source_path.mkdir()
    target_path.mkdir()

    # Don't create the config file

    with patch("imbue.mngr.utils.claude_config.get_claude_config_path", return_value=config_file):
        with pytest.raises(ClaudeTrustNotFoundError):
            extend_claude_trust_to_worktree(source_path, target_path)


def test_extend_claude_trust_to_worktree_empty_config_file(tmp_path: Path) -> None:
    """Test that extend_claude_trust_to_worktree raises if config file is empty."""
    config_file = tmp_path / ".claude.json"
    source_path = tmp_path / "source"
    target_path = tmp_path / "target"
    source_path.mkdir()
    target_path.mkdir()

    # Create empty config file
    config_file.write_text("")

    with patch("imbue.mngr.utils.claude_config.get_claude_config_path", return_value=config_file):
        with pytest.raises(ClaudeDirectoryNotTrustedError):
            extend_claude_trust_to_worktree(source_path, target_path)

    # File should be unchanged after error
    assert config_file.read_text() == ""


def test_extend_claude_trust_to_worktree_from_ancestor(tmp_path: Path) -> None:
    """Test that extend_claude_trust_to_worktree copies from ancestor if exact match not found."""
    config_file = tmp_path / ".claude.json"
    source_path = tmp_path / "project" / "src" / "components"
    target_path = tmp_path / "worktree"
    source_path.mkdir(parents=True)
    target_path.mkdir()

    # Create config for the project root, not the subdirectory
    project_root = tmp_path / "project"
    config = {
        "projects": {
            str(project_root): {"allowedTools": ["bash", "edit"], "hasTrustDialogAccepted": True},
        }
    }
    config_file.write_text(json.dumps(config, indent=2))

    with patch("imbue.mngr.utils.claude_config.get_claude_config_path", return_value=config_file):
        extend_claude_trust_to_worktree(source_path, target_path)

    # Target should have the config from the ancestor
    updated_config = json.loads(config_file.read_text())
    assert str(target_path) in updated_config["projects"]
    assert updated_config["projects"][str(target_path)] == {
        "allowedTools": ["bash", "edit"],
        "hasTrustDialogAccepted": True,
    }


def test_extend_claude_trust_to_worktree_config_is_copied_not_referenced(tmp_path: Path) -> None:
    """Test that the config is copied, not just referenced."""
    config_file = tmp_path / ".claude.json"
    source_path = tmp_path / "source"
    target_path = tmp_path / "target"
    source_path.mkdir()
    target_path.mkdir()

    # Create initial config
    config = {
        "projects": {
            str(source_path): {"allowedTools": ["bash"], "hasTrustDialogAccepted": True},
        }
    }
    config_file.write_text(json.dumps(config, indent=2))

    with patch("imbue.mngr.utils.claude_config.get_claude_config_path", return_value=config_file):
        extend_claude_trust_to_worktree(source_path, target_path)

    # Modify the source config
    updated_config = json.loads(config_file.read_text())
    updated_config["projects"][str(source_path)]["allowedTools"].append("write")
    config_file.write_text(json.dumps(updated_config, indent=2))

    # Target should still have original value
    final_config = json.loads(config_file.read_text())
    assert final_config["projects"][str(target_path)]["allowedTools"] == ["bash"]


def test_extend_claude_trust_to_worktree_preserves_other_fields(tmp_path: Path) -> None:
    """Test that extend_claude_trust_to_worktree preserves other fields in config."""
    config_file = tmp_path / ".claude.json"
    source_path = tmp_path / "source"
    target_path = tmp_path / "target"
    source_path.mkdir()
    target_path.mkdir()

    # Create config with extra fields
    config = {
        "someOtherField": "value",
        "projects": {
            str(source_path): {"allowedTools": ["bash"], "hasTrustDialogAccepted": True},
        },
        "anotherField": 123,
    }
    config_file.write_text(json.dumps(config, indent=2))

    with patch("imbue.mngr.utils.claude_config.get_claude_config_path", return_value=config_file):
        extend_claude_trust_to_worktree(source_path, target_path)

    # Other fields should be preserved
    updated_config = json.loads(config_file.read_text())
    assert updated_config["someOtherField"] == "value"
    assert updated_config["anotherField"] == 123


@pytest.mark.parametrize(
    "source_config",
    [
        {"allowedTools": ["bash", "edit", "write"], "hasTrustDialogAccepted": True},
        {"allowedTools": ["bash"], "hasTrustDialogAccepted": True, "extraField": "value"},
    ],
)
def test_extend_claude_trust_to_worktree_various_configs(tmp_path: Path, source_config: dict[str, Any]) -> None:
    """Test that extend_claude_trust_to_worktree handles various config structures."""
    config_file = tmp_path / ".claude.json"
    source_path = tmp_path / "source"
    target_path = tmp_path / "target"
    source_path.mkdir()
    target_path.mkdir()

    # Create initial config
    config = {"projects": {str(source_path): source_config}}
    config_file.write_text(json.dumps(config, indent=2))

    with patch("imbue.mngr.utils.claude_config.get_claude_config_path", return_value=config_file):
        extend_claude_trust_to_worktree(source_path, target_path)

    # Target should have the same config
    updated_config = json.loads(config_file.read_text())
    assert updated_config["projects"][str(target_path)] == source_config


def test_extend_claude_trust_to_worktree_raises_if_not_trusted(tmp_path: Path) -> None:
    """Test that extend_claude_trust_to_worktree raises if source has hasTrustDialogAccepted=false."""
    config_file = tmp_path / ".claude.json"
    source_path = tmp_path / "source"
    target_path = tmp_path / "target"
    source_path.mkdir()
    target_path.mkdir()

    # Create config with hasTrustDialogAccepted=False
    config = {
        "projects": {
            str(source_path): {"allowedTools": ["bash"], "hasTrustDialogAccepted": False},
        }
    }
    config_file.write_text(json.dumps(config, indent=2))
    original_content = config_file.read_text()

    with patch("imbue.mngr.utils.claude_config.get_claude_config_path", return_value=config_file):
        with pytest.raises(ClaudeDirectoryNotTrustedError) as exc_info:
            extend_claude_trust_to_worktree(source_path, target_path)

    assert str(source_path) in str(exc_info.value)
    # File should be unchanged after error
    assert config_file.read_text() == original_content


def test_extend_claude_trust_to_worktree_raises_if_trust_field_missing(tmp_path: Path) -> None:
    """Test that extend_claude_trust_to_worktree raises if hasTrustDialogAccepted is missing."""
    config_file = tmp_path / ".claude.json"
    source_path = tmp_path / "source"
    target_path = tmp_path / "target"
    source_path.mkdir()
    target_path.mkdir()

    # Create config without hasTrustDialogAccepted field
    config = {
        "projects": {
            str(source_path): {"allowedTools": ["bash"]},
        }
    }
    config_file.write_text(json.dumps(config, indent=2))
    original_content = config_file.read_text()

    with patch("imbue.mngr.utils.claude_config.get_claude_config_path", return_value=config_file):
        with pytest.raises(ClaudeDirectoryNotTrustedError):
            extend_claude_trust_to_worktree(source_path, target_path)

    # File should be unchanged after error
    assert config_file.read_text() == original_content


def test_extend_claude_trust_to_worktree_concurrent_writes(tmp_path: Path) -> None:
    """Test that concurrent calls to extend_claude_trust_to_worktree don't corrupt the file.

    Multiple threads write to the same config file simultaneously, and the result
    should be a valid JSON file with all expected entries.
    """
    config_file = tmp_path / ".claude.json"
    source_path = tmp_path / "source"
    source_path.mkdir()

    # Create initial config with source project
    config = {
        "projects": {
            str(source_path): {"allowedTools": ["bash"], "hasTrustDialogAccepted": True},
        }
    }
    config_file.write_text(json.dumps(config, indent=2))

    thread_count = 10
    target_paths = []

    # Create all target directories
    for i in range(thread_count):
        target_path = tmp_path / f"target_{i}"
        target_path.mkdir()
        target_paths.append(target_path)

    def write_config(target_path: Path) -> None:
        with patch("imbue.mngr.utils.claude_config.get_claude_config_path", return_value=config_file):
            extend_claude_trust_to_worktree(source_path, target_path)

    # Run all writes concurrently - any exception will propagate via .result()
    with ThreadPoolExecutor(max_workers=thread_count) as executor:
        futures = [executor.submit(write_config, target_path) for target_path in target_paths]
        for future in futures:
            future.result()

    # Verify the final config is valid JSON
    final_config = json.loads(config_file.read_text())

    # All target paths should be present
    for target_path in target_paths:
        assert str(target_path) in final_config["projects"], f"Missing entry for {target_path}"
        assert final_config["projects"][str(target_path)] == {
            "allowedTools": ["bash"],
            "hasTrustDialogAccepted": True,
        }

    # Source should still be present
    assert str(source_path) in final_config["projects"]
