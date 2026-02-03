import copy
import fcntl
import json
import os
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from loguru import logger

from imbue.imbue_common.pure import pure
from imbue.mngr.errors import ClaudeDirectoryNotTrustedError
from imbue.mngr.errors import ClaudeTrustNotFoundError


def get_claude_config_path() -> Path:
    """Return the path to the Claude config file."""
    return Path.home() / ".claude.json"


def extend_claude_trust_to_worktree(source_path: Path, worktree_path: Path) -> None:
    """Extend Claude's trust settings from source_path to a new worktree.

    Reads ~/.claude.json, finds the project entry for source_path (or the closest
    ancestor with a config entry), and creates a new entry for worktree_path with
    the same settings (allowedTools, hasTrustDialogAccepted).

    Uses file locking to prevent race conditions when multiple agents are running.

    Raises ClaudeDirectoryNotTrustedError if the source config does not have
    hasTrustDialogAccepted=true.
    """
    config_path = get_claude_config_path()

    if not config_path.exists():
        raise ClaudeTrustNotFoundError(str(source_path))

    # Resolve paths to absolute paths for consistent comparison
    source_path = source_path.resolve()
    worktree_path = worktree_path.resolve()

    # Use file locking to prevent race conditions
    # Open in r+ mode for read and write
    with open(config_path, "r+") as f:
        fcntl.flock(f.fileno(), fcntl.LOCK_EX)
        try:
            # Read existing content
            f.seek(0)
            content = f.read()
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

            # Extend trust to the worktree
            projects[worktree_path_str] = copy.deepcopy(source_config)
            config["projects"] = projects

            # Write the updated config
            f.seek(0)
            f.truncate()
            json.dump(config, f, indent=2)
            f.write("\n")

            # Ensure the file is flushed to disk
            f.flush()
            os.fsync(f.fileno())

            logger.debug(
                "Extended Claude trust from {} to worktree {}",
                source_path,
                worktree_path,
            )
        finally:
            fcntl.flock(f.fileno(), fcntl.LOCK_UN)


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
