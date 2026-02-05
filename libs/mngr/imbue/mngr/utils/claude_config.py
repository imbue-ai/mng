import copy
import fcntl
import json
import os
import shutil
import tempfile
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from loguru import logger

from imbue.imbue_common.pure import pure
from imbue.mngr.errors import ClaudeDirectoryNotTrustedError


def get_claude_config_path() -> Path:
    """Return the path to the Claude config file."""
    return Path.home() / ".claude.json"


def get_claude_config_backup_path() -> Path:
    """Return the path to the Claude config backup file."""
    return Path.home() / ".claude.json.bak"


def check_source_directory_trusted(source_path: Path) -> None:
    """Check that the source directory is trusted in Claude's config.

    Reads ~/.claude.json and verifies that source_path (or an ancestor) has
    hasTrustDialogAccepted=true.

    Raises ClaudeDirectoryNotTrustedError if the source is not trusted.
    """
    config_path = get_claude_config_path()

    if not config_path.exists():
        raise ClaudeDirectoryNotTrustedError(str(source_path))

    # Resolve path to absolute for consistent comparison
    source_path = source_path.resolve()

    content = config_path.read_text()
    if not content.strip():
        raise ClaudeDirectoryNotTrustedError(str(source_path))

    config = json.loads(content)

    # Find the source project config
    projects = config.get("projects", {})
    source_config = _find_project_config(projects, source_path)

    if source_config is None:
        raise ClaudeDirectoryNotTrustedError(str(source_path))

    # Verify the source directory was actually trusted
    if not source_config.get("hasTrustDialogAccepted", False):
        raise ClaudeDirectoryNotTrustedError(str(source_path))


def extend_claude_trust_to_worktree(source_path: Path, worktree_path: Path) -> None:
    """Extend Claude's trust settings from source_path to a new worktree.

    Reads ~/.claude.json, finds the project entry for source_path (or the closest
    ancestor with a config entry), and creates a new entry for worktree_path with
    the same settings (allowedTools, hasTrustDialogAccepted, etc.).

    Uses file locking to prevent race conditions when multiple agents are running.
    Writes to a temp file and atomically moves it to prevent partial reads.
    Creates a backup before modifying.

    Raises ClaudeDirectoryNotTrustedError if the source config does not have
    hasTrustDialogAccepted=true.
    """
    config_path = get_claude_config_path()

    if not config_path.exists():
        raise ClaudeDirectoryNotTrustedError(str(source_path))

    # Resolve paths to absolute paths for consistent comparison
    source_path = source_path.resolve()
    worktree_path = worktree_path.resolve()

    # Use file locking to prevent race conditions
    # We create a separate lock file to avoid issues with atomic replacement
    lock_path = config_path.parent / ".claude.json.lock"
    lock_path.touch(exist_ok=True)

    with open(lock_path, "r") as lock_file:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
        try:
            _extend_trust_locked(config_path, source_path, worktree_path)
        finally:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


def _extend_trust_locked(config_path: Path, source_path: Path, worktree_path: Path) -> None:
    """Extend trust while holding the lock. Internal helper."""
    content = config_path.read_text()
    if not content.strip():
        raise ClaudeDirectoryNotTrustedError(str(source_path))

    config = json.loads(content)

    # Find the source project config
    projects = config.get("projects", {})
    source_config = _find_project_config(projects, source_path)

    if source_config is None:
        raise ClaudeDirectoryNotTrustedError(str(source_path))

    # Verify the source directory was actually trusted
    if not source_config.get("hasTrustDialogAccepted", False):
        raise ClaudeDirectoryNotTrustedError(str(source_path))

    # Check if worktree already has config
    worktree_path_str = str(worktree_path)
    if worktree_path_str in projects:
        logger.debug(
            "Claude trust already exists for worktree {}",
            worktree_path,
        )
        return

    # Create a backup before modifying the config
    backup_path = get_claude_config_backup_path()
    shutil.copy2(config_path, backup_path)
    logger.debug("Created backup of Claude config at {}", backup_path)

    # Extend trust to the worktree
    projects[worktree_path_str] = copy.deepcopy(source_config)
    config["projects"] = projects

    # Write to a temp file and atomically move it
    # This prevents readers from seeing partial writes
    config_dir = config_path.parent
    with tempfile.NamedTemporaryFile(
        mode="w",
        dir=config_dir,
        prefix=".claude.json.",
        suffix=".tmp",
        delete=False,
    ) as tmp_file:
        json.dump(config, tmp_file, indent=2)
        tmp_file.write("\n")
        tmp_file.flush()
        os.fsync(tmp_file.fileno())
        tmp_path = Path(tmp_file.name)

    # Atomic move
    tmp_path.rename(config_path)

    logger.debug(
        "Extended Claude trust from {} to worktree {}",
        source_path,
        worktree_path,
    )


def remove_claude_trust_for_path(path: Path) -> bool:
    """Remove Claude's trust entry for a path.

    Removes the project entry for the given path from ~/.claude.json.
    Used during agent cleanup to remove worktree trust entries.

    Uses file locking and atomic writes like extend_claude_trust_to_worktree.

    Returns True if the entry was removed, False if it didn't exist.
    Does not raise on errors - returns False and logs a warning instead.
    """
    config_path = get_claude_config_path()

    if not config_path.exists():
        return False

    path = path.resolve()

    # Use file locking to prevent race conditions
    lock_path = config_path.parent / ".claude.json.lock"
    lock_path.touch(exist_ok=True)

    try:
        with open(lock_path, "r") as lock_file:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
            try:
                return _remove_trust_locked(config_path, path)
            finally:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
    except (OSError, json.JSONDecodeError, KeyError) as e:
        logger.warning(
            "Failed to remove Claude trust entry for {}: {}",
            path,
            e,
        )
        return False


def _remove_trust_locked(config_path: Path, path: Path) -> bool:
    """Remove trust while holding the lock. Internal helper."""
    content = config_path.read_text()
    if not content.strip():
        return False

    config = json.loads(content)
    projects = config.get("projects", {})

    path_str = str(path)
    if path_str not in projects:
        logger.debug("No Claude trust entry found for {}", path)
        return False

    # Remove the entry
    del projects[path_str]
    config["projects"] = projects

    # Write to a temp file and atomically move it
    config_dir = config_path.parent
    with tempfile.NamedTemporaryFile(
        mode="w",
        dir=config_dir,
        prefix=".claude.json.",
        suffix=".tmp",
        delete=False,
    ) as tmp_file:
        json.dump(config, tmp_file, indent=2)
        tmp_file.write("\n")
        tmp_file.flush()
        os.fsync(tmp_file.fileno())
        tmp_path = Path(tmp_file.name)

    # Atomic move
    tmp_path.rename(config_path)

    logger.debug("Removed Claude trust entry for {}", path)
    return True


@pure
def _find_project_config(projects: Mapping[str, Any], path: Path) -> dict[str, Any] | None:
    """Find the project configuration for a path or its closest ancestor.

    Searches for an exact match first, then walks up the directory tree
    to find the closest ancestor with a configuration entry. Returns the
    project configuration dict if found, None otherwise.
    """
    # Try exact match first
    path_str = str(path)
    if path_str in projects:
        return projects[path_str]

    # Walk up the directory tree to find closest ancestor
    current = path.parent
    root = Path(path.anchor)

    while current != root:
        current_str = str(current)
        if current_str in projects:
            return projects[current_str]
        current = current.parent

    # Check root as well
    if str(root) in projects:
        return projects[str(root)]

    return None
