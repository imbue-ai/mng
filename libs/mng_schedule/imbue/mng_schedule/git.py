"""Shared git utilities for the mng_schedule plugin."""

from pathlib import Path

from loguru import logger

from imbue.concurrency_group.concurrency_group import ConcurrencyGroup
from imbue.mng_schedule.errors import ScheduleDeployError


def resolve_git_ref(ref: str, cwd: Path | None = None) -> str:
    """Resolve a git ref (e.g. HEAD, branch name) to a full commit SHA.

    Raises ScheduleDeployError if the ref cannot be resolved.
    """
    with ConcurrencyGroup(name="git-rev-parse") as cg:
        result = cg.run_process_to_completion(
            ["git", "rev-parse", ref],
            is_checked_after=False,
            cwd=cwd,
        )
    if result.returncode != 0:
        raise ScheduleDeployError(f"Could not resolve git ref '{ref}': {result.stderr.strip()}") from None
    return result.stdout.strip()


def get_current_branch(cwd: Path | None = None) -> str:
    """Get the current git branch name.

    Raises ScheduleDeployError if the branch cannot be determined or HEAD is detached.
    """
    with ConcurrencyGroup(name="git-current-branch") as cg:
        result = cg.run_process_to_completion(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            is_checked_after=False,
            cwd=cwd,
        )
    if result.returncode != 0:
        raise ScheduleDeployError(f"Could not determine current branch: {result.stderr.strip()}") from None
    branch_name = result.stdout.strip()
    if branch_name == "HEAD":
        raise ScheduleDeployError("Cannot deploy from a detached HEAD. Check out a branch first.") from None
    return branch_name


def ensure_current_branch_is_pushed(cwd: Path | None = None) -> None:
    """Verify that the current branch has been pushed to the remote.

    Checks that:
    1. The current branch is not detached
    2. The remote tracking branch (origin/<branch>) exists
    3. There are no unpushed commits (local is not ahead of remote)

    Raises ScheduleDeployError if the branch is not fully pushed.
    """
    branch_name = get_current_branch(cwd=cwd)

    # Check if the remote tracking branch exists and if there are unpushed commits.
    with ConcurrencyGroup(name="git-upstream-check") as cg:
        result = cg.run_process_to_completion(
            ["git", "log", f"origin/{branch_name}..HEAD", "--oneline"],
            is_checked_after=False,
            cwd=cwd,
        )
    if result.returncode != 0:
        raise ScheduleDeployError(
            f"Branch '{branch_name}' has no remote tracking branch at origin/{branch_name}. Push the branch first."
        ) from None
    if result.stdout.strip():
        raise ScheduleDeployError(f"Branch '{branch_name}' has unpushed commits. Push the branch first.") from None


def get_current_mng_git_hash() -> str:
    """Get the git commit hash of the current mng codebase.

    Returns 'unknown' if the current directory is not inside a git repository.
    """
    try:
        return resolve_git_ref("HEAD")
    except ScheduleDeployError:
        logger.warning("Could not determine mng git hash (not in a git repository?)")
        return "unknown"
