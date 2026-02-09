import shutil
import subprocess
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Final
from typing import Iterator
from typing import assert_never

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
from imbue.mngr.utils.git_utils import get_head_commit
from imbue.mngr.utils.git_utils import is_ancestor
from imbue.mngr.utils.git_utils import is_git_repository

_GIT_FETCH_TIMEOUT_SECONDS: Final[float] = 30.0


class GitSyncAction(FrozenModel):
    """Describes which side (agent or local) has commits the other doesn't."""

    agent_is_ahead: bool = Field(
        default=False,
        description="True if agent has commits that local doesn't have",
    )
    local_is_ahead: bool = Field(
        default=False,
        description="True if local has commits that agent doesn't have",
    )
    agent_branch: str = Field(
        description="The branch name on the agent side",
    )
    local_branch: str = Field(
        description="The branch name on the local side",
    )


class UnisonSyncer(MutableModel):
    """Manages a unison process for continuous bidirectional file synchronization."""

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
        match self.conflict_mode:
            case ConflictMode.SOURCE:
                cmd.extend(["-prefer", str(self.source_path)])
            case ConflictMode.TARGET:
                cmd.extend(["-prefer", str(self.target_path)])
            case ConflictMode.NEWER:
                cmd.extend(["-prefer", "newer"])
            case ConflictMode.ASK:
                raise NotImplementedError("ConflictMode.ASK is not yet implemented")
            case _ as unreachable:
                assert_never(unreachable)

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

        try:
            for line in iter(self._process.stdout.readline, ""):
                if self._stop_event.is_set():
                    break
                stripped_line = line.rstrip()
                if stripped_line:
                    logger.debug("unison: {}", stripped_line)
        except (OSError, ValueError):
            # OSError: broken pipe / I/O error when process terminates
            # ValueError: I/O operation on closed file
            logger.debug("unison output reader stopped")

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
    """Check if unison and unison-fsmonitor are available in PATH."""
    return shutil.which("unison") is not None and shutil.which("unison-fsmonitor") is not None


def determine_git_sync_actions(
    agent_path: Path,
    local_path: Path,
) -> GitSyncAction | None:
    """Determine what git sync actions are needed between agent and local repos.

    Returns None if either path is not a git repository. Fetches objects from
    local into agent's object store (a read-only side effect on agent's repo)
    to enable ancestry comparison.
    """
    if not is_git_repository(agent_path) or not is_git_repository(local_path):
        return None

    agent_branch = get_current_branch(agent_path)
    local_branch = get_current_branch(local_path)

    agent_commit = get_head_commit(agent_path)
    local_commit = get_head_commit(local_path)

    if agent_commit is None or local_commit is None:
        return GitSyncAction(
            agent_branch=agent_branch,
            local_branch=local_branch,
        )

    if agent_commit == local_commit:
        return GitSyncAction(
            agent_branch=agent_branch,
            local_branch=local_branch,
        )

    # Fetch local refs into agent's object store so we can compare ancestry.
    # This only adds git objects -- it does not modify branches or working tree.
    fetch_result = subprocess.run(
        ["git", "fetch", str(local_path), local_branch],
        cwd=agent_path,
        capture_output=True,
        text=True,
        timeout=_GIT_FETCH_TIMEOUT_SECONDS,
    )
    if fetch_result.returncode != 0:
        logger.warning(
            "Failed to fetch from local for git sync comparison: {}",
            fetch_result.stderr.strip(),
        )
        return GitSyncAction(
            agent_branch=agent_branch,
            local_branch=local_branch,
        )

    # Check ancestry from the agent repo (which now has both sets of objects)
    agent_ahead = is_ancestor(agent_path, local_commit, agent_commit)
    local_ahead = is_ancestor(agent_path, agent_commit, local_commit)

    if agent_ahead and not local_ahead:
        return GitSyncAction(
            agent_is_ahead=True,
            agent_branch=agent_branch,
            local_branch=local_branch,
        )
    elif local_ahead and not agent_ahead:
        return GitSyncAction(
            local_is_ahead=True,
            agent_branch=agent_branch,
            local_branch=local_branch,
        )
    else:
        return GitSyncAction(
            agent_is_ahead=True,
            local_is_ahead=True,
            agent_branch=agent_branch,
            local_branch=local_branch,
        )


def sync_git_state(
    agent: AgentInterface,
    host: OnlineHostInterface,
    local_path: Path,
    git_sync_action: GitSyncAction,
    uncommitted_changes: UncommittedChangesMode,
) -> tuple[bool, bool]:
    """Synchronize git state between agent and local paths.

    Returns (did_pull, did_push) indicating which operations were performed.
    """
    did_pull = False
    did_push = False

    if git_sync_action.agent_is_ahead:
        logger.debug("Pulling git state from agent to local")
        pull_git(
            agent=agent,
            host=host,
            destination=local_path,
            source_branch=git_sync_action.agent_branch,
            target_branch=git_sync_action.local_branch,
            uncommitted_changes=uncommitted_changes,
        )
        did_pull = True

    if git_sync_action.local_is_ahead:
        logger.debug("Pushing git state from local to agent")
        push_git(
            agent=agent,
            host=host,
            source=local_path,
            source_branch=git_sync_action.local_branch,
            target_branch=git_sync_action.agent_branch,
            uncommitted_changes=uncommitted_changes,
        )
        did_push = True

    return did_pull, did_push


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

    # Validate directories exist
    if not source_path.is_dir():
        raise MngrError(f"Source directory does not exist: {source_path}")
    if not actual_target.is_dir():
        raise MngrError(f"Target directory does not exist: {actual_target}")

    # Validate source and target are different directories
    if source_path.resolve() == actual_target.resolve():
        raise MngrError(
            f"Source and target are the same directory: {source_path.resolve()}. "
            "Pair requires two different directories to sync between."
        )

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
    if source_is_git and target_is_git:
        git_action = determine_git_sync_actions(source_path, actual_target)
        if git_action is not None and (git_action.agent_is_ahead or git_action.local_is_ahead):
            logger.info(
                "Synchronizing git state (agent_ahead={}, local_ahead={})",
                git_action.agent_is_ahead,
                git_action.local_is_ahead,
            )
            sync_git_state(
                agent=agent,
                host=host,
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
