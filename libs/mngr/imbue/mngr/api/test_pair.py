import subprocess
import time
from pathlib import Path
from typing import Any
from typing import cast

import pytest
from pydantic import Field

from imbue.imbue_common.frozen_model import FrozenModel
from imbue.imbue_common.mutable_model import MutableModel
from imbue.mngr.api.pair import UnisonSyncer
from imbue.mngr.api.pair import check_unison_installed
from imbue.mngr.api.pair import determine_git_sync_actions
from imbue.mngr.api.pair import pair_files
from imbue.mngr.api.pair import sync_git_state
from imbue.mngr.errors import MngrError
from imbue.mngr.errors import UnisonNotInstalledError
from imbue.mngr.interfaces.agent import AgentInterface
from imbue.mngr.interfaces.data_types import CommandResult
from imbue.mngr.interfaces.host import HostInterface
from imbue.mngr.primitives import ConflictMode
from imbue.mngr.primitives import SyncDirection
from imbue.mngr.primitives import UncommittedChangesMode


class _FakeAgent(FrozenModel):
    """Minimal test double for AgentInterface."""

    work_dir: Path = Field(description="Working directory for this agent")


class _FakeHost(MutableModel):
    """Minimal test double for HostInterface."""

    is_local: bool = Field(default=True, description="Whether this is a local host")

    def execute_command(
        self,
        command: str,
        cwd: Path | None = None,
    ) -> CommandResult:
        """Execute a shell command locally and return the result."""
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            cwd=cwd,
        )
        return CommandResult(
            stdout=result.stdout,
            stderr=result.stderr,
            success=result.returncode == 0,
        )


def _run_git(cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    """Run a git command in the given directory."""
    result = subprocess.run(
        ["git", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise MngrError(f"git {' '.join(args)} failed: {result.stderr}")
    return result


def _init_git_repo(path: Path) -> None:
    """Initialize a git repository with an initial commit."""
    path.mkdir(parents=True, exist_ok=True)
    _run_git(path, "init")
    _run_git(path, "config", "user.email", "test@example.com")
    _run_git(path, "config", "user.name", "Test User")
    (path / "README.md").write_text("Initial content")
    _run_git(path, "add", "README.md")
    _run_git(path, "commit", "-m", "Initial commit")


class PairTestContext(FrozenModel):
    """Shared test context for pair integration tests."""

    source_dir: Path = Field(description="Source (agent) directory")
    target_dir: Path = Field(description="Target (local) directory")
    agent: Any = Field(description="Test agent")
    host: Any = Field(description="Test host")


@pytest.fixture
def pair_ctx(tmp_path: Path) -> PairTestContext:
    """Create a test context with source and target directories as git repos."""
    source_dir = tmp_path / "source"
    target_dir = tmp_path / "target"

    # Initialize both as git repos with shared history
    _init_git_repo(source_dir)
    subprocess.run(
        ["git", "clone", str(source_dir), str(target_dir)],
        capture_output=True,
        check=True,
    )
    _run_git(target_dir, "config", "user.email", "test@example.com")
    _run_git(target_dir, "config", "user.name", "Test User")

    # Configure source to accept pushes to current branch
    _run_git(source_dir, "config", "receive.denyCurrentBranch", "ignore")

    return PairTestContext(
        source_dir=source_dir,
        target_dir=target_dir,
        agent=cast(AgentInterface, _FakeAgent(work_dir=source_dir)),
        host=cast(HostInterface, _FakeHost()),
    )


# =============================================================================
# Test: sync_git_state
# =============================================================================


def test_sync_git_state_performs_push_when_local_is_ahead(pair_ctx: PairTestContext) -> None:
    """Test that sync_git_state pushes commits from local to agent when local is ahead."""
    # Add a commit to target (local) that needs to be pushed to source (agent)
    (pair_ctx.target_dir / "new_file.txt").write_text("new content")
    _run_git(pair_ctx.target_dir, "add", "new_file.txt")
    _run_git(pair_ctx.target_dir, "commit", "-m", "Add new file")

    # In pair semantics: source=agent, target=local
    # So we call determine_git_sync_actions(agent_dir, local_dir)
    git_action = determine_git_sync_actions(pair_ctx.source_dir, pair_ctx.target_dir)
    assert git_action is not None
    # needs_pull means target (local) is ahead -> push from local to agent
    assert git_action.needs_pull is True

    git_pull_performed, git_push_performed = sync_git_state(
        agent=pair_ctx.agent,
        host=pair_ctx.host,
        agent_path=pair_ctx.source_dir,
        local_path=pair_ctx.target_dir,
        git_sync_action=git_action,
        uncommitted_changes=UncommittedChangesMode.CLOBBER,
    )

    assert git_push_performed is True
    assert git_pull_performed is False
    # Verify the file now exists in source (agent)
    assert (pair_ctx.source_dir / "new_file.txt").exists()


def test_sync_git_state_performs_pull_when_agent_is_ahead(pair_ctx: PairTestContext) -> None:
    """Test that sync_git_state pulls commits from agent to local when agent is ahead."""
    # Add a commit to source (agent) that needs to be pulled to target (local)
    (pair_ctx.source_dir / "agent_file.txt").write_text("agent content")
    _run_git(pair_ctx.source_dir, "add", "agent_file.txt")
    _run_git(pair_ctx.source_dir, "commit", "-m", "Add agent file")

    # In pair semantics: source=agent, target=local
    git_action = determine_git_sync_actions(pair_ctx.source_dir, pair_ctx.target_dir)
    assert git_action is not None
    # needs_push means source (agent) is ahead -> pull from agent to local
    assert git_action.needs_push is True

    git_pull_performed, git_push_performed = sync_git_state(
        agent=pair_ctx.agent,
        host=pair_ctx.host,
        agent_path=pair_ctx.source_dir,
        local_path=pair_ctx.target_dir,
        git_sync_action=git_action,
        uncommitted_changes=UncommittedChangesMode.CLOBBER,
    )

    assert git_pull_performed is True
    assert git_push_performed is False
    # Verify the file now exists in target (local)
    assert (pair_ctx.target_dir / "agent_file.txt").exists()


# =============================================================================
# Test: pair_files context manager
# =============================================================================


def test_pair_files_raises_when_unison_not_installed_and_mocked(
    pair_ctx: PairTestContext,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test that pair_files raises UnisonNotInstalledError when unison is not available."""
    # Mock check_unison_installed to return False
    monkeypatch.setattr("imbue.mngr.api.pair.check_unison_installed", lambda: False)

    with pytest.raises(UnisonNotInstalledError):
        with pair_files(
            agent=pair_ctx.agent,
            host=pair_ctx.host,
            source_path=pair_ctx.source_dir,
            target_path=pair_ctx.target_dir,
            is_require_git=False,
        ):
            pass


def test_pair_files_raises_when_git_required_but_not_present(
    tmp_path: Path,
) -> None:
    """Test that pair_files raises MngrError when git is required but directories are not repos."""
    source_dir = tmp_path / "source"
    target_dir = tmp_path / "target"
    source_dir.mkdir()
    target_dir.mkdir()

    agent = cast(AgentInterface, _FakeAgent(work_dir=source_dir))
    host = cast(HostInterface, _FakeHost())

    with pytest.raises(MngrError) as exc_info:
        with pair_files(
            agent=agent,
            host=host,
            source_path=source_dir,
            target_path=target_dir,
            is_require_git=True,
        ):
            pass

    assert "Git repositories required" in str(exc_info.value)


@pytest.mark.skipif(not check_unison_installed(), reason="unison not installed")
def test_pair_files_starts_and_stops_syncer(pair_ctx: PairTestContext) -> None:
    """Test that pair_files properly starts and stops the unison syncer."""
    with pair_files(
        agent=pair_ctx.agent,
        host=pair_ctx.host,
        source_path=pair_ctx.source_dir,
        target_path=pair_ctx.target_dir,
        is_require_git=True,
        uncommitted_changes=UncommittedChangesMode.CLOBBER,
    ) as syncer:
        # Give unison a moment to start
        time.sleep(0.5)

        # Syncer should be running
        assert syncer.is_running is True

        # Stop it manually
        syncer.stop()

        # Give it a moment to stop
        time.sleep(0.5)

        # Syncer should not be running
        assert syncer.is_running is False


@pytest.mark.skipif(not check_unison_installed(), reason="unison not installed")
def test_pair_files_syncs_git_state_before_starting(pair_ctx: PairTestContext) -> None:
    """Test that pair_files syncs git state before starting continuous sync."""
    # Add a commit to source (agent) that should be pulled to target
    (pair_ctx.source_dir / "agent_commit.txt").write_text("agent content")
    _run_git(pair_ctx.source_dir, "add", "agent_commit.txt")
    _run_git(pair_ctx.source_dir, "commit", "-m", "Add agent commit")

    # Verify file doesn't exist in target yet
    assert not (pair_ctx.target_dir / "agent_commit.txt").exists()

    with pair_files(
        agent=pair_ctx.agent,
        host=pair_ctx.host,
        source_path=pair_ctx.source_dir,
        target_path=pair_ctx.target_dir,
        is_require_git=True,
        uncommitted_changes=UncommittedChangesMode.CLOBBER,
    ) as syncer:
        # Git sync should have happened before unison started
        # The file should now exist in target
        assert (pair_ctx.target_dir / "agent_commit.txt").exists()

        # Stop immediately - we just want to test git sync
        syncer.stop()


@pytest.mark.skipif(not check_unison_installed(), reason="unison not installed")
def test_pair_files_with_no_git_requirement(tmp_path: Path) -> None:
    """Test that pair_files works without git when is_require_git=False."""
    source_dir = tmp_path / "source"
    target_dir = tmp_path / "target"
    source_dir.mkdir()
    target_dir.mkdir()

    # Create a file in source
    (source_dir / "test_file.txt").write_text("test content")

    agent = cast(AgentInterface, _FakeAgent(work_dir=source_dir))
    host = cast(HostInterface, _FakeHost())

    with pair_files(
        agent=agent,
        host=host,
        source_path=source_dir,
        target_path=target_dir,
        is_require_git=False,
    ) as syncer:
        # Give unison a moment to start and sync
        time.sleep(1.0)

        # Syncer should be running
        assert syncer.is_running is True

        syncer.stop()


# =============================================================================
# Test: UnisonSyncer with actual unison
# =============================================================================


@pytest.mark.skipif(not check_unison_installed(), reason="unison not installed")
def test_unison_syncer_start_and_stop(tmp_path: Path) -> None:
    """Test that UnisonSyncer can start and stop unison process."""
    source = tmp_path / "source"
    target = tmp_path / "target"
    source.mkdir()
    target.mkdir()

    syncer = UnisonSyncer(
        source_path=source,
        target_path=target,
        sync_direction=SyncDirection.BOTH,
        conflict_mode=ConflictMode.NEWER,
    )

    try:
        syncer.start()

        # Give unison a moment to start
        time.sleep(0.5)

        assert syncer.is_running is True
    finally:
        syncer.stop()

    # Give it a moment to fully stop
    time.sleep(0.5)
    assert syncer.is_running is False


@pytest.mark.skipif(not check_unison_installed(), reason="unison not installed")
def test_unison_syncer_syncs_file_changes(tmp_path: Path) -> None:
    """Test that UnisonSyncer actually syncs file changes."""
    source = tmp_path / "source"
    target = tmp_path / "target"
    source.mkdir()
    target.mkdir()

    # Create initial file in source
    (source / "initial.txt").write_text("initial content")

    syncer = UnisonSyncer(
        source_path=source,
        target_path=target,
        sync_direction=SyncDirection.BOTH,
        conflict_mode=ConflictMode.NEWER,
    )

    try:
        syncer.start()

        # Wait for initial sync
        for _ in range(20):
            if (target / "initial.txt").exists():
                break
            time.sleep(0.25)

        # File should be synced to target
        assert (target / "initial.txt").exists()
        assert (target / "initial.txt").read_text() == "initial content"
    finally:
        syncer.stop()
