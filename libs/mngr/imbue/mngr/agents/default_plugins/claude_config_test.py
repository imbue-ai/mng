"""Unit tests for claude_config.py."""

import json
from pathlib import Path

import pytest

from imbue.mngr.agents.default_plugins.claude_config import ClaudeDirectoryNotTrustedError
from imbue.mngr.agents.default_plugins.claude_config import _find_project_config
from imbue.mngr.agents.default_plugins.claude_config import add_claude_trust_for_path
from imbue.mngr.agents.default_plugins.claude_config import check_source_directory_trusted
from imbue.mngr.agents.default_plugins.claude_config import extend_claude_trust_to_worktree
from imbue.mngr.agents.default_plugins.claude_config import get_claude_config_backup_path
from imbue.mngr.agents.default_plugins.claude_config import get_claude_config_path
from imbue.mngr.agents.default_plugins.claude_config import remove_claude_trust_for_path


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
    config_file = get_claude_config_path()
    source_path = tmp_path / "source"
    source_path.mkdir()

    # Create config with trusted source
    config = {
        "projects": {
            str(source_path): {"allowedTools": ["bash"], "hasTrustDialogAccepted": True},
        }
    }
    config_file.write_text(json.dumps(config, indent=2))

    # Should not raise
    check_source_directory_trusted(source_path)


def test_check_source_directory_trusted_succeeds_for_subdirectory(tmp_path: Path) -> None:
    """Test that check_source_directory_trusted passes for subdirectory of trusted path."""
    config_file = get_claude_config_path()
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

    # Should not raise - subdirectory inherits trust from ancestor
    check_source_directory_trusted(source_path)


def test_check_source_directory_trusted_raises_when_not_trusted(tmp_path: Path) -> None:
    """Test that check_source_directory_trusted raises when hasTrustDialogAccepted=false."""
    config_file = get_claude_config_path()
    source_path = tmp_path / "source"
    source_path.mkdir()

    # Create config with hasTrustDialogAccepted=False
    config = {
        "projects": {
            str(source_path): {"allowedTools": ["bash"], "hasTrustDialogAccepted": False},
        }
    }
    config_file.write_text(json.dumps(config, indent=2))

    with pytest.raises(ClaudeDirectoryNotTrustedError) as exc_info:
        check_source_directory_trusted(source_path)

    assert str(source_path) in str(exc_info.value)


def test_check_source_directory_trusted_raises_when_no_config_file(tmp_path: Path) -> None:
    """Test that check_source_directory_trusted raises when ~/.claude.json doesn't exist."""
    source_path = tmp_path / "source"
    source_path.mkdir()

    # Don't create the config file - HOME points to tmp_path via autouse fixture

    with pytest.raises(ClaudeDirectoryNotTrustedError):
        check_source_directory_trusted(source_path)


def test_check_source_directory_trusted_raises_when_empty_config(tmp_path: Path) -> None:
    """Test that check_source_directory_trusted raises when config file is empty."""
    config_file = get_claude_config_path()
    source_path = tmp_path / "source"
    source_path.mkdir()

    # Create empty config file
    config_file.write_text("")

    with pytest.raises(ClaudeDirectoryNotTrustedError):
        check_source_directory_trusted(source_path)


def test_check_source_directory_trusted_raises_when_not_in_projects(tmp_path: Path) -> None:
    """Test that check_source_directory_trusted raises when source not in projects."""
    config_file = get_claude_config_path()
    source_path = tmp_path / "source"
    source_path.mkdir()

    # Create config without the source project
    config = {"projects": {"/other/project": {"allowedTools": [], "hasTrustDialogAccepted": True}}}
    config_file.write_text(json.dumps(config, indent=2))

    with pytest.raises(ClaudeDirectoryNotTrustedError):
        check_source_directory_trusted(source_path)


def test_check_source_directory_trusted_raises_when_trust_field_missing(tmp_path: Path) -> None:
    """Test that check_source_directory_trusted raises when hasTrustDialogAccepted is missing."""
    config_file = get_claude_config_path()
    source_path = tmp_path / "source"
    source_path.mkdir()

    # Create config without hasTrustDialogAccepted field
    config = {
        "projects": {
            str(source_path): {"allowedTools": ["bash"]},
        }
    }
    config_file.write_text(json.dumps(config, indent=2))

    with pytest.raises(ClaudeDirectoryNotTrustedError):
        check_source_directory_trusted(source_path)


def test_check_source_directory_trusted_raises_json_error_for_invalid_json(tmp_path: Path) -> None:
    """Test that check_source_directory_trusted lets JSONDecodeError bubble up."""
    config_file = get_claude_config_path()
    source_path = tmp_path / "source"
    source_path.mkdir()

    # Create invalid JSON
    config_file.write_text("{ invalid json }")

    with pytest.raises(json.JSONDecodeError):
        check_source_directory_trusted(source_path)


# Tests for add_claude_trust_for_path


def test_add_claude_trust_creates_config_when_none_exists(tmp_path: Path) -> None:
    """Test that add_claude_trust_for_path creates ~/.claude.json if it doesn't exist."""
    source_path = tmp_path / "source"
    source_path.mkdir()

    # HOME points to a test-isolated temp dir (autouse setup_test_mngr_env)
    config_file = get_claude_config_path()
    assert not config_file.exists()

    add_claude_trust_for_path(source_path)

    assert config_file.exists()
    config = json.loads(config_file.read_text())
    assert config["projects"][str(source_path)]["hasTrustDialogAccepted"] is True


def test_add_claude_trust_adds_entry_to_existing_config(tmp_path: Path) -> None:
    """Test that add_claude_trust_for_path adds entry to existing config."""
    config_file = get_claude_config_path()
    source_path = tmp_path / "source"
    source_path.mkdir()

    # Create config with another project
    config = {"projects": {"/other/project": {"allowedTools": [], "hasTrustDialogAccepted": True}}}
    config_file.write_text(json.dumps(config, indent=2))

    add_claude_trust_for_path(source_path)

    updated = json.loads(config_file.read_text())
    # New entry added
    assert updated["projects"][str(source_path)]["hasTrustDialogAccepted"] is True
    # Existing entry preserved
    assert "/other/project" in updated["projects"]


def test_add_claude_trust_is_noop_when_already_trusted(tmp_path: Path) -> None:
    """Test that add_claude_trust_for_path is a no-op when path is already trusted."""
    config_file = get_claude_config_path()
    backup_file = get_claude_config_backup_path()
    source_path = tmp_path / "source"
    source_path.mkdir()

    # Create config with already-trusted source
    config = {
        "projects": {
            str(source_path): {"allowedTools": ["bash"], "hasTrustDialogAccepted": True},
        }
    }
    config_file.write_text(json.dumps(config, indent=2))

    add_claude_trust_for_path(source_path)

    # No backup should be created (no modification)
    assert not backup_file.exists()
    # Config should be unchanged
    updated = json.loads(config_file.read_text())
    assert updated["projects"][str(source_path)]["allowedTools"] == ["bash"]


def test_add_claude_trust_updates_entry_when_trust_is_false(tmp_path: Path) -> None:
    """Test that add_claude_trust_for_path updates entry when hasTrustDialogAccepted is False."""
    config_file = get_claude_config_path()
    source_path = tmp_path / "source"
    source_path.mkdir()

    # Create config with untrusted entry that has other fields
    config = {
        "projects": {
            str(source_path): {"allowedTools": ["bash"], "hasTrustDialogAccepted": False},
        }
    }
    config_file.write_text(json.dumps(config, indent=2))

    add_claude_trust_for_path(source_path)

    updated = json.loads(config_file.read_text())
    entry = updated["projects"][str(source_path)]
    # Trust should be set
    assert entry["hasTrustDialogAccepted"] is True
    # Other fields preserved
    assert entry["allowedTools"] == ["bash"]


def test_add_claude_trust_handles_empty_config_file(tmp_path: Path) -> None:
    """Test that add_claude_trust_for_path handles empty config file."""
    config_file = get_claude_config_path()
    source_path = tmp_path / "source"
    source_path.mkdir()

    config_file.write_text("")

    add_claude_trust_for_path(source_path)

    config = json.loads(config_file.read_text())
    assert config["projects"][str(source_path)]["hasTrustDialogAccepted"] is True


# Tests for extend_claude_trust_to_worktree


def test_extend_claude_trust_creates_entry_for_worktree(tmp_path: Path) -> None:
    """Test that extend_claude_trust_to_worktree creates an entry for the worktree."""
    config_file = get_claude_config_path()
    source_path = tmp_path / "source"
    worktree_path = tmp_path / "worktree"
    source_path.mkdir()
    worktree_path.mkdir()

    # Create config with trusted source
    source_config = {
        "allowedTools": ["bash", "read"],
        "hasTrustDialogAccepted": True,
        "mcpServers": {"example": {"command": "test"}},
    }
    config = {"projects": {str(source_path): source_config}}
    config_file.write_text(json.dumps(config, indent=2))

    extend_claude_trust_to_worktree(source_path, worktree_path)

    # Verify the worktree entry was created with mngr metadata
    updated_config = json.loads(config_file.read_text())
    assert str(worktree_path) in updated_config["projects"]
    worktree_config = updated_config["projects"][str(worktree_path)]
    # Check source config fields are copied
    assert worktree_config["allowedTools"] == source_config["allowedTools"]
    assert worktree_config["hasTrustDialogAccepted"] == source_config["hasTrustDialogAccepted"]
    assert worktree_config["mcpServers"] == source_config["mcpServers"]
    # Check mngr metadata is added
    assert worktree_config["_mngrCreated"] is True
    assert worktree_config["_mngrSourcePath"] == str(source_path)


def test_extend_claude_trust_creates_backup(tmp_path: Path) -> None:
    """Test that extend_claude_trust_to_worktree creates a backup."""
    config_file = get_claude_config_path()
    backup_file = get_claude_config_backup_path()
    source_path = tmp_path / "source"
    worktree_path = tmp_path / "worktree"
    source_path.mkdir()
    worktree_path.mkdir()

    # Create config with trusted source
    config = {
        "projects": {
            str(source_path): {"allowedTools": [], "hasTrustDialogAccepted": True},
        }
    }
    config_file.write_text(json.dumps(config, indent=2))

    extend_claude_trust_to_worktree(source_path, worktree_path)

    # Verify backup was created
    assert backup_file.exists()
    backup_config = json.loads(backup_file.read_text())
    # Backup should have the original config (without worktree)
    assert str(worktree_path) not in backup_config["projects"]


def test_extend_claude_trust_skips_if_entry_exists(tmp_path: Path) -> None:
    """Test that extend_claude_trust_to_worktree skips if entry already exists."""
    config_file = get_claude_config_path()
    backup_file = get_claude_config_backup_path()
    source_path = tmp_path / "source"
    worktree_path = tmp_path / "worktree"
    source_path.mkdir()
    worktree_path.mkdir()

    # Create config with both source and worktree already present
    existing_worktree_config = {"allowedTools": ["existing"], "hasTrustDialogAccepted": True}
    config = {
        "projects": {
            str(source_path): {"allowedTools": ["bash"], "hasTrustDialogAccepted": True},
            str(worktree_path): existing_worktree_config,
        }
    }
    config_file.write_text(json.dumps(config, indent=2))

    extend_claude_trust_to_worktree(source_path, worktree_path)

    # Verify the existing worktree config was not modified
    updated_config = json.loads(config_file.read_text())
    assert updated_config["projects"][str(worktree_path)] == existing_worktree_config
    # No backup should be created when skipping
    assert not backup_file.exists()


def test_extend_claude_trust_raises_when_source_not_trusted(tmp_path: Path) -> None:
    """Test that extend_claude_trust_to_worktree raises when source not trusted."""
    config_file = get_claude_config_path()
    source_path = tmp_path / "source"
    worktree_path = tmp_path / "worktree"
    source_path.mkdir()
    worktree_path.mkdir()

    # Create config with untrusted source
    config = {
        "projects": {
            str(source_path): {"allowedTools": [], "hasTrustDialogAccepted": False},
        }
    }
    config_file.write_text(json.dumps(config, indent=2))

    with pytest.raises(ClaudeDirectoryNotTrustedError):
        extend_claude_trust_to_worktree(source_path, worktree_path)


def test_extend_claude_trust_raises_when_no_config(tmp_path: Path) -> None:
    """Test that extend_claude_trust_to_worktree raises when config doesn't exist."""
    source_path = tmp_path / "source"
    worktree_path = tmp_path / "worktree"
    source_path.mkdir()
    worktree_path.mkdir()

    # Don't create the config file - HOME points to tmp_path via autouse fixture

    with pytest.raises(ClaudeDirectoryNotTrustedError):
        extend_claude_trust_to_worktree(source_path, worktree_path)


def test_extend_claude_trust_raises_when_empty_config(tmp_path: Path) -> None:
    """Test that extend_claude_trust_to_worktree raises when config file is empty."""
    config_file = get_claude_config_path()
    source_path = tmp_path / "source"
    worktree_path = tmp_path / "worktree"
    source_path.mkdir()
    worktree_path.mkdir()

    config_file.write_text("")

    with pytest.raises(ClaudeDirectoryNotTrustedError):
        extend_claude_trust_to_worktree(source_path, worktree_path)


# Tests for remove_claude_trust_for_path


def test_remove_claude_trust_removes_mngr_created_entry(tmp_path: Path) -> None:
    """Test that remove_claude_trust_for_path removes mngr-created entries."""
    config_file = get_claude_config_path()
    worktree_path = tmp_path / "worktree"
    worktree_path.mkdir()

    # Create config with mngr-created worktree entry
    config = {
        "projects": {
            str(worktree_path): {
                "allowedTools": [],
                "hasTrustDialogAccepted": True,
                "_mngrCreated": True,
                "_mngrSourcePath": "/some/source",
            },
            "/other/project": {"allowedTools": [], "hasTrustDialogAccepted": True},
        }
    }
    config_file.write_text(json.dumps(config, indent=2))

    result = remove_claude_trust_for_path(worktree_path)

    assert result is True
    updated_config = json.loads(config_file.read_text())
    assert str(worktree_path) not in updated_config["projects"]
    # Other entries should remain
    assert "/other/project" in updated_config["projects"]


def test_remove_claude_trust_skips_non_mngr_entry(tmp_path: Path) -> None:
    """Test that remove_claude_trust_for_path skips entries not created by mngr."""
    config_file = get_claude_config_path()
    worktree_path = tmp_path / "worktree"
    worktree_path.mkdir()

    # Create config with user-created entry (no _mngrCreated)
    config = {
        "projects": {
            str(worktree_path): {"allowedTools": [], "hasTrustDialogAccepted": True},
        }
    }
    config_file.write_text(json.dumps(config, indent=2))

    result = remove_claude_trust_for_path(worktree_path)

    # Should return False since it's not an mngr-created entry
    assert result is False
    # Entry should still exist
    updated_config = json.loads(config_file.read_text())
    assert str(worktree_path) in updated_config["projects"]


def test_remove_claude_trust_returns_false_when_not_found(tmp_path: Path) -> None:
    """Test that remove_claude_trust_for_path returns False when entry doesn't exist."""
    config_file = get_claude_config_path()
    worktree_path = tmp_path / "worktree"
    worktree_path.mkdir()

    # Create config without the worktree entry
    config = {
        "projects": {
            "/other/project": {"allowedTools": [], "hasTrustDialogAccepted": True},
        }
    }
    config_file.write_text(json.dumps(config, indent=2))

    result = remove_claude_trust_for_path(worktree_path)

    assert result is False


def test_remove_claude_trust_returns_false_when_no_config(tmp_path: Path) -> None:
    """Test that remove_claude_trust_for_path returns False when config doesn't exist."""
    worktree_path = tmp_path / "worktree"
    worktree_path.mkdir()

    # Don't create the config file - HOME points to tmp_path via autouse fixture

    result = remove_claude_trust_for_path(worktree_path)

    assert result is False


def test_remove_claude_trust_returns_false_on_error(tmp_path: Path) -> None:
    """Test that remove_claude_trust_for_path returns False on errors."""
    config_file = get_claude_config_path()
    worktree_path = tmp_path / "worktree"
    worktree_path.mkdir()

    # Create invalid JSON
    config_file.write_text("{ invalid json }")

    # Should not raise, but return False
    result = remove_claude_trust_for_path(worktree_path)

    assert result is False


def test_remove_claude_trust_returns_false_when_empty_config(tmp_path: Path) -> None:
    """Test that remove_claude_trust_for_path returns False when config file is empty."""
    config_file = get_claude_config_path()
    worktree_path = tmp_path / "worktree"
    worktree_path.mkdir()

    config_file.write_text("")

    result = remove_claude_trust_for_path(worktree_path)

    assert result is False
