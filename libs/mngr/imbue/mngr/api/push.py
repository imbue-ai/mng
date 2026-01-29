"""API functions for pushing files to agents."""

import shlex
import subprocess
from pathlib import Path
from typing import assert_never

from loguru import logger
from pydantic import Field

from imbue.imbue_common.frozen_model import FrozenModel
from imbue.mngr.api.pull import NotAGitRepositoryError
from imbue.mngr.api.pull import UncommittedChangesError
from imbue.mngr.api.pull import _get_current_branch
from imbue.mngr.api.pull import _is_git_repository
from imbue.mngr.errors import MngrError
from imbue.mngr.interfaces.agent import AgentInterface
from imbue.mngr.interfaces.host import HostInterface
from imbue.mngr.primitives import UncommittedChangesMode


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


def _parse_rsync_output(output: str) -> tuple[int, int]:
    """Parse rsync output to extract transfer statistics."""
    files_transferred = 0
    bytes_transferred = 0

    lines = output.strip().split("\n")

    for line in lines:
        line = line.strip()
        if not line:
            continue
        if line.startswith("sending incremental file list"):
            continue
        if line.startswith("sent "):
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
        if not line.startswith(" "):
            files_transferred += 1

    return files_transferred, bytes_transferred


def _handle_uncommitted_changes_in_agent(
    agent: AgentInterface,
    host: HostInterface,
    uncommitted_changes: UncommittedChangesMode,
) -> bool:
    """Handle uncommitted changes in the agent's work directory.

    Returns True if changes were stashed (and may need to be restored).
    """
    work_dir = agent.work_dir

    # Check if agent's work_dir has uncommitted changes
    result = host.execute_command("git status --porcelain", cwd=work_dir)
    if not result.success:
        # Not a git repo or git not available
        return False

    is_uncommitted = len(result.stdout.strip()) > 0

    if not is_uncommitted:
        return False

    match uncommitted_changes:
        case UncommittedChangesMode.FAIL:
            raise UncommittedChangesError(work_dir)
        case UncommittedChangesMode.STASH:
            logger.debug("Stashing uncommitted changes in agent work_dir")
            stash_result = host.execute_command(
                "git stash push -u -m 'mngr-push-stash'",
                cwd=work_dir,
            )
            if not stash_result.success:
                raise MngrError(f"git stash failed in agent: {stash_result.stderr}")
            return "No local changes to save" not in stash_result.stdout
        case UncommittedChangesMode.MERGE:
            logger.debug("Stashing uncommitted changes in agent work_dir for merge")
            stash_result = host.execute_command(
                "git stash push -u -m 'mngr-push-stash'",
                cwd=work_dir,
            )
            if not stash_result.success:
                raise MngrError(f"git stash failed in agent: {stash_result.stderr}")
            return "No local changes to save" not in stash_result.stdout
        case UncommittedChangesMode.CLOBBER:
            logger.debug("Clobbering uncommitted changes in agent work_dir")
            reset_result = host.execute_command("git reset --hard HEAD", cwd=work_dir)
            if not reset_result.success:
                raise MngrError(f"git reset --hard failed in agent: {reset_result.stderr}")
            clean_result = host.execute_command("git clean -fd", cwd=work_dir)
            if not clean_result.success:
                raise MngrError(f"git clean failed in agent: {clean_result.stderr}")
            return False
        case _ as unreachable:
            assert_never(unreachable)


def _git_stash_pop_in_agent(host: HostInterface, work_dir: Path) -> None:
    """Pop the most recent stash in the agent's work directory."""
    result = host.execute_command("git stash pop", cwd=work_dir)
    if not result.success:
        raise MngrError(f"git stash pop failed in agent: {result.stderr}")


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
    # How to handle uncommitted changes in the agent workspace
    uncommitted_changes: UncommittedChangesMode = UncommittedChangesMode.FAIL,
) -> PushResult:
    """Push files from a local directory to an agent's work directory using rsync."""
    actual_destination_path = destination_path if destination_path is not None else agent.work_dir
    logger.debug("Pushing files from {} to {}", source, actual_destination_path)

    # Handle uncommitted changes in the agent
    did_stash = False
    if uncommitted_changes != UncommittedChangesMode.CLOBBER:
        did_stash = _handle_uncommitted_changes_in_agent(agent, host, uncommitted_changes)

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
    rsync_cmd.append(str(actual_destination_path))

    # For local agents, execute rsync directly
    if host.is_local:
        cmd_str = " ".join(rsync_cmd)
        logger.debug("Running rsync command: {}", cmd_str)
        result = subprocess.run(rsync_cmd, capture_output=True, text=True)
        if result.returncode != 0:
            if did_stash and uncommitted_changes == UncommittedChangesMode.MERGE:
                try:
                    _git_stash_pop_in_agent(host, agent.work_dir)
                except MngrError:
                    logger.warning("Failed to restore stashed changes after rsync failure")
            raise MngrError(f"rsync failed: {result.stderr}")
        stdout = result.stdout
    else:
        # For remote agents, we need to use rsync over SSH
        raise NotImplementedError("Pushing to remote agents is not implemented yet")

    # Parse rsync output to extract statistics
    files_transferred, bytes_transferred = _parse_rsync_output(stdout)

    # For merge mode, restore the stashed changes
    if did_stash and uncommitted_changes == UncommittedChangesMode.MERGE:
        logger.debug("Restoring stashed changes in agent work_dir")
        _git_stash_pop_in_agent(host, agent.work_dir)

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
        destination_path=actual_destination_path,
        is_dry_run=dry_run,
    )


def _count_commits_between_local(source: Path, base_ref: str, head_ref: str) -> int:
    """Count the number of commits between two refs in a local repository."""
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


def _get_head_commit_local(path: Path) -> str:
    """Get the current HEAD commit hash in a local repository."""
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=path,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise MngrError(f"Failed to get HEAD commit: {result.stderr}")
    return result.stdout.strip()


def push_git(
    agent: AgentInterface,
    host: HostInterface,
    source: Path,
    # Branch to push from the local repository (defaults to current branch)
    source_branch: str | None = None,
    # Branch to push into in the agent's repository (defaults to agent's current branch)
    target_branch: str | None = None,
    # If True, only show what would be pushed without actually pushing
    dry_run: bool = False,
    # If True, use --mirror flag (dangerous - replaces all refs)
    mirror: bool = False,
    # How to handle uncommitted changes in the agent workspace
    uncommitted_changes: UncommittedChangesMode = UncommittedChangesMode.FAIL,
) -> PushGitResult:
    """Push git commits from a local repository to an agent's repository.

    This function adds the agent's repository as a temporary remote, pushes to it,
    and then removes the remote after the push.
    """
    destination_path = agent.work_dir
    logger.debug("Pushing git from {} to {}", source, destination_path)

    # Verify both source and destination are git repositories
    if not _is_git_repository(source):
        raise NotAGitRepositoryError(source)

    # Check agent's repo
    check_result = host.execute_command("git rev-parse --git-dir", cwd=destination_path)
    if not check_result.success:
        raise NotAGitRepositoryError(destination_path)

    # Get the source branch (local current branch if not specified)
    actual_source_branch = source_branch if source_branch is not None else _get_current_branch(source)
    logger.debug("Source branch: {}", actual_source_branch)

    # Get the target branch (agent's current branch if not specified)
    if target_branch is not None:
        actual_target_branch = target_branch
    else:
        branch_result = host.execute_command("git rev-parse --abbrev-ref HEAD", cwd=destination_path)
        if not branch_result.success:
            raise MngrError(f"Failed to get agent's current branch: {branch_result.stderr}")
        actual_target_branch = branch_result.stdout.strip()
    logger.debug("Target branch: {}", actual_target_branch)

    # Handle uncommitted changes in the agent
    did_stash = _handle_uncommitted_changes_in_agent(agent, host, uncommitted_changes)

    # For local agents
    if not host.is_local:
        raise NotImplementedError("Pushing to remote agents is not implemented yet")

    # Record the HEAD commit before the push for counting commits
    pre_push_head_result = host.execute_command("git rev-parse HEAD", cwd=destination_path)
    pre_push_head = pre_push_head_result.stdout.strip() if pre_push_head_result.success else None

    # Add source repository as a temporary remote in the agent's repo
    remote_name = "mngr-source-temp"
    try:
        # Remove remote if it already exists (from a previous failed run)
        host.execute_command(f"git remote remove {shlex.quote(remote_name)}", cwd=destination_path)

        # Add the source repository as a remote
        logger.debug("Adding source repository as remote: {}", source)
        add_result = host.execute_command(
            f"git remote add {shlex.quote(remote_name)} {shlex.quote(str(source))}",
            cwd=destination_path,
        )
        if not add_result.success:
            raise MngrError(f"Failed to add remote: {add_result.stderr}")

        # Fetch from the source repository
        logger.debug("Fetching from source repository")
        fetch_result = host.execute_command(
            f"git fetch {shlex.quote(remote_name)} {shlex.quote(actual_source_branch)}",
            cwd=destination_path,
        )
        if not fetch_result.success:
            raise MngrError(f"Failed to fetch from source: {fetch_result.stderr}")

        # Count commits that will be merged
        count_result = host.execute_command(
            f"git rev-list --count HEAD..{shlex.quote(remote_name)}/{shlex.quote(actual_source_branch)}",
            cwd=destination_path,
        )
        commits_to_push = 0
        if count_result.success:
            try:
                commits_to_push = int(count_result.stdout.strip())
            except ValueError:
                pass

        if dry_run:
            logger.info(
                "Dry run: would push {} commits from {} into {}",
                commits_to_push,
                actual_source_branch,
                actual_target_branch,
            )
            commits_pushed = commits_to_push
        else:
            # Checkout the target branch if it's different from the current branch
            current_result = host.execute_command("git rev-parse --abbrev-ref HEAD", cwd=destination_path)
            current_branch = current_result.stdout.strip() if current_result.success else ""

            if current_branch != actual_target_branch:
                logger.debug("Checking out target branch: {}", actual_target_branch)
                checkout_result = host.execute_command(
                    f"git checkout {shlex.quote(actual_target_branch)}",
                    cwd=destination_path,
                )
                if not checkout_result.success:
                    raise MngrError(f"Failed to checkout target branch: {checkout_result.stderr}")

            # Merge the fetched branch
            logger.debug("Merging {}/{} into {}", remote_name, actual_source_branch, actual_target_branch)
            merge_result = host.execute_command(
                f"git merge {shlex.quote(remote_name)}/{shlex.quote(actual_source_branch)} --no-edit",
                cwd=destination_path,
            )
            if not merge_result.success:
                # Abort the merge on failure
                host.execute_command("git merge --abort", cwd=destination_path)
                raise MngrError(f"Git merge failed: {merge_result.stderr}")

            # Count actual commits merged
            if pre_push_head:
                post_push_head_result = host.execute_command("git rev-parse HEAD", cwd=destination_path)
                post_push_head = post_push_head_result.stdout.strip() if post_push_head_result.success else None

                if post_push_head and pre_push_head != post_push_head:
                    count_result = host.execute_command(
                        f"git rev-list --count {shlex.quote(pre_push_head)}..HEAD",
                        cwd=destination_path,
                    )
                    if count_result.success:
                        try:
                            commits_pushed = int(count_result.stdout.strip())
                        except ValueError:
                            commits_pushed = 0
                    else:
                        commits_pushed = 0
                else:
                    commits_pushed = 0
            else:
                commits_pushed = commits_to_push

            logger.info(
                "Git push complete: merged {} commits from {} into {}",
                commits_pushed,
                actual_source_branch,
                actual_target_branch,
            )
    finally:
        # Always remove the temporary remote
        host.execute_command(f"git remote remove {shlex.quote(remote_name)}", cwd=destination_path)

        # For merge mode, restore the stashed changes
        if did_stash and uncommitted_changes == UncommittedChangesMode.MERGE:
            logger.debug("Restoring stashed changes")
            try:
                _git_stash_pop_in_agent(host, destination_path)
            except MngrError:
                logger.warning("Failed to restore stashed changes after git push")

    return PushGitResult(
        source_branch=actual_source_branch,
        target_branch=actual_target_branch,
        source_path=source,
        destination_path=destination_path,
        is_dry_run=dry_run,
        commits_pushed=commits_pushed if not dry_run else commits_to_push,
    )
