import subprocess
from pathlib import Path
from typing import assert_never

import deal
from loguru import logger
from pydantic import Field

from imbue.imbue_common.frozen_model import FrozenModel
from imbue.mngr.errors import MngrError
from imbue.mngr.interfaces.agent import AgentInterface
from imbue.mngr.interfaces.data_types import CommandResult
from imbue.mngr.interfaces.host import HostInterface
from imbue.mngr.primitives import UncommittedChangesMode


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


class UncommittedChangesError(MngrError):
    """Raised when there are uncommitted changes and mode is FAIL."""

    user_help_text = (
        "Use --uncommitted-changes=stash to stash changes before pulling, "
        "--uncommitted-changes=clobber to overwrite changes, "
        "or --uncommitted-changes=merge to stash, pull, then unstash."
    )

    def __init__(self, destination: Path) -> None:
        self.destination = destination
        super().__init__(f"Uncommitted changes in destination: {destination}")


class NotAGitRepositoryError(MngrError):
    """Raised when a git operation is attempted on a non-git directory."""

    user_help_text = (
        "Use --sync-mode=files to sync files without git, "
        "or ensure both source and destination are git repositories."
    )

    def __init__(self, path: Path) -> None:
        self.path = path
        super().__init__(f"Not a git repository: {path}")


class GitMergeError(MngrError):
    """Raised when a git merge operation fails."""

    user_help_text = (
        "Resolve the merge conflict manually, or use --uncommitted-changes=clobber "
        "to discard local changes."
    )

    def __init__(self, message: str) -> None:
        super().__init__(f"Git merge failed: {message}")


def _has_uncommitted_changes(destination: Path) -> bool:
    """Check if the destination directory has uncommitted git changes.

    Works correctly even when destination is a subdirectory within a git repository.
    """
    # Run git status to check for uncommitted changes
    # This works from any subdirectory within a git worktree
    result = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=destination,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        # If git status fails, assume no changes (not inside a git repo)
        return False

    # If output is non-empty, there are changes
    return len(result.stdout.strip()) > 0


def _git_stash(destination: Path) -> bool:
    """Stash uncommitted changes. Returns True if something was stashed."""
    result = subprocess.run(
        ["git", "stash", "push", "-m", "mngr-pull-stash"],
        cwd=destination,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise MngrError(f"git stash failed: {result.stderr}")

    # Check if something was actually stashed by looking at the output
    # "No local changes to save" means nothing was stashed
    return "No local changes to save" not in result.stdout


def _git_stash_pop(destination: Path) -> None:
    """Pop the most recent stash."""
    result = subprocess.run(
        ["git", "stash", "pop"],
        cwd=destination,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise MngrError(f"git stash pop failed: {result.stderr}")


def _is_git_repository(path: Path) -> bool:
    """Check if the given path is inside a git repository."""
    result = subprocess.run(
        ["git", "rev-parse", "--git-dir"],
        cwd=path,
        capture_output=True,
        text=True,
    )
    return result.returncode == 0


def _get_current_branch(path: Path) -> str:
    """Get the current branch name for a git repository."""
    result = subprocess.run(
        ["git", "rev-parse", "--abbrev-ref", "HEAD"],
        cwd=path,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise MngrError(f"Failed to get current branch: {result.stderr}")
    return result.stdout.strip()


def _git_reset_hard(destination: Path) -> None:
    """Hard reset the destination to discard all uncommitted changes."""
    result = subprocess.run(
        ["git", "reset", "--hard", "HEAD"],
        cwd=destination,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise MngrError(f"git reset --hard failed: {result.stderr}")

    # Also clean untracked files
    result = subprocess.run(
        ["git", "clean", "-fd"],
        cwd=destination,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise MngrError(f"git clean failed: {result.stderr}")


def handle_uncommitted_changes(
    destination: Path,
    uncommitted_changes: UncommittedChangesMode,
) -> bool:
    """Handle uncommitted changes according to the specified mode.

    Returns True if changes were stashed (and may need to be restored).
    """
    is_uncommitted = _has_uncommitted_changes(destination)

    if not is_uncommitted:
        return False

    match uncommitted_changes:
        case UncommittedChangesMode.FAIL:
            raise UncommittedChangesError(destination)
        case UncommittedChangesMode.STASH:
            logger.debug("Stashing uncommitted changes")
            return _git_stash(destination)
        case UncommittedChangesMode.MERGE:
            logger.debug("Stashing uncommitted changes for merge")
            return _git_stash(destination)
        case UncommittedChangesMode.CLOBBER:
            logger.debug("Clobbering uncommitted changes")
            _git_reset_hard(destination)
            return False
        case _ as unreachable:
            assert_never(unreachable)


def pull_files(
    agent: AgentInterface,
    host: HostInterface,
    destination: Path,
    # Source path within agent's work_dir (defaults to work_dir itself)
    source_path: Path | None = None,
    # If True, only show what would be transferred
    dry_run: bool = False,
    # If True, delete files in destination that don't exist in source
    delete: bool = False,
    # How to handle uncommitted changes in the destination
    uncommitted_changes: UncommittedChangesMode = UncommittedChangesMode.FAIL,
) -> PullResult:
    """Pull files from an agent's work directory to a local directory using rsync."""
    # Determine source path
    actual_source_path = source_path if source_path is not None else agent.work_dir
    logger.debug("Pulling files from {} to {}", actual_source_path, destination)

    # Handle uncommitted changes in the destination
    # Note: For files mode, CLOBBER just lets rsync overwrite (no git reset needed)
    did_stash = False
    if uncommitted_changes != UncommittedChangesMode.CLOBBER:
        did_stash = handle_uncommitted_changes(destination, uncommitted_changes)

    # Build rsync command
    # -a: archive mode (recursive, preserves permissions, etc.)
    # -v: verbose
    # -z: compress during transfer
    # --progress: show progress
    # --exclude=.git: exclude git directory to avoid conflicts
    rsync_cmd = ["rsync", "-avz", "--progress", "--exclude=.git"]

    if dry_run:
        rsync_cmd.append("--dry-run")

    if delete:
        rsync_cmd.append("--delete")

    # Add trailing slash to source to copy contents, not the directory itself
    source_str = str(actual_source_path)
    if not source_str.endswith("/"):
        source_str += "/"

    rsync_cmd.append(source_str)
    rsync_cmd.append(str(destination))

    # Execute rsync on the host
    cmd_str = " ".join(rsync_cmd)
    logger.debug("Running rsync command: {}", cmd_str)

    result: CommandResult = host.execute_command(cmd_str)

    if not result.success:
        # If we stashed and rsync failed, try to restore the stash for merge mode
        if did_stash and uncommitted_changes == UncommittedChangesMode.MERGE:
            try:
                _git_stash_pop(destination)
            except MngrError:
                logger.warning("Failed to restore stashed changes after rsync failure")
        raise MngrError(f"rsync failed: {result.stderr}")

    # Parse rsync output to extract statistics
    files_transferred, bytes_transferred = _parse_rsync_output(result.stdout)

    # For merge mode, restore the stashed changes
    if did_stash and uncommitted_changes == UncommittedChangesMode.MERGE:
        logger.debug("Restoring stashed changes")
        _git_stash_pop(destination)

    logger.info(
        "Pull complete: {} files, {} bytes transferred{}",
        files_transferred,
        bytes_transferred,
        " (dry run)" if dry_run else "",
    )

    return PullResult(
        files_transferred=files_transferred,
        bytes_transferred=bytes_transferred,
        source_path=actual_source_path,
        destination_path=destination,
        is_dry_run=dry_run,
    )


@deal.has()
def _parse_rsync_output(
    # stdout from rsync command
    output: str,
    # Tuple of (files_transferred, bytes_transferred)
) -> tuple[int, int]:
    """Parse rsync output to extract transfer statistics."""
    files_transferred = 0
    bytes_transferred = 0

    lines = output.strip().split("\n")

    # Count files from the output (non-empty, non-stat lines)
    for line in lines:
        line = line.strip()
        # Skip empty lines and stat summary lines
        if not line:
            continue
        if line.startswith("sending incremental file list"):
            continue
        if line.startswith("sent "):
            # Parse "sent X bytes  received Y bytes" line
            parts = line.split()
            for i, part in enumerate(parts):
                if part == "bytes" and i > 0:
                    try:
                        bytes_transferred = int(parts[i - 1].replace(",", ""))
                    except (ValueError, IndexError):
                        pass
                    break
            continue
        if line.startswith("total size"):
            continue
        # This is a file being transferred
        if not line.startswith(" "):
            files_transferred += 1

    return files_transferred, bytes_transferred


def _count_commits_between(destination: Path, base_ref: str, head_ref: str) -> int:
    """Count the number of commits between two refs."""
    result = subprocess.run(
        ["git", "rev-list", "--count", f"{base_ref}..{head_ref}"],
        cwd=destination,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return 0
    try:
        return int(result.stdout.strip())
    except ValueError:
        return 0


def _get_head_commit(path: Path) -> str:
    """Get the current HEAD commit hash."""
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=path,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise MngrError(f"Failed to get HEAD commit: {result.stderr}")
    return result.stdout.strip()


def pull_git(
    agent: AgentInterface,
    host: HostInterface,
    destination: Path,
    # Branch to merge from the agent's repository (defaults to agent's current branch)
    source_branch: str | None = None,
    # Branch to merge into in the destination (defaults to destination's current branch)
    target_branch: str | None = None,
    # If True, only show what would be merged without actually merging
    dry_run: bool = False,
    # How to handle uncommitted changes in the destination
    uncommitted_changes: UncommittedChangesMode = UncommittedChangesMode.FAIL,
) -> PullGitResult:
    """Pull git commits from an agent's repository by merging branches.

    This function fetches the agent's branch and merges it into the destination's branch.
    The agent's repository is added as a temporary remote, fetched from, and then the
    remote is removed after the merge.
    """
    source_path = agent.work_dir
    logger.debug("Pulling git from {} to {}", source_path, destination)

    # Verify both source and destination are git repositories
    if not _is_git_repository(destination):
        raise NotAGitRepositoryError(destination)

    if not _is_git_repository(source_path):
        raise NotAGitRepositoryError(source_path)

    # Get the source branch (agent's current branch if not specified)
    actual_source_branch = source_branch if source_branch is not None else _get_current_branch(source_path)
    logger.debug("Source branch: {}", actual_source_branch)

    # Get the target branch (destination's current branch if not specified)
    actual_target_branch = target_branch if target_branch is not None else _get_current_branch(destination)
    logger.debug("Target branch: {}", actual_target_branch)

    # Handle uncommitted changes in the destination
    did_stash = handle_uncommitted_changes(destination, uncommitted_changes)

    # Record the HEAD commit before the merge for counting commits
    pre_merge_head = _get_head_commit(destination)

    # Add agent's repository as a temporary remote
    remote_name = "mngr-agent-temp"
    try:
        # Remove remote if it already exists (from a previous failed run)
        subprocess.run(
            ["git", "remote", "remove", remote_name],
            cwd=destination,
            capture_output=True,
            text=True,
        )

        # Add the agent's repository as a remote
        logger.debug("Adding agent repository as remote: {}", source_path)
        result = subprocess.run(
            ["git", "remote", "add", remote_name, str(source_path)],
            cwd=destination,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise MngrError(f"Failed to add remote: {result.stderr}")

        # Fetch from the agent's repository
        logger.debug("Fetching from agent repository")
        result = subprocess.run(
            ["git", "fetch", remote_name, actual_source_branch],
            cwd=destination,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise MngrError(f"Failed to fetch from agent: {result.stderr}")

        # Checkout the target branch if it's different from the current branch
        current_branch = _get_current_branch(destination)
        if current_branch != actual_target_branch:
            logger.debug("Checking out target branch: {}", actual_target_branch)
            result = subprocess.run(
                ["git", "checkout", actual_target_branch],
                cwd=destination,
                capture_output=True,
                text=True,
            )
            if result.returncode != 0:
                raise MngrError(f"Failed to checkout target branch: {result.stderr}")

        # Count commits that will be merged
        commits_to_merge = _count_commits_between(
            destination,
            "HEAD",
            f"{remote_name}/{actual_source_branch}",
        )

        if dry_run:
            logger.info(
                "Dry run: would merge {} commits from {} into {}",
                commits_to_merge,
                actual_source_branch,
                actual_target_branch,
            )
        else:
            # Merge the fetched branch
            logger.debug("Merging {}/{} into {}", remote_name, actual_source_branch, actual_target_branch)
            result = subprocess.run(
                ["git", "merge", f"{remote_name}/{actual_source_branch}", "--no-edit"],
                cwd=destination,
                capture_output=True,
                text=True,
            )
            if result.returncode != 0:
                # Abort the merge on failure
                subprocess.run(
                    ["git", "merge", "--abort"],
                    cwd=destination,
                    capture_output=True,
                    text=True,
                )
                raise GitMergeError(result.stderr)

            # Count actual commits merged
            post_merge_head = _get_head_commit(destination)
            if pre_merge_head != post_merge_head:
                commits_merged = _count_commits_between(destination, pre_merge_head, post_merge_head)
            else:
                commits_merged = 0

            logger.info(
                "Git pull complete: merged {} commits from {} into {}",
                commits_merged,
                actual_source_branch,
                actual_target_branch,
            )
    finally:
        # Always remove the temporary remote
        subprocess.run(
            ["git", "remote", "remove", remote_name],
            cwd=destination,
            capture_output=True,
            text=True,
        )

        # For merge mode, restore the stashed changes
        if did_stash and uncommitted_changes == UncommittedChangesMode.MERGE:
            logger.debug("Restoring stashed changes")
            try:
                _git_stash_pop(destination)
            except MngrError:
                logger.warning("Failed to restore stashed changes after git pull")

    commits_merged_result = commits_to_merge if dry_run else commits_merged

    return PullGitResult(
        source_branch=actual_source_branch,
        target_branch=actual_target_branch,
        source_path=source_path,
        destination_path=destination,
        is_dry_run=dry_run,
        commits_merged=commits_merged_result,
    )
