"""Vendor repositories into a mind's vendor directory as git subtrees.

Reads ``[[vendor]]`` entries from minds.toml (via ``ClaudeMindSettings``) and
adds each repository as a git subtree under ``vendor/<name>/``.

When no vendor configuration is present, falls back to vendoring the mng
repository.  In development mode (running from within the mng monorepo) the
local checkout is used; otherwise the public GitHub URL is used.

Local/editable repos must be "clean" (no uncommitted changes, no untracked
files) before they can be vendored.
"""

from collections.abc import Callable
from pathlib import Path
from typing import Final

from loguru import logger

from imbue.concurrency_group.concurrency_group import ConcurrencyGroup
from imbue.imbue_common.primitives import NonEmptyStr
from imbue.minds.errors import DirtyRepoError
from imbue.minds.errors import VendorError
from imbue.mng_claude_mind.data_types import VendorRepoConfig

MNG_GITHUB_URL: Final[str] = "https://github.com/imbue-ai/mng.git"

VENDOR_DIR_NAME: Final[str] = "vendor"

VENDOR_MNG_DIR_NAME: Final[NonEmptyStr] = NonEmptyStr("mng")


def find_mng_repo_root() -> Path | None:
    """Find the mng monorepo root by walking up from this module's source file.

    Returns the repo root if this module is part of an mng checkout
    (regular repo or worktree), or None if running from an installed package.
    """
    current = Path(__file__).resolve().parent
    while current != current.parent:
        git_marker = current / ".git"
        if git_marker.exists():
            if (current / "libs" / "mng").is_dir():
                return current
            return None
        current = current.parent
    return None


def default_vendor_configs(mng_repo_root: Path | None) -> tuple[VendorRepoConfig, ...]:
    """Build the default vendor config (mng repo) when none is configured.

    Uses the local checkout in development mode, GitHub URL otherwise.
    """
    if mng_repo_root is not None:
        return (
            VendorRepoConfig(
                name=VENDOR_MNG_DIR_NAME,
                path=str(mng_repo_root),
            ),
        )
    return (
        VendorRepoConfig(
            name=VENDOR_MNG_DIR_NAME,
            url=MNG_GITHUB_URL,
        ),
    )


_VENDOR_GIT_USER_NAME: Final[str] = "minds"
_VENDOR_GIT_USER_EMAIL: Final[str] = "minds@localhost"


def _ensure_git_identity(repo_dir: Path) -> None:
    """Ensure git user.name and user.email are configured in the repo.

    ``git subtree add`` creates merge commits, which require a committer
    identity.  When running in environments without a global git config
    (e.g. CI containers), this sets a repo-local identity so the subtree
    operation can succeed.
    """
    cg = ConcurrencyGroup(name="vendor-git-identity")
    with cg:
        name_result = cg.run_process_to_completion(
            command=["git", "config", "user.name"],
            cwd=repo_dir,
            is_checked_after=False,
        )
    if name_result.returncode != 0:
        _run_git(
            ["config", "user.name", _VENDOR_GIT_USER_NAME],
            cwd=repo_dir,
            error_message="Failed to set git user.name",
        )
        _run_git(
            ["config", "user.email", _VENDOR_GIT_USER_EMAIL],
            cwd=repo_dir,
            error_message="Failed to set git user.email",
        )


def vendor_repos(
    mind_dir: Path,
    configs: tuple[VendorRepoConfig, ...],
    on_output: Callable[[str, bool], None] | None = None,
) -> None:
    """Add each configured repository as a git subtree under vendor/.

    Skips any repo whose ``vendor/<name>`` directory already exists.
    Raises DirtyRepoError if a local repo has uncommitted or untracked changes.
    Raises VendorError if any git operation fails.
    """
    _ensure_git_identity(mind_dir)
    for config in configs:
        vendor_subdir = mind_dir / VENDOR_DIR_NAME / config.name
        if vendor_subdir.exists():
            logger.debug("vendor/{} already exists, skipping", config.name)
            continue

        if config.is_local:
            repo_path = _resolve_local_path(config.path)
            check_repo_is_clean(repo_path)
            ref = _resolve_ref_local(repo_path, config.ref)
            logger.debug("Vendoring {} from local repo {} at {}", config.name, repo_path, ref)
            _add_subtree(mind_dir, config.name, str(repo_path), ref, on_output)
        else:
            url = _require_url(config.url)
            ref = _resolve_ref_remote(url, config.ref, on_output)
            logger.debug("Vendoring {} from {} at {}", config.name, url, ref)
            _add_subtree(mind_dir, config.name, url, ref, on_output)


def check_repo_is_clean(repo_path: Path) -> None:
    """Verify that a local repository has no uncommitted changes or untracked files.

    Raises DirtyRepoError if the working tree is not clean.
    """
    status_output = _run_git(
        ["status", "--porcelain"],
        cwd=repo_path,
        error_message="Failed to check git status of {}".format(repo_path),
    )
    if status_output.strip():
        dirty_summary = status_output.strip()[:500]
        raise DirtyRepoError(
            "Local repo {} has uncommitted changes or untracked files and cannot be vendored:\n{}".format(
                repo_path, dirty_summary
            )
        )


def _resolve_local_path(path_str: str | None) -> Path:
    """Resolve a local repo path to an absolute path."""
    if path_str is None:
        raise VendorError("local vendor repo has no path")
    resolved = Path(path_str).expanduser().resolve()
    if not resolved.is_dir():
        raise VendorError("local vendor repo path does not exist: {}".format(resolved))
    return resolved


def _resolve_ref_local(repo_path: Path, ref: str | None) -> str:
    """Resolve the git ref for a local repo, defaulting to HEAD."""
    if ref is not None:
        return ref
    return _run_git(
        ["rev-parse", "HEAD"],
        cwd=repo_path,
        error_message="Failed to resolve HEAD of {}".format(repo_path),
    ).strip()


def _require_url(url: str | None) -> str:
    """Narrow a url that should be non-None (validated by VendorRepoConfig)."""
    if url is None:
        raise VendorError("remote vendor repo has no url")
    return url


def _resolve_ref_remote(
    url: str,
    ref: str | None,
    on_output: Callable[[str, bool], None] | None = None,
) -> str:
    """Resolve the git ref for a remote repo, defaulting to HEAD."""
    if ref is not None:
        return ref
    ls_output = _run_git(
        ["ls-remote", url, "HEAD"],
        cwd=Path.cwd(),
        on_output=on_output,
        error_message="Failed to resolve HEAD of {}".format(url),
    )
    parts = ls_output.strip().split()
    if not parts:
        raise VendorError("git ls-remote returned no output for {}".format(url))
    return parts[0]


def _add_subtree(
    mind_dir: Path,
    name: str,
    url_or_path: str,
    ref: str,
    on_output: Callable[[str, bool], None] | None = None,
) -> None:
    """Run ``git subtree add`` to add a repository under vendor/<name>/."""
    prefix = "{}/{}".format(VENDOR_DIR_NAME, name)
    _run_git(
        ["subtree", "add", "--prefix", prefix, url_or_path, ref, "--squash"],
        cwd=mind_dir,
        on_output=on_output,
        error_message="Failed to add git subtree for {}".format(name),
    )


def _run_git(
    args: list[str],
    cwd: Path,
    on_output: Callable[[str, bool], None] | None = None,
    error_message: str = "git command failed",
) -> str:
    """Run a git command and return stdout.

    Raises VendorError if the command exits with a non-zero status.
    """
    cg = ConcurrencyGroup(name="vendor-git")
    with cg:
        result = cg.run_process_to_completion(
            command=["git", *args],
            cwd=cwd,
            is_checked_after=False,
            on_output=on_output,
        )
    if result.returncode != 0:
        raise VendorError(
            "{} (exit code {}):\n{}".format(
                error_message,
                result.returncode,
                result.stderr.strip() if result.stderr.strip() else result.stdout.strip(),
            )
        )
    return result.stdout
