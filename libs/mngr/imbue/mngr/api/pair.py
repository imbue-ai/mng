import shutil
import subprocess
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from loguru import logger
from pydantic import Field
from pydantic import PrivateAttr

from imbue.imbue_common.frozen_model import FrozenModel
from imbue.imbue_common.mutable_model import MutableModel
from imbue.mngr.api.pull import pull_git
from imbue.mngr.api.push import push_git
from imbue.mngr.errors import MngrError
from imbue.mngr.errors import UnisonNotInstalledError
from imbue.mngr.interfaces.agent import AgentInterface
from imbue.mngr.interfaces.host import OnlineHostInterface
from imbue.mngr.primitives import ConflictMode
from imbue.mngr.primitives import SyncDirection
from imbue.mngr.primitives import UncommittedChangesMode
from imbue.mngr.utils.git_utils import get_current_branch
from imbue.mngr.utils.git_utils import is_git_repository


class GitSyncAction(FrozenModel):
    """Describes the git sync state between two repositories.

    This class describes which repository (source or target) has commits
    that the other doesn't. The caller is responsible for determining
    what actions to take based on this state.
    """

    source_is_ahead: bool = Field(
        default=False,
        description="True if source has commits that target doesn't have",
    )
    target_is_ahead: bool = Field(
        default=False,
        description="True if target has commits that source doesn't have",
    )
    source_branch: str = Field(
        description="The branch name on the source side",
    )
    target_branch: str = Field(
        description="The branch name on the target side",
    )


class UnisonSyncer(MutableModel):
    """Context manager for running unison file synchronization.

    This class manages a unison process that continuously syncs files between
    a source and target directory. The sync can be stopped programmatically
    by calling the stop() method, or automatically when the context manager exits.
    """

    source_path: Path = Field(frozen=True, description="Source directory to sync from")
    target_path: Path = Field(frozen=True, description="Target directory to sync to")
    sync_direction: SyncDirection = Field(
        frozen=True,
        default=SyncDirection.BOTH,
        description="Direction of sync: forward, reverse, or both",
    )
    conflict_mode: ConflictMode = Field(
        frozen=True,
        default=ConflictMode.NEWER,
        description="How to resolve conflicts",
    )
    exclude_patterns: tuple[str, ...] = Field(
        frozen=True,
        default=(),
        description="Glob patterns to exclude from sync",
    )
    include_patterns: tuple[str, ...] = Field(
        frozen=True,
        default=(),
        description="Glob patterns to include in sync",
    )
    _process: subprocess.Popen | None = PrivateAttr(default=None)
    _stop_event: threading.Event = PrivateAttr(default_factory=threading.Event)
    _output_thread: threading.Thread | None = PrivateAttr(default=None)

    model_config = {"arbitrary_types_allowed": True}

    def _build_unison_command(self) -> list[str]:
        """Build the unison command line arguments."""
        cmd = [
            "unison",
            str(self.source_path),
            str(self.target_path),
            "-repeat",
            "watch",
            "-auto",
            "-batch",
            "-ignore",
            "Name .git",
        ]

        # Add conflict preference based on mode
        if self.conflict_mode == ConflictMode.SOURCE:
            cmd.extend(["-prefer", str(self.source_path)])
        elif self.conflict_mode == ConflictMode.TARGET:
            cmd.extend(["-prefer", str(self.target_path)])
        elif self.conflict_mode == ConflictMode.NEWER:
            cmd.extend(["-prefer", "newer"])
        else:
            # ConflictMode.ASK requires interactive mode, default to newer
            cmd.extend(["-prefer", "newer"])

        # Add sync direction constraints
        if self.sync_direction == SyncDirection.FORWARD:
            cmd.extend(["-force", str(self.source_path)])
        elif self.sync_direction == SyncDirection.REVERSE:
            cmd.extend(["-force", str(self.target_path)])
        else:
            # SyncDirection.BOTH - bidirectional sync, no force flag needed
            pass

        # Add exclude patterns
        for pattern in self.exclude_patterns:
            cmd.extend(["-ignore", f"Name {pattern}"])

        # Add include patterns
        for pattern in self.include_patterns:
            cmd.extend(["-path", pattern])

        return cmd

    def _read_output(self) -> None:
        """Read and log output from the unison process."""
        if self._process is None or self._process.stdout is None:
            return

        for line in iter(self._process.stdout.readline, ""):
            if self._stop_event.is_set():
                break
            line = line.rstrip()
            if line:
                logger.debug("unison: {}", line)

    def start(self) -> None:
        """Start the unison sync process."""
        cmd = self._build_unison_command()
        logger.debug("Starting unison with command: {}", " ".join(cmd))

        self._process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )

        # Start a thread to read and log output
        self._output_thread = threading.Thread(
            target=self._read_output,
            daemon=True,
        )
        self._output_thread.start()

        logger.info("Started continuous sync between {} and {}", self.source_path, self.target_path)

    def stop(self) -> None:
        """Stop the unison sync process gracefully."""
        self._stop_event.set()

        if self._process is not None:
            logger.debug("Stopping unison process")
            # Send SIGTERM for graceful shutdown
            self._process.terminate()
            try:
                self._process.wait(timeout=5.0)
            except subprocess.TimeoutExpired:
                logger.warning("unison did not terminate gracefully, killing")
                self._process.kill()
                self._process.wait()

            self._process = None

        if self._output_thread is not None and self._output_thread.is_alive():
            self._output_thread.join(timeout=1.0)
            self._output_thread = None

        logger.info("Stopped continuous sync")

    def wait(self) -> int:
        """Wait for the unison process to complete and return the exit code."""
        if self._process is None:
            return 0
        return self._process.wait()

    @property
    def is_running(self) -> bool:
        """Check if the unison process is currently running."""
        if self._process is None:
            return False
        return self._process.poll() is None


def check_unison_installed() -> bool:
    """Check if unison is installed and available in PATH."""
    return shutil.which("unison") is not None


def _get_commit_hash(path: Path) -> str | None:
    """Get the current HEAD commit hash for a repository."""
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=path,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return None
    return result.stdout.strip()


def _get_remote_commit_hash(local_path: Path, remote_path: Path, branch: str) -> str | None:
    """Get the commit hash of a branch from a remote repository.

    Uses git ls-remote directly with the path, avoiding the need to add a temporary remote.
    """
    result = subprocess.run(
        ["git", "ls-remote", str(remote_path), branch],
        cwd=local_path,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0 or not result.stdout.strip():
        return None

    # Output format: "<hash>\t<ref>"
    return result.stdout.strip().split()[0]


def _is_ancestor(path: Path, ancestor_commit: str, descendant_commit: str) -> bool:
    """Check if ancestor_commit is an ancestor of descendant_commit."""
    result = subprocess.run(
        ["git", "merge-base", "--is-ancestor", ancestor_commit, descendant_commit],
        cwd=path,
        capture_output=True,
        text=True,
    )
    return result.returncode == 0


def determine_git_sync_actions(
    source_path: Path,
    target_path: Path,
) -> GitSyncAction | None:
    """Determine what git sync actions are needed between source and target.

    Returns None if either path is not a git repository.
    """
    # Check if both paths are git repositories
    if not is_git_repository(source_path) or not is_git_repository(target_path):
        return None

    source_branch = get_current_branch(source_path)
    target_branch = get_current_branch(target_path)

    source_commit = _get_commit_hash(source_path)
    target_commit = _get_commit_hash(target_path)

    if source_commit is None or target_commit is None:
        return GitSyncAction(
            source_is_ahead=False,
            target_is_ahead=False,
            source_branch=source_branch,
            target_branch=target_branch,
        )

    # Check if commits are the same (already in sync)
    if source_commit == target_commit:
        return GitSyncAction(
            source_is_ahead=False,
            target_is_ahead=False,
            source_branch=source_branch,
            target_branch=target_branch,
        )

    # Fetch target refs to compare
    # We need to determine if:
    # 1. Source is ahead of target (needs push)
    # 2. Target is ahead of source (needs pull)
    # 3. Both have diverged (needs both or conflict resolution)

    # Fetch from target directly (without adding a remote) to get the objects
    # This makes the target commit available locally for ancestry checks
    subprocess.run(
        ["git", "fetch", str(target_path), target_branch],
        cwd=source_path,
        capture_output=True,
        text=True,
    )

    # Check if source is ahead of target (target commit is ancestor of source)
    source_ahead = _is_ancestor(source_path, target_commit, source_commit)

    # Check if target is ahead of source (source commit is ancestor of target)
    target_ahead = _is_ancestor(source_path, source_commit, target_commit)

    if source_ahead and not target_ahead:
        # Source has commits that target doesn't - need push
        return GitSyncAction(
            source_is_ahead=True,
            target_is_ahead=False,
            source_branch=source_branch,
            target_branch=target_branch,
        )
    elif target_ahead and not source_ahead:
        # Target has commits that source doesn't - need pull
        return GitSyncAction(
            source_is_ahead=False,
            target_is_ahead=True,
            source_branch=source_branch,
            target_branch=target_branch,
        )
    else:
        # Both have diverged - need both operations
        return GitSyncAction(
            source_is_ahead=True,
            target_is_ahead=True,
            source_branch=source_branch,
            target_branch=target_branch,
        )


def sync_git_state(
    agent: AgentInterface,
    host: OnlineHostInterface,
    agent_path: Path,
    local_path: Path,
    git_sync_action: GitSyncAction,
    uncommitted_changes: UncommittedChangesMode,
) -> tuple[bool, bool]:
    """Synchronize git state between agent and local paths.

    The git_sync_action determines what operations are needed:
    - source_is_ahead: agent (source) has commits local doesn't -> pull from agent to local
    - target_is_ahead: local (target) has commits agent doesn't -> push from local to agent

    Note: The naming in GitSyncAction (source_is_ahead/target_is_ahead) refers to the direction
    of data flow relative to the source/target passed to determine_git_sync_actions.
    Since source=agent and target=local in our calling convention:
    - source_is_ahead (source ahead) means we need to bring local up to date -> pull_git
    - target_is_ahead (target ahead) means we need to bring agent up to date -> push_git

    Returns a tuple of (git_pull_performed, git_push_performed) where:
    - git_pull_performed: True if we pulled from agent to local
    - git_push_performed: True if we pushed from local to agent
    """
    git_pull_performed = False
    git_push_performed = False

    # If agent (source) has commits local doesn't -> pull from agent to local
    if git_sync_action.source_is_ahead:
        logger.debug("Pulling git state from agent to local")
        pull_git(
            agent=agent,
            host=host,
            destination=local_path,
            source_branch=git_sync_action.source_branch,
            target_branch=git_sync_action.target_branch,
            uncommitted_changes=uncommitted_changes,
        )
        git_pull_performed = True

    # If local (target) has commits agent doesn't -> push from local to agent
    if git_sync_action.target_is_ahead:
        logger.debug("Pushing git state from local to agent")
        push_git(
            agent=agent,
            host=host,
            source=local_path,
            source_branch=git_sync_action.target_branch,
            target_branch=git_sync_action.source_branch,
            uncommitted_changes=uncommitted_changes,
        )
        git_push_performed = True

    return git_pull_performed, git_push_performed


@contextmanager
def pair_files(
    agent: AgentInterface,
    host: OnlineHostInterface,
    source_path: Path,
    target_path: Path | None = None,
    sync_direction: SyncDirection = SyncDirection.BOTH,
    conflict_mode: ConflictMode = ConflictMode.NEWER,
    is_require_git: bool = True,
    uncommitted_changes: UncommittedChangesMode = UncommittedChangesMode.FAIL,
    exclude_patterns: tuple[str, ...] = (),
    include_patterns: tuple[str, ...] = (),
) -> Iterator[UnisonSyncer]:
    """Start continuous file synchronization between source and agent.

    This function first synchronizes git state if both paths are git repositories,
    then starts a unison process for continuous file synchronization.

    The returned context manager yields a UnisonSyncer that can be used to
    programmatically stop the sync. The sync is automatically stopped when
    the context manager exits.
    """
    # Check unison is installed
    if not check_unison_installed():
        raise UnisonNotInstalledError()

    # Determine target path
    actual_target = target_path if target_path is not None else agent.work_dir

    # Check git requirements
    source_is_git = is_git_repository(source_path)
    target_is_git = is_git_repository(actual_target)

    if is_require_git and not (source_is_git and target_is_git):
        missing = []
        if not source_is_git:
            missing.append(f"source ({source_path})")
        if not target_is_git:
            missing.append(f"target ({actual_target})")
        raise MngrError(
            f"Git repositories required but not found in: {', '.join(missing)}. "
            "Use --no-require-git to sync without git."
        )

    # Determine and perform git sync
    git_push_performed = False
    git_pull_performed = False

    if source_is_git and target_is_git:
        git_action = determine_git_sync_actions(source_path, actual_target)
        if git_action is not None and (git_action.source_is_ahead or git_action.target_is_ahead):
            logger.info(
                "Synchronizing git state (agent_ahead={}, local_ahead={})",
                git_action.source_is_ahead,
                git_action.target_is_ahead,
            )
            git_pull_performed, git_push_performed = sync_git_state(
                agent=agent,
                host=host,
                agent_path=source_path,
                local_path=actual_target,
                git_sync_action=git_action,
                uncommitted_changes=uncommitted_changes,
            )

    # Create and start the syncer
    syncer = UnisonSyncer(
        source_path=source_path,
        target_path=actual_target,
        sync_direction=sync_direction,
        conflict_mode=conflict_mode,
        exclude_patterns=exclude_patterns,
        include_patterns=include_patterns,
    )

    try:
        syncer.start()
        yield syncer
    finally:
        # Ensure the syncer is stopped when the context exits
        if syncer.is_running:
            syncer.stop()
