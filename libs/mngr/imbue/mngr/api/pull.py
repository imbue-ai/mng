"""Pull API for syncing from agent to local - thin wrappers around sync module."""

from pathlib import Path

from pydantic import Field

from imbue.imbue_common.frozen_model import FrozenModel
from imbue.mngr.api.sync import GitSyncError
from imbue.mngr.api.sync import LocalGitContext
from imbue.mngr.api.sync import NotAGitRepositoryError
from imbue.mngr.api.sync import SyncFilesResult
from imbue.mngr.api.sync import SyncGitResult
from imbue.mngr.api.sync import SyncMode
from imbue.mngr.api.sync import UncommittedChangesError
from imbue.mngr.api.sync import handle_uncommitted_changes
from imbue.mngr.api.sync import sync_files
from imbue.mngr.api.sync import sync_git
from imbue.mngr.interfaces.agent import AgentInterface
from imbue.mngr.interfaces.host import HostInterface
from imbue.mngr.primitives import UncommittedChangesMode

# === Backward-compatible Result Classes ===
# These classes provide the same interface as before for backward compatibility


class PullResult(FrozenModel):
    """Result of a pull operation."""

    files_transferred: int = Field(
        default=0,
        description="Number of files transferred",
    )
    bytes_transferred: int = Field(
        default=0,
        description="Total bytes transferred",
    )
    source_path: Path = Field(
        description="Source path on the agent",
    )
    destination_path: Path = Field(
        description="Destination path on local machine",
    )
    is_dry_run: bool = Field(
        default=False,
        description="Whether this was a dry run",
    )


class PullGitResult(FrozenModel):
    """Result of a git pull operation."""

    source_branch: str = Field(
        description="Branch that was merged from",
    )
    target_branch: str = Field(
        description="Branch that was merged into",
    )
    source_path: Path = Field(
        description="Source repository path (agent's work_dir)",
    )
    destination_path: Path = Field(
        description="Destination repository path",
    )
    is_dry_run: bool = Field(
        default=False,
        description="Whether this was a dry run",
    )
    commits_merged: int = Field(
        default=0,
        description="Number of commits merged",
    )


# === Backward-compatible Error Class ===


class GitMergeError(GitSyncError):
    """Raised when a git merge operation fails."""

    user_help_text = (
        "Resolve the merge conflict manually, or use --uncommitted-changes=clobber to discard local changes."
    )


# === Helper Functions for Backward Compatibility ===


def _has_uncommitted_changes(destination: Path) -> bool:
    """Check if the destination directory has uncommitted git changes."""
    git_ctx = LocalGitContext()
    return git_ctx.has_uncommitted_changes(destination)


def _git_stash(destination: Path) -> bool:
    """Stash uncommitted changes including untracked files. Returns True if something was stashed."""
    git_ctx = LocalGitContext()
    return git_ctx.git_stash(destination)


def _git_stash_pop(destination: Path) -> None:
    """Pop the most recent stash."""
    git_ctx = LocalGitContext()
    git_ctx.git_stash_pop(destination)


def _git_reset_hard(destination: Path) -> None:
    """Hard reset the destination to discard all uncommitted changes."""
    git_ctx = LocalGitContext()
    git_ctx.git_reset_hard(destination)


# === Conversion Functions ===


def _sync_files_result_to_pull_result(result: SyncFilesResult) -> PullResult:
    """Convert SyncFilesResult to PullResult for backward compatibility."""
    return PullResult(
        files_transferred=result.files_transferred,
        bytes_transferred=result.bytes_transferred,
        source_path=result.source_path,
        destination_path=result.destination_path,
        is_dry_run=result.is_dry_run,
    )


def _sync_git_result_to_pull_git_result(result: SyncGitResult) -> PullGitResult:
    """Convert SyncGitResult to PullGitResult for backward compatibility."""
    return PullGitResult(
        source_branch=result.source_branch,
        target_branch=result.target_branch,
        source_path=result.source_path,
        destination_path=result.destination_path,
        is_dry_run=result.is_dry_run,
        commits_merged=result.commits_transferred,
    )


# === Main API Functions ===


def pull_files(
    agent: AgentInterface,
    host: HostInterface,
    destination: Path,
    source_path: Path | None = None,
    dry_run: bool = False,
    delete: bool = False,
    uncommitted_changes: UncommittedChangesMode = UncommittedChangesMode.FAIL,
) -> PullResult:
    """Pull files from an agent's work directory to a local directory using rsync."""
    result = sync_files(
        agent=agent,
        host=host,
        mode=SyncMode.PULL,
        local_path=destination,
        remote_path=source_path,
        dry_run=dry_run,
        delete=delete,
        uncommitted_changes=uncommitted_changes,
    )
    return _sync_files_result_to_pull_result(result)


def pull_git(
    agent: AgentInterface,
    host: HostInterface,
    destination: Path,
    source_branch: str | None = None,
    target_branch: str | None = None,
    dry_run: bool = False,
    uncommitted_changes: UncommittedChangesMode = UncommittedChangesMode.FAIL,
) -> PullGitResult:
    """Pull git commits from an agent's repository by merging branches."""
    try:
        result = sync_git(
            agent=agent,
            host=host,
            mode=SyncMode.PULL,
            local_path=destination,
            source_branch=source_branch,
            target_branch=target_branch,
            dry_run=dry_run,
            uncommitted_changes=uncommitted_changes,
        )
    except GitSyncError as e:
        # Re-raise as GitMergeError for backward compatibility
        raise GitMergeError(str(e).replace("Git sync failed: ", "")) from e
    return _sync_git_result_to_pull_git_result(result)


# === Re-exports for Backward Compatibility ===


__all__ = [
    # Result classes
    "PullResult",
    "PullGitResult",
    # Error classes
    "UncommittedChangesError",
    "NotAGitRepositoryError",
    "GitMergeError",
    # Functions
    "pull_files",
    "pull_git",
    "handle_uncommitted_changes",
    # Helper functions for tests
    "_has_uncommitted_changes",
    "_git_stash",
    "_git_stash_pop",
    "_git_reset_hard",
]
