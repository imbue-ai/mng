import fcntl
import json
import os
import shutil
from collections.abc import Mapping
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from loguru import logger
from pydantic import Field

from imbue.imbue_common.frozen_model import FrozenModel
from imbue.imbue_common.pure import pure
from imbue.mngr.errors import ClaudeDirectoryNotTrustedError
from imbue.mngr.errors import ClaudeTrustNotFoundError


class ClaudeProjectConfig(FrozenModel, extra="allow"):
    """Configuration for a Claude project entry in ~/.claude.json.

    Allows extra fields since Claude's config may contain additional properties.
    """

    allowedTools: Sequence[str] = Field(default_factory=list, description="List of allowed tools for this project")
    hasTrustDialogAccepted: bool = Field(default=False, description="Whether the trust dialog has been accepted")


def get_claude_config_path() -> Path:
    """Return the path to the Claude config file."""
    return Path.home() / ".claude.json"


def get_claude_config_backup_path() -> Path:
    """Return the path to the Claude config backup file."""
    return Path.home() / ".claude.json.bak"


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
            if not source_config.hasTrustDialogAccepted:
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
            projects[worktree_path_str] = source_config.model_dump()
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
def _find_project_config(projects: Mapping[str, Any], path: Path) -> ClaudeProjectConfig | None:
    """Find the project configuration for a path or its closest ancestor.

    Searches for an exact match first, then walks up the directory tree
    to find the closest ancestor with a configuration entry. Returns the
    project configuration if found, None otherwise.
    """
    # Try exact match first
    path_str = str(path)
    if path_str in projects:
        return ClaudeProjectConfig.model_validate(projects[path_str])

    # Walk up the directory tree to find closest ancestor
    current = path.parent
    root = Path(path.anchor)

    while current != root:
        current_str = str(current)
        if current_str in projects:
            return ClaudeProjectConfig.model_validate(projects[current_str])
        current = current.parent

    # Check root as well
    if str(root) in projects:
        return ClaudeProjectConfig.model_validate(projects[str(root)])

    return None
