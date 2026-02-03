import copy
import fcntl
import json
import os
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from loguru import logger

from imbue.imbue_common.pure import pure


def get_claude_config_path() -> Path:
    """Return the path to the Claude config file."""
    return Path.home() / ".claude.json"


def copy_claude_project_config(source_path: Path, target_path: Path) -> None:
    """Copy Claude project configuration from source path to target path.

    Reads ~/.claude.json, finds the project entry for source_path (or the closest
    ancestor with a config entry), and creates a new entry for target_path with
    the same settings (allowedTools, hasTrustDialogAccepted).

    Uses file locking to prevent race conditions when multiple agents are running.

    Args:
        source_path: The original project directory path
        target_path: The new worktree/clone directory path
    """
    config_path = get_claude_config_path()

    # Return early if config file doesn't exist
    if not config_path.exists():
        logger.debug("Claude config file does not exist, nothing to copy")
        return

    # Resolve paths to absolute paths for consistent comparison
    source_path = source_path.resolve()
    target_path = target_path.resolve()

    # Use file locking to prevent race conditions
    # Open in r+ mode for read and write
    with open(config_path, "r+") as f:
        fcntl.flock(f.fileno(), fcntl.LOCK_EX)
        try:
            # Read existing content
            f.seek(0)
            content = f.read()
            if not content.strip():
                logger.debug("Claude config file is empty, nothing to copy")
                return

            config = json.loads(content)

            # Find the source project config
            projects = config.get("projects", {})
            source_config = _find_project_config(projects, source_path)

            if source_config is None:
                logger.debug(
                    "No Claude project config found for source path {}",
                    source_path,
                )
                return

            # Check if target already has config
            target_path_str = str(target_path)
            if target_path_str in projects:
                logger.debug(
                    "Claude project config already exists for target path {}",
                    target_path,
                )
                return

            # Copy the config to the target path
            projects[target_path_str] = copy.deepcopy(source_config)
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
                "Copied Claude project config from {} to {}",
                source_path,
                target_path,
            )
        finally:
            fcntl.flock(f.fileno(), fcntl.LOCK_UN)


@pure
def _find_project_config(projects: Mapping[str, Any], path: Path) -> dict[str, Any] | None:
    """Find the project configuration for a path or its closest ancestor.

    Searches for an exact match first, then walks up the directory tree
    to find the closest ancestor with a configuration entry.

    Args:
        projects: The projects dictionary from ~/.claude.json
        path: The path to search for

    Returns:
        The project configuration dict if found, None otherwise
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
