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
    is_uncommitted = _has_uncommitted_changes(destination)
    did_stash = False

    if is_uncommitted:
        match uncommitted_changes:
            case UncommittedChangesMode.FAIL:
                raise UncommittedChangesError(destination)
            case UncommittedChangesMode.STASH:
                logger.debug("Stashing uncommitted changes")
                did_stash = _git_stash(destination)
            case UncommittedChangesMode.MERGE:
                logger.debug("Stashing uncommitted changes for merge")
                did_stash = _git_stash(destination)
            case UncommittedChangesMode.CLOBBER:
                logger.debug("Clobbering uncommitted changes")
                # Do nothing - rsync will overwrite
            case _ as unreachable:
                assert_never(unreachable)

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
