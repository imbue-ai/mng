import subprocess
from pathlib import Path
from typing import assert_never

from loguru import logger
from pydantic import Field

from imbue.imbue_common.frozen_model import FrozenModel
from imbue.mngr.api.pull import NotAGitRepositoryError
from imbue.mngr.errors import MngrError
from imbue.mngr.utils.git_utils import get_current_branch
from imbue.mngr.utils.git_utils import is_git_repository
from imbue.mngr.interfaces.agent import AgentInterface
from imbue.mngr.interfaces.data_types import CommandResult
from imbue.mngr.interfaces.host import HostInterface
from imbue.mngr.primitives import UncommittedChangesMode
from imbue.mngr.utils.rsync_utils import parse_rsync_output


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


class GitPushError(MngrError):
    """Raised when a git push operation fails."""

    user_help_text = (
        "Check that the remote repository is accessible and that you have push permissions. "
        "You may need to resolve conflicts manually or use --force-git to overwrite."
    )

    def __init__(self, message: str) -> None:
        super().__init__(f"Git push failed: {message}")


def _git_reset_hard_on_host(host: HostInterface, destination: Path) -> None:
    """Hard reset the destination to discard all uncommitted changes on the remote host."""
    result = host.execute_command("git reset --hard HEAD", cwd=destination)
    if not result.success:
        raise MngrError(f"git reset --hard failed: {result.stderr}")

    # Also clean untracked files
    result = host.execute_command("git clean -fd", cwd=destination)
    if not result.success:
        raise MngrError(f"git clean failed: {result.stderr}")


def _git_stash_on_host(host: HostInterface, destination: Path) -> bool:
    """Stash uncommitted changes on the remote host. Returns True if something was stashed."""
    result = host.execute_command(
        'git stash push -u -m "mngr-push-stash"',
        cwd=destination,
    )
    if not result.success:
        raise MngrError(f"git stash failed: {result.stderr}")

    # Check if something was actually stashed
    return "No local changes to save" not in result.stdout


def _git_stash_pop_on_host(host: HostInterface, destination: Path) -> None:
    """Pop the most recent stash on the remote host."""
    result = host.execute_command("git stash pop", cwd=destination)
    if not result.success:
        raise MngrError(f"git stash pop failed: {result.stderr}")


def _has_uncommitted_changes_on_host(host: HostInterface, destination: Path) -> bool:
    """Check if the destination directory on the host has uncommitted git changes."""
    result = host.execute_command("git status --porcelain", cwd=destination)
    if not result.success:
        # If git status fails, assume no changes (not inside a git repo)
        return False

    # If output is non-empty, there are changes
    return len(result.stdout.strip()) > 0


def _is_git_repository_on_host(host: HostInterface, path: Path) -> bool:
    """Check if the given path on the host is inside a git repository."""
    result = host.execute_command("git rev-parse --git-dir", cwd=path)
    return result.success


def _get_current_branch_on_host(host: HostInterface, path: Path) -> str:
    """Get the current branch name for a git repository on the host."""
    result = host.execute_command("git rev-parse --abbrev-ref HEAD", cwd=path)
    if not result.success:
        raise MngrError(f"Failed to get current branch: {result.stderr}")
    return result.stdout.strip()


def handle_uncommitted_changes_on_target(
    host: HostInterface,
    destination: Path,
    uncommitted_changes: UncommittedChangesMode,
) -> bool:
    """Handle uncommitted changes on the target according to the specified mode.

    Returns True if changes were stashed (and may need to be restored).
    """
    is_uncommitted = _has_uncommitted_changes_on_host(host, destination)

    if not is_uncommitted:
        return False

    match uncommitted_changes:
        case UncommittedChangesMode.FAIL:
            raise UncommittedChangesOnTargetError(destination)
        case UncommittedChangesMode.STASH:
            logger.debug("Stashing uncommitted changes on target")
            return _git_stash_on_host(host, destination)
        case UncommittedChangesMode.MERGE:
            logger.debug("Stashing uncommitted changes on target for merge")
            return _git_stash_on_host(host, destination)
        case UncommittedChangesMode.CLOBBER:
            logger.debug("Clobbering uncommitted changes on target")
            _git_reset_hard_on_host(host, destination)
            return False
        case _ as unreachable:
            assert_never(unreachable)


def push_files(
    agent: AgentInterface,
    host: HostInterface,
    source: Path,
    # Destination path within agent's work_dir (defaults to work_dir itself)
    destination_path: Path | None = None,
    # If True, only show what would be transferred
    dry_run: bool = False,
    # If True, delete files in destination that don't exist in source
    delete: bool = False,
    # How to handle uncommitted changes in the destination
    uncommitted_changes: UncommittedChangesMode = UncommittedChangesMode.FAIL,
) -> PushResult:
    """Push files from a local directory to an agent's work directory using rsync."""
    # Determine destination path
    actual_destination = destination_path if destination_path is not None else agent.work_dir
    logger.debug("Pushing files from {} to {}", source, actual_destination)

    # Handle uncommitted changes in the destination
    # For files mode, CLOBBER just lets rsync overwrite (no git reset needed)
    did_stash = False
    if uncommitted_changes != UncommittedChangesMode.CLOBBER:
        did_stash = handle_uncommitted_changes_on_target(host, actual_destination, uncommitted_changes)

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
    source_str = str(source)
    if not source_str.endswith("/"):
        source_str += "/"

    rsync_cmd.append(source_str)
    rsync_cmd.append(str(actual_destination))

    # Execute rsync locally (pushing to the agent's directory)
    cmd_str = " ".join(rsync_cmd)
    logger.debug("Running rsync command: {}", cmd_str)

    result: CommandResult = host.execute_command(cmd_str)

    if not result.success:
        # If we stashed and rsync failed, try to restore the stash for merge mode
        if did_stash and uncommitted_changes == UncommittedChangesMode.MERGE:
            try:
                _git_stash_pop_on_host(host, actual_destination)
            except MngrError:
                logger.warning("Failed to restore stashed changes after rsync failure")
        raise MngrError(f"rsync failed: {result.stderr}")

    # Parse rsync output to extract statistics
    files_transferred, bytes_transferred = parse_rsync_output(result.stdout)

    # For merge mode, restore the stashed changes
    if did_stash and uncommitted_changes == UncommittedChangesMode.MERGE:
        logger.debug("Restoring stashed changes on target")
        _git_stash_pop_on_host(host, actual_destination)

    logger.info(
        "Push complete: {} files, {} bytes transferred{}",
        files_transferred,
        bytes_transferred,
        " (dry run)" if dry_run else "",
    )

    return PushResult(
        files_transferred=files_transferred,
        bytes_transferred=bytes_transferred,
        source_path=source,
        destination_path=actual_destination,
        is_dry_run=dry_run,
    )


def _count_commits_between_local(source: Path, base_ref: str, head_ref: str) -> int:
    """Count the number of commits between two refs locally."""
    result = subprocess.run(
        ["git", "rev-list", "--count", f"{base_ref}..{head_ref}"],
        cwd=source,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return 0
    try:
        return int(result.stdout.strip())
    except ValueError:
        return 0


def push_git(
    agent: AgentInterface,
    host: HostInterface,
    source: Path,
    # Branch to push from the source repository (defaults to source's current branch)
    source_branch: str | None = None,
    # Branch to push to in the destination (defaults to destination's current branch)
    target_branch: str | None = None,
    # If True, only show what would be pushed without actually pushing
    dry_run: bool = False,
    # How to handle uncommitted changes in the destination
    uncommitted_changes: UncommittedChangesMode = UncommittedChangesMode.FAIL,
    # If True, use --mirror for git push (dangerous - overwrites all refs)
    mirror: bool = False,
) -> PushGitResult:
    """Push git commits from a local repository to an agent's repository.

    This function pushes from the source to the agent's repository by adding
    the agent's repository as a temporary remote, pushing to it, and then
    removing the remote.
    """
    destination_path = agent.work_dir
    logger.debug("Pushing git from {} to {}", source, destination_path)

    # Verify both source and destination are git repositories
    if not is_git_repository(source):
        raise NotAGitRepositoryError(source)

    if not _is_git_repository_on_host(host, destination_path):
        raise NotAGitRepositoryError(destination_path)

    # Get the source branch (current branch if not specified)
    actual_source_branch = source_branch if source_branch is not None else get_current_branch(source)
    logger.debug("Source branch: {}", actual_source_branch)

    # Get the target branch (destination's current branch if not specified)
    actual_target_branch = target_branch if target_branch is not None else _get_current_branch_on_host(
        host, destination_path
    )
    logger.debug("Target branch: {}", actual_target_branch)

    # Handle uncommitted changes in the destination
    did_stash = handle_uncommitted_changes_on_target(host, destination_path, uncommitted_changes)

    try:
        # The agent's repository is accessible locally if the host is local
        if host.is_local:
            # Direct push from source to agent's repo
            target_git_dir = str(destination_path)

            if mirror:
                # Mirror push - overwrites all refs (dangerous)
                logger.debug("Performing mirror push to {}", target_git_dir)
                if dry_run:
                    # For dry run, just count commits that would be pushed
                    commits_to_push = _count_commits_between_local(
                        source,
                        actual_target_branch,
                        actual_source_branch,
                    )
                    logger.info(
                        "Dry run: would push {} commits (mirror) from {} to {}",
                        commits_to_push,
                        actual_source_branch,
                        actual_target_branch,
                    )
                else:
                    result = subprocess.run(
                        ["git", "-C", str(source), "push", "--mirror", target_git_dir],
                        capture_output=True,
                        text=True,
                    )
                    if result.returncode != 0:
                        raise GitPushError(result.stderr)
            else:
                # Standard push - push specific branch
                logger.debug("Pushing branch {} to {}", actual_source_branch, target_git_dir)

                # Count commits that will be pushed
                commits_to_push = _count_commits_between_local(
                    source,
                    actual_target_branch,
                    actual_source_branch,
                )

                if dry_run:
                    logger.info(
                        "Dry run: would push {} commits from {} into {}",
                        commits_to_push,
                        actual_source_branch,
                        actual_target_branch,
                    )
                else:
                    # Add agent's repo as a remote, push, then remove
                    remote_name = "mngr-push-temp"

                    # Remove remote if it already exists (from a previous failed run)
                    subprocess.run(
                        ["git", "-C", str(source), "remote", "remove", remote_name],
                        capture_output=True,
                        text=True,
                    )

                    # Add the agent's repository as a remote
                    result = subprocess.run(
                        ["git", "-C", str(source), "remote", "add", remote_name, target_git_dir],
                        capture_output=True,
                        text=True,
                    )
                    if result.returncode != 0:
                        raise GitPushError(f"Failed to add remote: {result.stderr}")

                    try:
                        # Push to the agent's repository
                        result = subprocess.run(
                            [
                                "git",
                                "-C",
                                str(source),
                                "push",
                                remote_name,
                                f"{actual_source_branch}:{actual_target_branch}",
                            ],
                            capture_output=True,
                            text=True,
                        )
                        if result.returncode != 0:
                            raise GitPushError(result.stderr)

                        # Update the working tree on the target.
                        # When pushing to a non-bare repo, the working tree doesn't
                        # automatically update. We need to reset --hard to update it.
                        reset_result = host.execute_command(
                            f"git reset --hard {actual_target_branch}",
                            cwd=destination_path,
                        )
                        if not reset_result.success:
                            raise GitPushError(
                                f"Failed to update working tree: {reset_result.stderr}"
                            )
                    finally:
                        # Always remove the temporary remote
                        subprocess.run(
                            ["git", "-C", str(source), "remote", "remove", remote_name],
                            capture_output=True,
                            text=True,
                        )

                    logger.info(
                        "Git push complete: pushed {} commits from {} to {}",
                        commits_to_push,
                        actual_source_branch,
                        actual_target_branch,
                    )
        else:
            # Remote host - we need to push via SSH
            raise NotImplementedError("Pushing to remote hosts is not implemented yet")

    finally:
        # For merge mode, restore the stashed changes
        if did_stash and uncommitted_changes == UncommittedChangesMode.MERGE:
            logger.debug("Restoring stashed changes on target")
            try:
                _git_stash_pop_on_host(host, destination_path)
            except MngrError:
                logger.warning("Failed to restore stashed changes after git push")

    commits_pushed = commits_to_push

    return PushGitResult(
        source_branch=actual_source_branch,
        target_branch=actual_target_branch,
        source_path=source,
        destination_path=destination_path,
        is_dry_run=dry_run,
        commits_pushed=commits_pushed,
    )
