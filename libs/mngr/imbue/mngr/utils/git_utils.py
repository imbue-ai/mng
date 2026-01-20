import subprocess
from pathlib import Path
from urllib.parse import urlparse

import deal


def get_current_git_branch(path: Path | None = None) -> str | None:
    """Get the current git branch name for the repository at the given path.

    Returns None if the path is not a git repository or an error occurs.
    """
    try:
        cwd = path or Path.cwd()
        result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=cwd,
            capture_output=True,
            text=True,
            check=True,
        )
        branch_name = result.stdout.strip()
        return branch_name
    except subprocess.CalledProcessError:
        return None


def derive_project_name_from_path(path: Path) -> str:
    """Derive a project name from a path.

    Attempts to extract the project name from the git remote origin URL if available.
    Falls back to the folder name if there is no git repository or the URL structure
    is not recognized.
    """
    # Try to get the git remote origin URL
    git_project_name = _get_project_name_from_git_remote(path)
    if git_project_name is not None:
        return git_project_name

    # Fallback to the folder name
    return path.resolve().name


def _get_project_name_from_git_remote(path: Path) -> str | None:
    """Get the project name from the git remote origin URL.

    Supports GitHub and GitLab URL formats:
    - https://github.com/owner/repo.git
    - git@github.com:owner/repo.git
    - https://gitlab.com/owner/repo.git
    - git@gitlab.com:owner/repo.git

    Returns None if not a git repo or URL format is unknown.
    """
    # Check if this is a git repository
    git_dir = path / ".git"
    if not git_dir.exists():
        return None

    # Try to get the remote origin URL
    try:
        result = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            cwd=path,
            capture_output=True,
            text=True,
            timeout=5,
        )

        if result.returncode != 0:
            return None

        origin_url = result.stdout.strip()

        # Parse the URL to extract the project name
        return _parse_project_name_from_url(origin_url)
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return None


@deal.has()
def _parse_project_name_from_url(url: str) -> str | None:
    """Parse the project name from a git remote URL.

    Returns None if the URL format is not recognized.
    """
    # Handle SSH-style URLs (e.g., git@github.com:owner/repo.git)
    if "@" in url and ":" in url:
        # Split on ':' to get the path part
        parts = url.split(":")
        if len(parts) == 2:
            path_part = parts[1]
            # Remove .git suffix if present
            if path_part.endswith(".git"):
                path_part = path_part[:-4]
            # Extract the project name (last component)
            project_name = path_part.split("/")[-1]
            if project_name:
                return project_name

    # Handle HTTPS URLs (e.g., https://github.com/owner/repo.git)
    try:
        parsed = urlparse(url)
        # Only process if it looks like a proper URL with a scheme
        if parsed.scheme in ("http", "https"):
            if parsed.path:
                path = parsed.path.strip("/")
                # Remove .git suffix if present
                if path.endswith(".git"):
                    path = path[:-4]
                # Extract the project name (last component)
                project_name = path.split("/")[-1]
                if project_name:
                    return project_name
    except ValueError:
        pass

    return None


def find_git_worktree_root(start: Path | None = None) -> Path | None:
    """Find the git worktree root."""
    cwd = start or Path.cwd()
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=cwd,
            capture_output=True,
            text=True,
            check=True,
        )
        return Path(result.stdout.strip())
    except subprocess.CalledProcessError:
        return None
