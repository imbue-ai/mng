import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from imbue.imbue_common.pure import pure
from imbue.mngr.errors import ClaudeDirectoryNotTrustedError


def get_claude_config_path() -> Path:
    """Return the path to the Claude config file."""
    return Path.home() / ".claude.json"


def check_source_directory_trusted(source_path: Path) -> None:
    """Check that the source directory is trusted in Claude's config.

    Reads ~/.claude.json and verifies that source_path (or an ancestor) has
    hasTrustDialogAccepted=true. This ensures that worktrees created inside
    the source's .git directory will inherit the trust.

    Raises ClaudeDirectoryNotTrustedError if the source is not trusted.
    """
    config_path = get_claude_config_path()

    if not config_path.exists():
        raise ClaudeDirectoryNotTrustedError(str(source_path))

    # Resolve path to absolute for consistent comparison
    source_path = source_path.resolve()

    try:
        content = config_path.read_text()
        if not content.strip():
            raise ClaudeDirectoryNotTrustedError(str(source_path))

        config = json.loads(content)
    except (json.JSONDecodeError, OSError):
        raise ClaudeDirectoryNotTrustedError(str(source_path))

    # Find the source project config
    projects = config.get("projects", {})
    source_config = _find_project_config(projects, source_path)

    if source_config is None:
        raise ClaudeDirectoryNotTrustedError(str(source_path))

    # Verify the source directory was actually trusted
    if not source_config.get("hasTrustDialogAccepted", False):
        raise ClaudeDirectoryNotTrustedError(str(source_path))


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
