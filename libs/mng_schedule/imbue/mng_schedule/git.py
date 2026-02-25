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


def get_current_mng_git_hash() -> str:
    """Get the git commit hash of the current mng codebase.

    Returns 'unknown' if the current directory is not inside a git repository.
    """
    try:
        return resolve_git_ref("HEAD")
    except ScheduleDeployError:
        logger.warning("Could not determine mng git hash (not in a git repository?)")
        return "unknown"
