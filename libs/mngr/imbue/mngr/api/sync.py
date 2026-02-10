"""Unified sync API for push and pull operations between local and agent repositories."""

import shlex
import subprocess
from abc import ABC
from abc import abstractmethod
from collections.abc import Iterator
from contextlib import contextmanager
from contextlib import nullcontext
from enum import auto
from pathlib import Path
from typing import assert_never

from loguru import logger
from pydantic import Field
from pydantic import PrivateAttr

from imbue.imbue_common.enums import UpperCaseStrEnum
from imbue.imbue_common.frozen_model import FrozenModel
from imbue.imbue_common.logging import log_span
from imbue.imbue_common.mutable_model import MutableModel
from imbue.mngr.errors import MngrError
from imbue.mngr.interfaces.agent import AgentInterface
from imbue.mngr.interfaces.data_types import CommandResult
from imbue.mngr.interfaces.host import OnlineHostInterface
from imbue.mngr.primitives import UncommittedChangesMode
from imbue.mngr.utils.git_utils import count_commits_between
from imbue.mngr.utils.git_utils import get_current_branch
from imbue.mngr.utils.git_utils import get_head_commit
from imbue.mngr.utils.git_utils import is_ancestor
from imbue.mngr.utils.git_utils import is_git_repository
from imbue.mngr.utils.rsync_utils import parse_rsync_output

# === Enums ===


class SyncMode(UpperCaseStrEnum):
    """Direction of sync operation.

    PUSH: local -> agent
    PULL: agent -> local
    """

    PUSH = auto()
    PULL = auto()


# === Error Classes ===


class UncommittedChangesError(MngrError):
    """Raised when there are uncommitted changes and mode is FAIL."""

    user_help_text = (
        "Use --uncommitted-changes=stash to stash changes before syncing, "
        "--uncommitted-changes=clobber to overwrite changes, "
        "or --uncommitted-changes=merge to stash, sync, then unstash."
    )

    def __init__(self, destination: Path) -> None:
        self.destination = destination
        super().__init__(f"Uncommitted changes in destination: {destination}")


class NotAGitRepositoryError(MngrError):
    """Raised when a git operation is attempted on a non-git directory."""

    user_help_text = (
        "Use --sync-mode=files to sync files without git, or ensure both source and destination are git repositories."
    )

    def __init__(self, path: Path) -> None:
        self.path = path
        super().__init__(f"Not a git repository: {path}")


class GitSyncError(MngrError):
    """Raised when a git sync operation fails."""

    user_help_text = (
        "Check that the repository is accessible and you have the necessary permissions. "
        "You may need to resolve conflicts manually or use --uncommitted-changes=clobber."
    )

    def __init__(self, message: str) -> None:
        super().__init__(f"Git sync failed: {message}")


# === Result Classes ===


class SyncFilesResult(FrozenModel):
    """Result of a files sync operation."""

    files_transferred: int = Field(
        default=0,
        description="Number of files transferred",
    )
    bytes_transferred: int = Field(
        default=0,
        description="Total bytes transferred",
    )
    source_path: Path = Field(
        description="Source path",
    )
    destination_path: Path = Field(
        description="Destination path",
    )
    is_dry_run: bool = Field(
        default=False,
        description="Whether this was a dry run",
    )
    mode: SyncMode = Field(
        description="Direction of the sync operation",
    )


class SyncGitResult(FrozenModel):
    """Result of a git sync operation."""

    source_branch: str = Field(
        description="Branch that was synced from",
    )
    target_branch: str = Field(
        description="Branch that was synced to",
    )
    source_path: Path = Field(
        description="Source repository path",
    )
    destination_path: Path = Field(
        description="Destination repository path",
    )
    is_dry_run: bool = Field(
        default=False,
        description="Whether this was a dry run",
    )
    commits_transferred: int = Field(
        default=0,
        description="Number of commits transferred",
    )
    mode: SyncMode = Field(
        description="Direction of the sync operation",
    )


# === Git Context Interface and Implementations ===


class GitContextInterface(MutableModel, ABC):
    """Interface for executing git commands either locally or on a remote host."""

    @abstractmethod
    def has_uncommitted_changes(self, path: Path) -> bool:
        """Check if the path has uncommitted git changes."""

    @abstractmethod
    def git_stash(self, path: Path) -> bool:
        """Stash uncommitted changes. Returns True if something was stashed."""

    @abstractmethod
    def git_stash_pop(self, path: Path) -> None:
        """Pop the most recent stash."""

    @abstractmethod
    def git_reset_hard(self, path: Path) -> None:
        """Hard reset to discard all uncommitted changes."""

    @abstractmethod
    def get_current_branch(self, path: Path) -> str:
        """Get the current branch name."""

    @abstractmethod
    def is_git_repository(self, path: Path) -> bool:
        """Check if the path is inside a git repository."""


class LocalGitContext(GitContextInterface):
    """Execute git commands locally via subprocess."""

    def has_uncommitted_changes(self, path: Path) -> bool:
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=path,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise MngrError(f"git status failed in {path}: {result.stderr}")
        return len(result.stdout.strip()) > 0

    def git_stash(self, path: Path) -> bool:
        result = subprocess.run(
            ["git", "stash", "push", "-u", "-m", "mngr-sync-stash"],
            cwd=path,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise MngrError(f"git stash failed: {result.stderr}")
        return "No local changes to save" not in result.stdout

    def git_stash_pop(self, path: Path) -> None:
        result = subprocess.run(
            ["git", "stash", "pop"],
            cwd=path,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise MngrError(f"git stash pop failed: {result.stderr}")

    def git_reset_hard(self, path: Path) -> None:
        result = subprocess.run(
            ["git", "reset", "--hard", "HEAD"],
            cwd=path,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise MngrError(f"git reset --hard failed: {result.stderr}")
        result = subprocess.run(
            ["git", "clean", "-fd"],
            cwd=path,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise MngrError(f"git clean failed: {result.stderr}")

    def get_current_branch(self, path: Path) -> str:
        return get_current_branch(path)

    def is_git_repository(self, path: Path) -> bool:
        return is_git_repository(path)


class RemoteGitContext(GitContextInterface):
    """Execute git commands on a remote host via host.execute_command."""

    _host: OnlineHostInterface = PrivateAttr()

    def __init__(self, *, host: OnlineHostInterface) -> None:
        super().__init__()
        self._host = host

    @property
    def host(self) -> OnlineHostInterface:
        """The host to execute commands on."""
        return self._host

    def has_uncommitted_changes(self, path: Path) -> bool:
        result = self._host.execute_command("git status --porcelain", cwd=path)
        if not result.success:
            raise MngrError(f"git status failed in {path}: {result.stderr}")
        return len(result.stdout.strip()) > 0

    def git_stash(self, path: Path) -> bool:
        result = self._host.execute_command(
            'git stash push -u -m "mngr-sync-stash"',
            cwd=path,
        )
        if not result.success:
            raise MngrError(f"git stash failed: {result.stderr}")
        return "No local changes to save" not in result.stdout

    def git_stash_pop(self, path: Path) -> None:
        result = self._host.execute_command("git stash pop", cwd=path)
        if not result.success:
            raise MngrError(f"git stash pop failed: {result.stderr}")

    def git_reset_hard(self, path: Path) -> None:
        result = self._host.execute_command("git reset --hard HEAD", cwd=path)
        if not result.success:
            raise MngrError(f"git reset --hard failed: {result.stderr}")
        result = self._host.execute_command("git clean -fd", cwd=path)
        if not result.success:
            raise MngrError(f"git clean failed: {result.stderr}")

    def get_current_branch(self, path: Path) -> str:
        result = self._host.execute_command("git rev-parse --abbrev-ref HEAD", cwd=path)
        if not result.success:
            raise MngrError(f"Failed to get current branch: {result.stderr}")
        return result.stdout.strip()

    def is_git_repository(self, path: Path) -> bool:
        result = self._host.execute_command("git rev-parse --git-dir", cwd=path)
        return result.success


# === Uncommitted Changes Handling ===


def handle_uncommitted_changes(
    git_ctx: GitContextInterface,
    path: Path,
    uncommitted_changes: UncommittedChangesMode,
) -> bool:
    """Handle uncommitted changes according to the specified mode.

    Returns True if changes were stashed (and may need to be restored).
    """
    is_uncommitted = git_ctx.has_uncommitted_changes(path)

    if not is_uncommitted:
        return False

    match uncommitted_changes:
        case UncommittedChangesMode.FAIL:
            raise UncommittedChangesError(path)
        case UncommittedChangesMode.STASH:
            logger.debug("Stashing uncommitted changes")
            return git_ctx.git_stash(path)
        case UncommittedChangesMode.MERGE:
            logger.debug("Stashing uncommitted changes for merge")
            return git_ctx.git_stash(path)
        case UncommittedChangesMode.CLOBBER:
            logger.debug("Clobbering uncommitted changes")
            git_ctx.git_reset_hard(path)
            return False
        case _ as unreachable:
            assert_never(unreachable)


@contextmanager
def _stash_guard(
    git_ctx: GitContextInterface,
    path: Path,
    uncommitted_changes: UncommittedChangesMode,
) -> Iterator[bool]:
    """Context manager that stashes/pops around a sync operation.

    Yields True if changes were stashed. On normal exit, pops stash if mode is
    MERGE. On exception, attempts to pop stash for MERGE mode with a warning on
    failure.
    """
    did_stash = handle_uncommitted_changes(git_ctx, path, uncommitted_changes)
    is_success = False
    try:
        yield did_stash
        is_success = True
    finally:
        if did_stash and uncommitted_changes == UncommittedChangesMode.MERGE:
            if is_success:
                logger.debug("Restoring stashed changes")
                git_ctx.git_stash_pop(path)
            else:
                try:
                    git_ctx.git_stash_pop(path)
                except MngrError:
                    logger.warning(
                        "Failed to restore stashed changes after sync failure. "
                        "Run 'git stash pop' in {} to recover your changes.",
                        path,
                    )


# === File Sync Functions ===


def sync_files(
    agent: AgentInterface,
    host: OnlineHostInterface,
    mode: SyncMode,
    local_path: Path,
    remote_path: Path | None = None,
    dry_run: bool = False,
    delete: bool = False,
    uncommitted_changes: UncommittedChangesMode = UncommittedChangesMode.FAIL,
) -> SyncFilesResult:
    """Sync files between local and agent using rsync."""
    if not host.is_local:
        raise NotImplementedError("File sync with remote hosts is not yet implemented")

    actual_remote_path = remote_path if remote_path is not None else agent.work_dir

    # Determine source and destination based on mode
    if mode == SyncMode.PUSH:
        source_path = local_path
        destination_path = actual_remote_path
        git_ctx: GitContextInterface = RemoteGitContext(host=host)
    else:
        source_path = actual_remote_path
        destination_path = local_path
        git_ctx = LocalGitContext()

    # Handle uncommitted changes in the destination.
    # CLOBBER mode skips this check entirely in the file sync path -- it means
    # "proceed with rsync regardless of uncommitted changes" and overwrites files
    # in-place. This differs from handle_uncommitted_changes with CLOBBER in the
    # git sync path, where CLOBBER calls git_reset_hard to discard changes before
    # merging.
    #
    # Also skip if the destination doesn't exist yet (e.g. pushing to a new
    # subdirectory) or isn't a git repo (e.g. pulling to a plain directory).
    is_destination_git_repo = destination_path.is_dir() and git_ctx.is_git_repository(destination_path)
    should_stash = uncommitted_changes != UncommittedChangesMode.CLOBBER and is_destination_git_repo

    stash_cm = _stash_guard(git_ctx, destination_path, uncommitted_changes) if should_stash else nullcontext(False)

    with stash_cm:
        # Ensure destination directory exists for push mode subdirectory targets
        if mode == SyncMode.PUSH and not destination_path.is_dir():
            destination_path.mkdir(parents=True, exist_ok=True)

        # Build rsync command
        rsync_cmd = ["rsync", "-avz", "--stats", "--exclude=.git"]

        if dry_run:
            rsync_cmd.append("--dry-run")

        if delete:
            rsync_cmd.append("--delete")

        # Add trailing slash to source to copy contents, not the directory itself
        source_str = str(source_path)
        if not source_str.endswith("/"):
            source_str += "/"

        rsync_cmd.append(source_str)
        rsync_cmd.append(str(destination_path))

        # Execute rsync
        cmd_str = shlex.join(rsync_cmd)
        direction = "Pushing" if mode == SyncMode.PUSH else "Pulling"

        with log_span("{} files from {} to {}", direction, source_path, destination_path):
            logger.debug("Running rsync command: {}", cmd_str)
            result: CommandResult = host.execute_command(cmd_str)

        if not result.success:
            raise MngrError(f"rsync failed: {result.stderr}")

        # Parse rsync output to extract statistics
        files_transferred, bytes_transferred = parse_rsync_output(result.stdout)

    logger.debug(
        "Sync complete: {} files, {} bytes transferred{}",
        files_transferred,
        bytes_transferred,
        " (dry run)" if dry_run else "",
    )

    return SyncFilesResult(
        files_transferred=files_transferred,
        bytes_transferred=bytes_transferred,
        source_path=source_path,
        destination_path=destination_path,
        is_dry_run=dry_run,
        mode=mode,
    )


# === Git Sync Helper Functions ===


def _get_head_commit_or_raise(path: Path) -> str:
    """Get the current HEAD commit hash, raising on failure."""
    commit = get_head_commit(path)
    if commit is None:
        raise MngrError(f"Failed to get HEAD commit in {path}")
    return commit


def _merge_fetch_head(local_path: Path) -> None:
    """Merge FETCH_HEAD into the current branch, aborting on conflict."""
    result = subprocess.run(
        ["git", "merge", "FETCH_HEAD", "--no-edit"],
        cwd=local_path,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        # Check if a merge is actually in progress before trying to abort
        merge_check = subprocess.run(
            ["git", "rev-parse", "--verify", "MERGE_HEAD"],
            cwd=local_path,
            capture_output=True,
            text=True,
        )
        if merge_check.returncode == 0:
            abort_result = subprocess.run(
                ["git", "merge", "--abort"],
                cwd=local_path,
                capture_output=True,
                text=True,
            )
            if abort_result.returncode != 0:
                logger.warning(
                    "Failed to abort merge in {}: {}. Repository may be in a conflicted state.",
                    local_path,
                    abort_result.stderr.strip(),
                )
        raise GitSyncError(result.stderr)


# === Git Push Functions ===


def _local_git_push_mirror(
    local_path: Path,
    destination_path: Path,
    host: OnlineHostInterface,
    source_branch: str,
    dry_run: bool,
) -> int:
    """Push via mirror fetch, overwriting all refs in the target.

    Returns the number of commits transferred.
    """
    target_git_dir = str(destination_path)
    logger.debug("Performing mirror fetch to {}", target_git_dir)

    pre_fetch_head = get_head_commit(destination_path)

    if dry_run:
        # Estimate using pre_fetch_head (the agent's current HEAD). target_branch
        # is a branch name that may not exist locally, but pre_fetch_head is a
        # commit hash valid in both repos since local agents share the same git
        # object store.
        if pre_fetch_head is not None:
            return count_commits_between(local_path, pre_fetch_head, source_branch)
        return 0

    # Fetch all refs from source into target. --update-head-ok is needed because
    # git otherwise refuses to fetch into the currently checked-out branch.
    result = subprocess.run(
        [
            "git",
            "-C",
            target_git_dir,
            "fetch",
            "--update-head-ok",
            str(local_path),
            "--force",
            "refs/*:refs/*",
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise GitSyncError(result.stderr)

    # Reset working tree to match the source branch content. We do NOT checkout
    # source_branch because in the worktree case (local agents), the source
    # branch may already be checked out in the source worktree, and git forbids
    # two worktrees from having the same branch checked out.
    reset_result = host.execute_command(
        f"git reset --hard refs/heads/{source_branch}",
        cwd=destination_path,
    )
    if not reset_result.success:
        raise GitSyncError(f"Failed to update working tree: {reset_result.stderr}")

    # Count actual commits transferred by comparing pre/post HEAD
    post_fetch_head = get_head_commit(destination_path)
    if pre_fetch_head is not None and post_fetch_head is not None and pre_fetch_head != post_fetch_head:
        return count_commits_between(destination_path, pre_fetch_head, post_fetch_head)
    return 0


def _local_git_push_branch(
    local_path: Path,
    destination_path: Path,
    host: OnlineHostInterface,
    source_branch: str,
    target_branch: str,
    dry_run: bool,
) -> int:
    """Push a single branch via fetch+reset.

    Returns the number of commits transferred.
    """
    target_git_dir = str(destination_path)
    logger.debug("Fetching branch {} into {}", source_branch, target_git_dir)

    pre_fetch_head = get_head_commit(destination_path)

    if dry_run:
        if pre_fetch_head is not None:
            return count_commits_between(local_path, pre_fetch_head, source_branch)
        return 0

    # Fetch from source repo into the target
    result = subprocess.run(
        ["git", "-C", target_git_dir, "fetch", str(local_path), source_branch],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise GitSyncError(result.stderr)

    # Resolve FETCH_HEAD to an explicit commit hash to avoid race conditions
    hash_result = subprocess.run(
        ["git", "-C", target_git_dir, "rev-parse", "FETCH_HEAD"],
        capture_output=True,
        text=True,
    )
    if hash_result.returncode != 0:
        raise GitSyncError(f"Failed to resolve FETCH_HEAD: {hash_result.stderr}")
    fetched_commit = hash_result.stdout.strip()

    # Check for non-fast-forward push (diverged history)
    if pre_fetch_head is not None and pre_fetch_head != fetched_commit:
        is_fast_forward = is_ancestor(destination_path, pre_fetch_head, fetched_commit)
        if not is_fast_forward:
            raise GitSyncError(
                f"Cannot push: agent branch '{target_branch}' has diverged from "
                f"local branch '{source_branch}'. Use --mirror to force-overwrite "
                f"all refs, or pull agent changes first to reconcile."
            )

    # Reset the target branch to the fetched commit
    reset_result = host.execute_command(
        f"git reset --hard {fetched_commit}",
        cwd=destination_path,
    )
    if not reset_result.success:
        raise GitSyncError(f"Failed to update working tree: {reset_result.stderr}")

    # Count actual commits transferred
    commits_transferred = 0
    if pre_fetch_head is not None and pre_fetch_head != fetched_commit:
        commits_transferred = count_commits_between(destination_path, pre_fetch_head, fetched_commit)

    logger.debug(
        "Git push complete: pushed {} commits from {} to {}",
        commits_transferred,
        source_branch,
        target_branch,
    )
    return commits_transferred


def _sync_git_push(
    agent: AgentInterface,
    host: OnlineHostInterface,
    local_path: Path,
    source_branch: str,
    target_branch: str,
    dry_run: bool,
    uncommitted_changes: UncommittedChangesMode,
    mirror: bool,
) -> SyncGitResult:
    """Push git commits from local to agent repository."""
    destination_path = agent.work_dir
    git_ctx = RemoteGitContext(host=host)

    with _stash_guard(git_ctx, destination_path, uncommitted_changes):
        if host.is_local:
            if mirror:
                commits_transferred = _local_git_push_mirror(
                    local_path,
                    destination_path,
                    host,
                    source_branch,
                    dry_run,
                )
            else:
                commits_transferred = _local_git_push_branch(
                    local_path,
                    destination_path,
                    host,
                    source_branch,
                    target_branch,
                    dry_run,
                )
        else:
            raise NotImplementedError("Pushing to remote hosts is not yet implemented")

    return SyncGitResult(
        source_branch=source_branch,
        target_branch=target_branch,
        source_path=local_path,
        destination_path=destination_path,
        is_dry_run=dry_run,
        commits_transferred=commits_transferred,
        mode=SyncMode.PUSH,
    )


# === Git Pull Functions ===


def _fetch_and_merge(
    local_path: Path,
    source_path: Path,
    source_branch: str,
    target_branch: str,
    original_branch: str,
    dry_run: bool,
) -> int:
    """Fetch from source repo and merge into target branch.

    Handles checkout to target_branch if different from original_branch, and
    restores original_branch on both success and failure. Returns the number
    of commits transferred.
    """
    # Fetch from the agent's repository (sets FETCH_HEAD)
    logger.debug("Fetching from agent repository: {}", source_path)
    result = subprocess.run(
        ["git", "fetch", str(source_path), source_branch],
        cwd=local_path,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise MngrError(f"Failed to fetch from agent: {result.stderr}")

    # Checkout the target branch if different from current
    did_checkout = original_branch != target_branch
    if did_checkout:
        logger.debug("Checking out target branch: {}", target_branch)
        checkout_result = subprocess.run(
            ["git", "checkout", target_branch],
            cwd=local_path,
            capture_output=True,
            text=True,
        )
        if checkout_result.returncode != 0:
            raise MngrError(f"Failed to checkout target branch: {checkout_result.stderr}")

    # Record HEAD after checkout so we count commits on the target branch
    pre_merge_head = _get_head_commit_or_raise(local_path)
    commits_to_merge = count_commits_between(local_path, "HEAD", "FETCH_HEAD")

    try:
        if dry_run:
            logger.debug(
                "Dry run: would merge {} commits from {} into {}",
                commits_to_merge,
                source_branch,
                target_branch,
            )
            commits_transferred = commits_to_merge
        else:
            _merge_fetch_head(local_path)
            post_merge_head = _get_head_commit_or_raise(local_path)
            commits_transferred = (
                count_commits_between(local_path, pre_merge_head, post_merge_head)
                if pre_merge_head != post_merge_head
                else 0
            )
            logger.debug(
                "Git pull complete: merged {} commits from {} into {}",
                commits_transferred,
                source_branch,
                target_branch,
            )
    except MngrError:
        # On failure, try to restore original branch before re-raising
        if did_checkout:
            restore_result = subprocess.run(
                ["git", "checkout", original_branch],
                cwd=local_path,
                capture_output=True,
                text=True,
            )
            if restore_result.returncode != 0:
                logger.warning(
                    "Failed to restore branch {} after git pull failure: {}",
                    original_branch,
                    restore_result.stderr.strip(),
                )
        raise

    # Restore original branch on success
    if did_checkout:
        restore_result = subprocess.run(
            ["git", "checkout", original_branch],
            cwd=local_path,
            capture_output=True,
            text=True,
        )
        if restore_result.returncode != 0:
            raise MngrError(f"Failed to checkout original branch {original_branch}: {restore_result.stderr}")

    return commits_transferred


def _sync_git_pull(
    agent: AgentInterface,
    host: OnlineHostInterface,
    local_path: Path,
    source_branch: str,
    target_branch: str,
    dry_run: bool,
    uncommitted_changes: UncommittedChangesMode,
) -> SyncGitResult:
    """Pull git commits from agent to local repository."""
    source_path = agent.work_dir
    git_ctx = LocalGitContext()
    original_branch = get_current_branch(local_path)

    with _stash_guard(git_ctx, local_path, uncommitted_changes):
        commits_transferred = _fetch_and_merge(
            local_path=local_path,
            source_path=source_path,
            source_branch=source_branch,
            target_branch=target_branch,
            original_branch=original_branch,
            dry_run=dry_run,
        )

    return SyncGitResult(
        source_branch=source_branch,
        target_branch=target_branch,
        source_path=source_path,
        destination_path=local_path,
        is_dry_run=dry_run,
        commits_transferred=commits_transferred,
        mode=SyncMode.PULL,
    )


# === Top-Level Git Sync ===


def sync_git(
    agent: AgentInterface,
    host: OnlineHostInterface,
    mode: SyncMode,
    local_path: Path,
    source_branch: str | None = None,
    target_branch: str | None = None,
    dry_run: bool = False,
    uncommitted_changes: UncommittedChangesMode = UncommittedChangesMode.FAIL,
    mirror: bool = False,
) -> SyncGitResult:
    """Sync git commits between local and agent."""
    remote_path = agent.work_dir
    local_git_ctx = LocalGitContext()
    remote_git_ctx = RemoteGitContext(host=host)

    logger.debug("Syncing git from {} to {} (mode={})", local_path, remote_path, mode)

    # Verify both are git repositories
    if not local_git_ctx.is_git_repository(local_path):
        raise NotAGitRepositoryError(local_path)

    if not remote_git_ctx.is_git_repository(remote_path):
        raise NotAGitRepositoryError(remote_path)

    if mode == SyncMode.PUSH:
        # Push: local -> agent
        actual_source_branch = (
            source_branch if source_branch is not None else local_git_ctx.get_current_branch(local_path)
        )
        actual_target_branch = (
            target_branch if target_branch is not None else remote_git_ctx.get_current_branch(remote_path)
        )

        return _sync_git_push(
            agent=agent,
            host=host,
            local_path=local_path,
            source_branch=actual_source_branch,
            target_branch=actual_target_branch,
            dry_run=dry_run,
            uncommitted_changes=uncommitted_changes,
            mirror=mirror,
        )
    else:
        # Pull: agent -> local
        actual_source_branch = (
            source_branch if source_branch is not None else remote_git_ctx.get_current_branch(remote_path)
        )
        actual_target_branch = (
            target_branch if target_branch is not None else local_git_ctx.get_current_branch(local_path)
        )

        if mirror:
            raise NotImplementedError("Mirror mode is only supported for push operations")

        return _sync_git_pull(
            agent=agent,
            host=host,
            local_path=local_path,
            source_branch=actual_source_branch,
            target_branch=actual_target_branch,
            dry_run=dry_run,
            uncommitted_changes=uncommitted_changes,
        )
