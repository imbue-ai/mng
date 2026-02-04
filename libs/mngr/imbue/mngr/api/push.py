"""Push API for syncing from local to agent - thin wrappers around sync module."""

from pathlib import Path

from pydantic import Field

from imbue.imbue_common.frozen_model import FrozenModel
from imbue.mngr.api.pull import NotAGitRepositoryError
from imbue.mngr.api.sync import GitSyncError
from imbue.mngr.api.sync import RemoteGitContext
from imbue.mngr.api.sync import SyncFilesResult
from imbue.mngr.api.sync import SyncGitResult
from imbue.mngr.api.sync import SyncMode
from imbue.mngr.api.sync import UncommittedChangesError
from imbue.mngr.api.sync import handle_uncommitted_changes
from imbue.mngr.api.sync import sync_files
from imbue.mngr.api.sync import sync_git
from imbue.mngr.errors import MngrError
from imbue.mngr.interfaces.agent import AgentInterface
from imbue.mngr.interfaces.host import HostInterface
from imbue.mngr.primitives import UncommittedChangesMode

# === Backward-compatible Result Classes ===


class PushResult(FrozenModel):
    """Result of a push operation."""

    files_transferred: int = Field(
        default=0,
        description="Number of files transferred",
    )
    bytes_transferred: int = Field(
        default=0,
        description="Total bytes transferred",
    )
    source_path: Path = Field(
        description="Source path on local machine",
    )
    destination_path: Path = Field(
        description="Destination path on the agent",
    )
    is_dry_run: bool = Field(
        default=False,
        description="Whether this was a dry run",
    )


class PushGitResult(FrozenModel):
    """Result of a git push operation."""

    source_branch: str = Field(
        description="Branch that was pushed from",
    )
    target_branch: str = Field(
        description="Branch that was pushed to",
    )
    source_path: Path = Field(
        description="Source repository path",
    )
    destination_path: Path = Field(
        description="Destination repository path (agent's work_dir)",
    )
    is_dry_run: bool = Field(
        default=False,
        description="Whether this was a dry run",
    )
    commits_pushed: int = Field(
        default=0,
        description="Number of commits pushed",
    )


# === Backward-compatible Error Classes ===


class UncommittedChangesOnTargetError(MngrError):
    """Raised when there are uncommitted changes on the target and mode is FAIL."""

    user_help_text = (
        "Use --uncommitted-changes=stash to stash changes before pushing, "
        "--uncommitted-changes=clobber to overwrite changes, "
        "or --uncommitted-changes=merge to stash, push, then unstash."
    )

    def __init__(self, destination: Path) -> None:
        self.destination = destination
        super().__init__(f"Uncommitted changes on target: {destination}")


class GitPushError(GitSyncError):
    """Raised when a git push operation fails."""

    user_help_text = (
        "Check that the remote repository is accessible and that you have push permissions. "
        "You may need to resolve conflicts manually or use --force-git to overwrite."
    )


# === Helper Functions for Backward Compatibility ===


def _git_reset_hard_on_host(host: HostInterface, destination: Path) -> None:
    """Hard reset the destination to discard all uncommitted changes on the remote host."""
    git_ctx = RemoteGitContext(host=host)
    git_ctx.git_reset_hard(destination)


def _git_stash_on_host(host: HostInterface, destination: Path) -> bool:
    """Stash uncommitted changes on the remote host. Returns True if something was stashed."""
    git_ctx = RemoteGitContext(host=host)
    return git_ctx.git_stash(destination)


def _git_stash_pop_on_host(host: HostInterface, destination: Path) -> None:
    """Pop the most recent stash on the remote host."""
    git_ctx = RemoteGitContext(host=host)
    git_ctx.git_stash_pop(destination)


def _has_uncommitted_changes_on_host(host: HostInterface, destination: Path) -> bool:
    """Check if the destination directory on the host has uncommitted git changes."""
    git_ctx = RemoteGitContext(host=host)
    return git_ctx.has_uncommitted_changes(destination)


def _is_git_repository_on_host(host: HostInterface, path: Path) -> bool:
    """Check if the given path on the host is inside a git repository."""
    git_ctx = RemoteGitContext(host=host)
    return git_ctx.is_git_repository(path)


def _get_current_branch_on_host(host: HostInterface, path: Path) -> str:
    """Get the current branch name for a git repository on the host."""
    git_ctx = RemoteGitContext(host=host)
    return git_ctx.get_current_branch(path)


def handle_uncommitted_changes_on_target(
    host: HostInterface,
    destination: Path,
    uncommitted_changes: UncommittedChangesMode,
) -> bool:
    """Handle uncommitted changes on the target according to the specified mode."""
    git_ctx = RemoteGitContext(host=host)
    return handle_uncommitted_changes(git_ctx, destination, uncommitted_changes)


# === Conversion Functions ===


def _sync_files_result_to_push_result(result: SyncFilesResult) -> PushResult:
    """Convert SyncFilesResult to PushResult for backward compatibility."""
    return PushResult(
        files_transferred=result.files_transferred,
        bytes_transferred=result.bytes_transferred,
        source_path=result.source_path,
        destination_path=result.destination_path,
        is_dry_run=result.is_dry_run,
    )


def _sync_git_result_to_push_git_result(result: SyncGitResult) -> PushGitResult:
    """Convert SyncGitResult to PushGitResult for backward compatibility."""
    return PushGitResult(
        source_branch=result.source_branch,
        target_branch=result.target_branch,
        source_path=result.source_path,
        destination_path=result.destination_path,
        is_dry_run=result.is_dry_run,
        commits_pushed=result.commits_transferred,
    )


# === Main API Functions ===


def push_files(
    agent: AgentInterface,
    host: HostInterface,
    source: Path,
    destination_path: Path | None = None,
    dry_run: bool = False,
    delete: bool = False,
    uncommitted_changes: UncommittedChangesMode = UncommittedChangesMode.FAIL,
) -> PushResult:
    """Push files from a local directory to an agent's work directory using rsync."""
    try:
        result = sync_files(
            agent=agent,
            host=host,
            mode=SyncMode.PUSH,
            local_path=source,
            remote_path=destination_path,
            dry_run=dry_run,
            delete=delete,
            uncommitted_changes=uncommitted_changes,
        )
    except UncommittedChangesError as e:
        # Re-raise as UncommittedChangesOnTargetError for backward compatibility
        raise UncommittedChangesOnTargetError(e.destination) from e
    return _sync_files_result_to_push_result(result)


def push_git(
    agent: AgentInterface,
    host: HostInterface,
    source: Path,
    source_branch: str | None = None,
    target_branch: str | None = None,
    dry_run: bool = False,
    uncommitted_changes: UncommittedChangesMode = UncommittedChangesMode.FAIL,
    mirror: bool = False,
) -> PushGitResult:
    """Push git commits from a local repository to an agent's repository."""
    try:
        result = sync_git(
            agent=agent,
            host=host,
            mode=SyncMode.PUSH,
            local_path=source,
            source_branch=source_branch,
            target_branch=target_branch,
            dry_run=dry_run,
            uncommitted_changes=uncommitted_changes,
            mirror=mirror,
        )
    except UncommittedChangesError as e:
        # Re-raise as UncommittedChangesOnTargetError for backward compatibility
        raise UncommittedChangesOnTargetError(e.destination) from e
    except GitSyncError as e:
        # Re-raise as GitPushError for backward compatibility
        raise GitPushError(str(e).replace("Git sync failed: ", "")) from e
    return _sync_git_result_to_push_git_result(result)


# === Re-exports for Backward Compatibility ===


__all__ = [
    # Result classes
    "PushResult",
    "PushGitResult",
    # Error classes
    "UncommittedChangesOnTargetError",
    "GitPushError",
    "NotAGitRepositoryError",
    # Functions
    "push_files",
    "push_git",
    "handle_uncommitted_changes_on_target",
    # Helper functions for tests
    "_git_reset_hard_on_host",
    "_git_stash_on_host",
    "_git_stash_pop_on_host",
    "_has_uncommitted_changes_on_host",
    "_is_git_repository_on_host",
    "_get_current_branch_on_host",
]
