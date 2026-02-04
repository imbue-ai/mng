"""Push API for syncing from local to agent - thin wrappers around sync module."""

from pathlib import Path

from imbue.mngr.api.sync import SyncFilesResult
from imbue.mngr.api.sync import SyncGitResult
from imbue.mngr.api.sync import SyncMode
from imbue.mngr.api.sync import sync_files
from imbue.mngr.api.sync import sync_git
from imbue.mngr.interfaces.agent import AgentInterface
from imbue.mngr.interfaces.host import OnlineHostInterface
from imbue.mngr.primitives import UncommittedChangesMode


def push_files(
    agent: AgentInterface,
    host: OnlineHostInterface,
    source: Path,
    destination_path: Path | None = None,
    dry_run: bool = False,
    delete: bool = False,
    uncommitted_changes: UncommittedChangesMode = UncommittedChangesMode.FAIL,
) -> SyncFilesResult:
    """Push files from a local directory to an agent's work directory using rsync."""
    return sync_files(
        agent=agent,
        host=host,
        mode=SyncMode.PUSH,
        local_path=source,
        remote_path=destination_path,
        dry_run=dry_run,
        delete=delete,
        uncommitted_changes=uncommitted_changes,
    )


def push_git(
    agent: AgentInterface,
    host: OnlineHostInterface,
    source: Path,
    source_branch: str | None = None,
    target_branch: str | None = None,
    dry_run: bool = False,
    uncommitted_changes: UncommittedChangesMode = UncommittedChangesMode.FAIL,
    mirror: bool = False,
) -> SyncGitResult:
    """Push git commits from a local repository to an agent's repository."""
    return sync_git(
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
