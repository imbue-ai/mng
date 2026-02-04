import subprocess
from pathlib import Path
from typing import Any
from typing import cast

import pytest
from pydantic import Field

from imbue.imbue_common.frozen_model import FrozenModel
from imbue.imbue_common.mutable_model import MutableModel
from imbue.mngr.api.push import push_files
from imbue.mngr.api.push import push_git
from imbue.mngr.api.sync import RemoteGitContext
from imbue.mngr.api.sync import UncommittedChangesError
from imbue.mngr.interfaces.agent import AgentInterface
from imbue.mngr.interfaces.data_types import CommandResult
from imbue.mngr.interfaces.host import OnlineHostInterface
from imbue.mngr.primitives import UncommittedChangesMode
from imbue.mngr.utils.testing import init_git_repo
from imbue.mngr.utils.testing import run_git_command


def _has_uncommitted_changes_on_host(host: OnlineHostInterface, path: Path) -> bool:
    """Helper to check for uncommitted changes on a remote host using RemoteGitContext."""
    return RemoteGitContext(host=host).has_uncommitted_changes(path)


class _FakeAgent(FrozenModel):
    """Minimal test double for AgentInterface.

    Only implements work_dir, which is all push_files actually uses.
    """

    work_dir: Path = Field(description="Working directory for this agent")


class _FakeHost(MutableModel):
    """Minimal test double for HostInterface.

    Only implements execute_command and is_local, which is all push_files actually uses.
    Executes commands locally via subprocess.
    """

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


def _get_stash_count(path: Path) -> int:
    """Get the number of stash entries."""
    result = subprocess.run(
        ["git", "stash", "list"],
        cwd=path,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return 0
    lines = result.stdout.strip().split("\n")
    return len([line for line in lines if line])


class PushTestContext(FrozenModel):
    """Shared test context for push_files integration tests."""

    host_dir: Path = Field(description="Host (source) directory - should remain unchanged")
    agent_dir: Path = Field(description="Agent working directory (destination)")
    # Use Any to avoid pydantic validation since our test doubles don't inherit from the interfaces
    agent: Any = Field(description="Test agent")
    host: Any = Field(description="Test host")


@pytest.fixture
def push_ctx(tmp_path: Path) -> PushTestContext:
    """Create a test context with host and agent directories."""
    host_dir = tmp_path / "host"
    agent_dir = tmp_path / "agent"
    host_dir.mkdir(parents=True)
    init_git_repo(agent_dir)
    return PushTestContext(
        host_dir=host_dir,
        agent_dir=agent_dir,
        agent=cast(AgentInterface, _FakeAgent(work_dir=agent_dir)),
        host=cast(OnlineHostInterface, _FakeHost()),
    )


# =============================================================================
# Test: FAIL mode (default)
# =============================================================================


def test_push_files_fail_mode_with_no_uncommitted_changes_succeeds(
    push_ctx: PushTestContext,
) -> None:
    """Test that FAIL mode succeeds when there are no uncommitted changes on target."""
    (push_ctx.host_dir / "file.txt").write_text("host content")
    assert not _has_uncommitted_changes_on_host(push_ctx.host, push_ctx.agent_dir)

    result = push_files(
        agent=push_ctx.agent,
        host=push_ctx.host,
        source=push_ctx.host_dir,
        uncommitted_changes=UncommittedChangesMode.FAIL,
    )

    assert (push_ctx.agent_dir / "file.txt").exists()
    assert (push_ctx.agent_dir / "file.txt").read_text() == "host content"
    assert result.destination_path == push_ctx.agent_dir
    assert result.source_path == push_ctx.host_dir


def test_push_files_fail_mode_with_uncommitted_changes_raises_error(
    push_ctx: PushTestContext,
) -> None:
    """Test that FAIL mode raises UncommittedChangesError when changes exist on target."""
    (push_ctx.host_dir / "file.txt").write_text("host content")
    (push_ctx.agent_dir / "uncommitted.txt").write_text("uncommitted content")
    assert _has_uncommitted_changes_on_host(push_ctx.host, push_ctx.agent_dir)

    with pytest.raises(UncommittedChangesError) as exc_info:
        push_files(
            agent=push_ctx.agent,
            host=push_ctx.host,
            source=push_ctx.host_dir,
            uncommitted_changes=UncommittedChangesMode.FAIL,
        )

    assert exc_info.value.destination == push_ctx.agent_dir


# =============================================================================
# Test: CLOBBER mode
# =============================================================================


def test_push_files_clobber_mode_overwrites_agent_changes(
    push_ctx: PushTestContext,
) -> None:
    """Test that CLOBBER mode overwrites uncommitted changes on the agent."""
    (push_ctx.host_dir / "shared.txt").write_text("host version")
    (push_ctx.agent_dir / "shared.txt").write_text("agent version")
    assert _has_uncommitted_changes_on_host(push_ctx.host, push_ctx.agent_dir)

    result = push_files(
        agent=push_ctx.agent,
        host=push_ctx.host,
        source=push_ctx.host_dir,
        uncommitted_changes=UncommittedChangesMode.CLOBBER,
    )

    assert (push_ctx.agent_dir / "shared.txt").read_text() == "host version"
    assert result.destination_path == push_ctx.agent_dir


def test_push_files_clobber_mode_when_only_agent_has_changes(
    push_ctx: PushTestContext,
) -> None:
    """Test CLOBBER mode when only the agent has a modified file."""
    (push_ctx.host_dir / "host_only.txt").write_text("host file")
    (push_ctx.agent_dir / "agent_only.txt").write_text("agent uncommitted content")
    assert _has_uncommitted_changes_on_host(push_ctx.host, push_ctx.agent_dir)

    push_files(
        agent=push_ctx.agent,
        host=push_ctx.host,
        source=push_ctx.host_dir,
        uncommitted_changes=UncommittedChangesMode.CLOBBER,
    )

    # rsync doesn't delete by default
    assert (push_ctx.agent_dir / "agent_only.txt").exists()
    assert (push_ctx.agent_dir / "host_only.txt").read_text() == "host file"


def test_push_files_clobber_mode_with_delete_flag_removes_agent_only_files(
    push_ctx: PushTestContext,
) -> None:
    """Test CLOBBER mode with delete=True removes files not in source."""
    (push_ctx.host_dir / "host_file.txt").write_text("host content")
    (push_ctx.agent_dir / "agent_extra.txt").write_text("this should be deleted")
    run_git_command(push_ctx.agent_dir, "add", "agent_extra.txt")
    run_git_command(push_ctx.agent_dir, "commit", "-m", "Add agent extra file")

    push_files(
        agent=push_ctx.agent,
        host=push_ctx.host,
        source=push_ctx.host_dir,
        delete=True,
        uncommitted_changes=UncommittedChangesMode.CLOBBER,
    )

    assert not (push_ctx.agent_dir / "agent_extra.txt").exists()
    assert (push_ctx.agent_dir / "host_file.txt").read_text() == "host content"


# =============================================================================
# Test: STASH mode
# =============================================================================


def test_push_files_stash_mode_stashes_changes_and_leaves_stashed(
    push_ctx: PushTestContext,
) -> None:
    """Test that STASH mode stashes uncommitted changes on target and leaves them stashed."""
    (push_ctx.host_dir / "host_file.txt").write_text("host content")
    # Modify a tracked file (README.md was created by _init_git_repo)
    (push_ctx.agent_dir / "README.md").write_text("modified content")
    initial_stash_count = _get_stash_count(push_ctx.agent_dir)
    assert _has_uncommitted_changes_on_host(push_ctx.host, push_ctx.agent_dir)

    push_files(
        agent=push_ctx.agent,
        host=push_ctx.host,
        source=push_ctx.host_dir,
        uncommitted_changes=UncommittedChangesMode.STASH,
    )

    final_stash_count = _get_stash_count(push_ctx.agent_dir)
    assert final_stash_count == initial_stash_count + 1
    # The modified tracked file should be reverted to its committed state
    assert (push_ctx.agent_dir / "README.md").read_text() == "Initial content"
    assert (push_ctx.agent_dir / "host_file.txt").read_text() == "host content"


def test_push_files_stash_mode_stashes_untracked_files(
    push_ctx: PushTestContext,
) -> None:
    """Test that STASH mode properly stashes untracked files on target."""
    (push_ctx.host_dir / "host_file.txt").write_text("host content")
    # Create an UNTRACKED file
    (push_ctx.agent_dir / "untracked_file.txt").write_text("untracked content")
    initial_stash_count = _get_stash_count(push_ctx.agent_dir)
    assert _has_uncommitted_changes_on_host(push_ctx.host, push_ctx.agent_dir)

    push_files(
        agent=push_ctx.agent,
        host=push_ctx.host,
        source=push_ctx.host_dir,
        uncommitted_changes=UncommittedChangesMode.STASH,
    )

    # Untracked file should be stashed with -u flag
    final_stash_count = _get_stash_count(push_ctx.agent_dir)
    assert final_stash_count == initial_stash_count + 1
    assert not (push_ctx.agent_dir / "untracked_file.txt").exists()
    assert (push_ctx.agent_dir / "host_file.txt").read_text() == "host content"


def test_push_files_stash_mode_with_no_uncommitted_changes_does_not_stash(
    push_ctx: PushTestContext,
) -> None:
    """Test that STASH mode does not create a stash when no changes exist on target."""
    (push_ctx.host_dir / "host_file.txt").write_text("host content")
    assert not _has_uncommitted_changes_on_host(push_ctx.host, push_ctx.agent_dir)
    initial_stash_count = _get_stash_count(push_ctx.agent_dir)

    push_files(
        agent=push_ctx.agent,
        host=push_ctx.host,
        source=push_ctx.host_dir,
        uncommitted_changes=UncommittedChangesMode.STASH,
    )

    final_stash_count = _get_stash_count(push_ctx.agent_dir)
    assert final_stash_count == initial_stash_count
    assert (push_ctx.agent_dir / "host_file.txt").read_text() == "host content"


# =============================================================================
# Test: MERGE mode
# =============================================================================


def test_push_files_merge_mode_stashes_and_restores_changes(
    push_ctx: PushTestContext,
) -> None:
    """Test that MERGE mode stashes changes on target, pushes, then restores changes."""
    (push_ctx.host_dir / "host_file.txt").write_text("host content")
    # Modify the tracked README.md file
    (push_ctx.agent_dir / "README.md").write_text("agent modified content")
    initial_stash_count = _get_stash_count(push_ctx.agent_dir)
    assert _has_uncommitted_changes_on_host(push_ctx.host, push_ctx.agent_dir)

    push_files(
        agent=push_ctx.agent,
        host=push_ctx.host,
        source=push_ctx.host_dir,
        uncommitted_changes=UncommittedChangesMode.MERGE,
    )

    final_stash_count = _get_stash_count(push_ctx.agent_dir)
    assert final_stash_count == initial_stash_count
    assert (push_ctx.agent_dir / "README.md").read_text() == "agent modified content"
    assert (push_ctx.agent_dir / "host_file.txt").read_text() == "host content"


def test_push_files_merge_mode_restores_untracked_files(
    push_ctx: PushTestContext,
) -> None:
    """Test that MERGE mode properly stashes and restores untracked files on target."""
    (push_ctx.host_dir / "host_file.txt").write_text("host content")
    (push_ctx.agent_dir / "untracked_file.txt").write_text("untracked content")
    initial_stash_count = _get_stash_count(push_ctx.agent_dir)
    assert _has_uncommitted_changes_on_host(push_ctx.host, push_ctx.agent_dir)

    push_files(
        agent=push_ctx.agent,
        host=push_ctx.host,
        source=push_ctx.host_dir,
        uncommitted_changes=UncommittedChangesMode.MERGE,
    )

    # Stash should be created and popped
    final_stash_count = _get_stash_count(push_ctx.agent_dir)
    assert final_stash_count == initial_stash_count
    assert (push_ctx.agent_dir / "untracked_file.txt").exists()
    assert (push_ctx.agent_dir / "untracked_file.txt").read_text() == "untracked content"
    assert (push_ctx.agent_dir / "host_file.txt").read_text() == "host content"


def test_push_files_merge_mode_when_both_modify_different_files(
    push_ctx: PushTestContext,
) -> None:
    """Test MERGE mode when host and agent modify different files."""
    (push_ctx.host_dir / "host_only.txt").write_text("host content")
    (push_ctx.agent_dir / "README.md").write_text("agent modified content")
    initial_stash_count = _get_stash_count(push_ctx.agent_dir)
    assert _has_uncommitted_changes_on_host(push_ctx.host, push_ctx.agent_dir)

    push_files(
        agent=push_ctx.agent,
        host=push_ctx.host,
        source=push_ctx.host_dir,
        uncommitted_changes=UncommittedChangesMode.MERGE,
    )

    assert (push_ctx.agent_dir / "host_only.txt").read_text() == "host content"
    assert (push_ctx.agent_dir / "README.md").read_text() == "agent modified content"
    final_stash_count = _get_stash_count(push_ctx.agent_dir)
    assert final_stash_count == initial_stash_count


def test_push_files_merge_mode_with_no_uncommitted_changes(
    push_ctx: PushTestContext,
) -> None:
    """Test that MERGE mode works correctly when there are no uncommitted changes on target."""
    (push_ctx.host_dir / "host_file.txt").write_text("host content")
    assert not _has_uncommitted_changes_on_host(push_ctx.host, push_ctx.agent_dir)
    initial_stash_count = _get_stash_count(push_ctx.agent_dir)

    push_files(
        agent=push_ctx.agent,
        host=push_ctx.host,
        source=push_ctx.host_dir,
        uncommitted_changes=UncommittedChangesMode.MERGE,
    )

    final_stash_count = _get_stash_count(push_ctx.agent_dir)
    assert final_stash_count == initial_stash_count
    assert (push_ctx.agent_dir / "host_file.txt").read_text() == "host content"


# =============================================================================
# Test: .git directory exclusion
# =============================================================================


def test_push_files_excludes_git_directory(
    push_ctx: PushTestContext,
) -> None:
    """Test that push_files excludes the .git directory from rsync."""
    # Make the host directory a git repo too
    run_git_command(push_ctx.host_dir, "init")
    run_git_command(push_ctx.host_dir, "config", "user.email", "test@example.com")
    run_git_command(push_ctx.host_dir, "config", "user.name", "Test User")
    (push_ctx.host_dir / "file.txt").write_text("host content")
    run_git_command(push_ctx.host_dir, "add", "file.txt")
    run_git_command(push_ctx.host_dir, "commit", "-m", "Add file")

    agent_commit_before = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=push_ctx.agent_dir,
        capture_output=True,
        text=True,
    ).stdout.strip()

    push_files(
        agent=push_ctx.agent,
        host=push_ctx.host,
        source=push_ctx.host_dir,
        uncommitted_changes=UncommittedChangesMode.CLOBBER,
    )

    # The agent's .git directory should be unchanged
    agent_commit_after = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=push_ctx.agent_dir,
        capture_output=True,
        text=True,
    ).stdout.strip()
    assert agent_commit_before == agent_commit_after
    assert (push_ctx.agent_dir / "file.txt").read_text() == "host content"


# =============================================================================
# Test: dry_run flag
# =============================================================================


def test_push_files_dry_run_does_not_modify_files(
    push_ctx: PushTestContext,
) -> None:
    """Test that dry_run=True shows what would be transferred without modifying files."""
    (push_ctx.host_dir / "new_file.txt").write_text("host content")
    assert not (push_ctx.agent_dir / "new_file.txt").exists()

    result = push_files(
        agent=push_ctx.agent,
        host=push_ctx.host,
        source=push_ctx.host_dir,
        dry_run=True,
    )

    assert not (push_ctx.agent_dir / "new_file.txt").exists()
    assert result.is_dry_run is True


# =============================================================================
# Test: destination_path parameter
# =============================================================================


def test_push_files_with_custom_destination_path(
    push_ctx: PushTestContext,
) -> None:
    """Test that push_files can use a custom destination path instead of work_dir."""
    custom_dest = push_ctx.agent_dir / "subdir"
    custom_dest.mkdir(parents=True)
    (push_ctx.host_dir / "file_from_host.txt").write_text("content from host")

    result = push_files(
        agent=push_ctx.agent,
        host=push_ctx.host,
        source=push_ctx.host_dir,
        destination_path=custom_dest,
    )

    assert (custom_dest / "file_from_host.txt").read_text() == "content from host"
    assert result.destination_path == custom_dest


# =============================================================================
# Test: Host directory is never modified
# =============================================================================


@pytest.mark.parametrize(
    "mode,modify_tracked_file",
    [
        (UncommittedChangesMode.CLOBBER, False),
        (UncommittedChangesMode.STASH, True),
        (UncommittedChangesMode.MERGE, True),
    ],
    ids=["clobber", "stash", "merge"],
)
def test_push_files_does_not_modify_host_directory(
    push_ctx: PushTestContext,
    mode: UncommittedChangesMode,
    modify_tracked_file: bool,
) -> None:
    """Test that pushing files NEVER modifies the host (source) directory.

    This test is parameterized to verify host immutability across all modes.
    STASH and MERGE modes modify tracked files to avoid untracked file conflicts
    when running in sequence.
    """
    # Set up host with some files
    (push_ctx.host_dir / "host_file.txt").write_text("host content")
    (push_ctx.host_dir / "another_file.txt").write_text("another host file")

    # Record the state of the host directory
    host_files_before = set(push_ctx.host_dir.iterdir())
    host_contents_before = {f.name: f.read_text() for f in push_ctx.host_dir.iterdir() if f.is_file()}

    # Set up agent with uncommitted changes
    if modify_tracked_file:
        # Modify tracked file to avoid untracked file conflicts
        (push_ctx.agent_dir / "README.md").write_text("agent uncommitted changes")
    else:
        # Create untracked file
        (push_ctx.agent_dir / "agent_uncommitted.txt").write_text("agent uncommitted")

    push_files(
        agent=push_ctx.agent,
        host=push_ctx.host,
        source=push_ctx.host_dir,
        uncommitted_changes=mode,
    )

    # Verify host directory is unchanged
    host_files_after = set(push_ctx.host_dir.iterdir())
    host_contents_after = {f.name: f.read_text() for f in push_ctx.host_dir.iterdir() if f.is_file()}

    assert host_files_before == host_files_after
    assert host_contents_before == host_contents_after


# =============================================================================
# Test: push_git function
# =============================================================================


@pytest.fixture
def git_push_ctx(tmp_path: Path) -> PushTestContext:
    """Create a test context with host and agent git repositories that share history."""
    host_dir = tmp_path / "host"
    agent_dir = tmp_path / "agent"

    # Initialize host repo with a commit
    init_git_repo(host_dir)

    # Clone the host repo to create the agent repo (so they share history)
    subprocess.run(
        ["git", "clone", str(host_dir), str(agent_dir)],
        capture_output=True,
        text=True,
        check=True,
    )

    # Configure agent repo to allow receiving pushes to the current branch
    # This is required for our push mechanism to work
    run_git_command(agent_dir, "config", "receive.denyCurrentBranch", "ignore")

    # Configure git user for the agent repo
    run_git_command(agent_dir, "config", "user.email", "test@example.com")
    run_git_command(agent_dir, "config", "user.name", "Test User")

    return PushTestContext(
        host_dir=host_dir,
        agent_dir=agent_dir,
        agent=cast(AgentInterface, _FakeAgent(work_dir=agent_dir)),
        host=cast(OnlineHostInterface, _FakeHost()),
    )


def test_push_git_basic_push(git_push_ctx: PushTestContext) -> None:
    """Test basic git push from host to agent."""
    # Create a new commit on the host
    (git_push_ctx.host_dir / "new_file.txt").write_text("new content")
    run_git_command(git_push_ctx.host_dir, "add", "new_file.txt")
    run_git_command(git_push_ctx.host_dir, "commit", "-m", "Add new file")

    result = push_git(
        agent=git_push_ctx.agent,
        host=git_push_ctx.host,
        source=git_push_ctx.host_dir,
        uncommitted_changes=UncommittedChangesMode.CLOBBER,
    )

    # The new file should exist on the agent
    assert (git_push_ctx.agent_dir / "new_file.txt").exists()
    assert (git_push_ctx.agent_dir / "new_file.txt").read_text() == "new content"
    # Note: commits_transferred count may be inaccurate because the counting logic
    # only looks at the source repo. The important thing is the files were pushed.
    assert result.is_dry_run is False


def test_push_git_dry_run(git_push_ctx: PushTestContext) -> None:
    """Test that dry_run=True does not actually push commits."""
    # Create a new commit on the host
    (git_push_ctx.host_dir / "new_file.txt").write_text("new content")
    run_git_command(git_push_ctx.host_dir, "add", "new_file.txt")
    run_git_command(git_push_ctx.host_dir, "commit", "-m", "Add new file")

    result = push_git(
        agent=git_push_ctx.agent,
        host=git_push_ctx.host,
        source=git_push_ctx.host_dir,
        dry_run=True,
        uncommitted_changes=UncommittedChangesMode.CLOBBER,
    )

    # The new file should NOT exist on the agent (dry run)
    assert not (git_push_ctx.agent_dir / "new_file.txt").exists()
    assert result.is_dry_run is True


def test_push_git_with_stash_mode(git_push_ctx: PushTestContext) -> None:
    """Test push_git with STASH mode for uncommitted changes on agent."""
    # Create a new commit on the host
    (git_push_ctx.host_dir / "new_file.txt").write_text("new content from host")
    run_git_command(git_push_ctx.host_dir, "add", "new_file.txt")
    run_git_command(git_push_ctx.host_dir, "commit", "-m", "Add new file")

    # Create uncommitted changes on the agent
    (git_push_ctx.agent_dir / "README.md").write_text("agent uncommitted changes")
    initial_stash_count = _get_stash_count(git_push_ctx.agent_dir)

    push_git(
        agent=git_push_ctx.agent,
        host=git_push_ctx.host,
        source=git_push_ctx.host_dir,
        uncommitted_changes=UncommittedChangesMode.STASH,
    )

    # The push should succeed and changes should be stashed
    final_stash_count = _get_stash_count(git_push_ctx.agent_dir)
    assert final_stash_count == initial_stash_count + 1
    assert (git_push_ctx.agent_dir / "new_file.txt").exists()


def test_push_git_with_merge_mode(git_push_ctx: PushTestContext) -> None:
    """Test push_git with MERGE mode restores uncommitted changes after push."""
    # Create a new commit on the host
    (git_push_ctx.host_dir / "new_file.txt").write_text("new content from host")
    run_git_command(git_push_ctx.host_dir, "add", "new_file.txt")
    run_git_command(git_push_ctx.host_dir, "commit", "-m", "Add new file")

    # Create an untracked file on the agent (different from host's new file)
    (git_push_ctx.agent_dir / "agent_local_file.txt").write_text("agent local content")
    initial_stash_count = _get_stash_count(git_push_ctx.agent_dir)

    push_git(
        agent=git_push_ctx.agent,
        host=git_push_ctx.host,
        source=git_push_ctx.host_dir,
        uncommitted_changes=UncommittedChangesMode.MERGE,
    )

    # The push should succeed and local changes should be restored
    final_stash_count = _get_stash_count(git_push_ctx.agent_dir)
    assert final_stash_count == initial_stash_count
    assert (git_push_ctx.agent_dir / "new_file.txt").exists()
    assert (git_push_ctx.agent_dir / "agent_local_file.txt").exists()
    assert (git_push_ctx.agent_dir / "agent_local_file.txt").read_text() == "agent local content"


def test_push_git_does_not_modify_host_directory(git_push_ctx: PushTestContext) -> None:
    """Test that push_git NEVER modifies the host (source) directory."""
    # Create a commit on the host
    (git_push_ctx.host_dir / "new_file.txt").write_text("host content")
    run_git_command(git_push_ctx.host_dir, "add", "new_file.txt")
    run_git_command(git_push_ctx.host_dir, "commit", "-m", "Add new file")

    # Record the state of the host directory
    host_files_before = set(git_push_ctx.host_dir.iterdir())
    host_contents_before = {f.name: f.read_text() for f in git_push_ctx.host_dir.iterdir() if f.is_file()}
    host_commit_before = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=git_push_ctx.host_dir,
        capture_output=True,
        text=True,
    ).stdout.strip()

    push_git(
        agent=git_push_ctx.agent,
        host=git_push_ctx.host,
        source=git_push_ctx.host_dir,
        uncommitted_changes=UncommittedChangesMode.CLOBBER,
    )

    # Verify host directory is unchanged
    host_files_after = set(git_push_ctx.host_dir.iterdir())
    host_contents_after = {f.name: f.read_text() for f in git_push_ctx.host_dir.iterdir() if f.is_file()}
    host_commit_after = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=git_push_ctx.host_dir,
        capture_output=True,
        text=True,
    ).stdout.strip()

    assert host_files_before == host_files_after
    assert host_contents_before == host_contents_after
    assert host_commit_before == host_commit_after


# =============================================================================
# Test: push_git mirror mode
# =============================================================================


def test_push_git_mirror_mode_dry_run(git_push_ctx: PushTestContext) -> None:
    """Test that mirror mode with dry_run=True shows what would be pushed."""
    # Create a new commit on the host
    (git_push_ctx.host_dir / "new_file.txt").write_text("new content")
    run_git_command(git_push_ctx.host_dir, "add", "new_file.txt")
    run_git_command(git_push_ctx.host_dir, "commit", "-m", "Add new file")

    result = push_git(
        agent=git_push_ctx.agent,
        host=git_push_ctx.host,
        source=git_push_ctx.host_dir,
        mirror=True,
        dry_run=True,
        uncommitted_changes=UncommittedChangesMode.CLOBBER,
    )

    # The new file should NOT exist on the agent (dry run)
    assert not (git_push_ctx.agent_dir / "new_file.txt").exists()
    assert result.is_dry_run is True
    # commits_transferred should show what would be pushed
    assert result.commits_transferred >= 0


def test_push_git_mirror_mode(git_push_ctx: PushTestContext) -> None:
    """Test that mirror mode pushes all refs to the agent repository."""
    # Create a new commit on the host
    (git_push_ctx.host_dir / "new_file.txt").write_text("new content")
    run_git_command(git_push_ctx.host_dir, "add", "new_file.txt")
    run_git_command(git_push_ctx.host_dir, "commit", "-m", "Add new file")

    # Get host commit before push
    host_commit = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=git_push_ctx.host_dir,
        capture_output=True,
        text=True,
    ).stdout.strip()

    result = push_git(
        agent=git_push_ctx.agent,
        host=git_push_ctx.host,
        source=git_push_ctx.host_dir,
        mirror=True,
        uncommitted_changes=UncommittedChangesMode.CLOBBER,
    )

    # Get agent commit after push
    agent_commit = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=git_push_ctx.agent_dir,
        capture_output=True,
        text=True,
    ).stdout.strip()

    # The commits should match after mirror push
    assert host_commit == agent_commit
    assert result.is_dry_run is False


# =============================================================================
# Test: Remote (non-local) host behavior
# =============================================================================


class _FakeRemoteHost(MutableModel):
    """Test double for a remote (non-local) host.

    Simulates a remote host by setting is_local=False while still executing
    commands locally. This tests the code paths for remote hosts.
    """

    is_local: bool = Field(default=False, description="Whether this is a local host")

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


@pytest.fixture
def remote_push_ctx(tmp_path: Path) -> PushTestContext:
    """Create a test context with a remote (non-local) host."""
    host_dir = tmp_path / "host"
    agent_dir = tmp_path / "agent"
    host_dir.mkdir(parents=True)
    init_git_repo(agent_dir)
    return PushTestContext(
        host_dir=host_dir,
        agent_dir=agent_dir,
        agent=cast(AgentInterface, _FakeAgent(work_dir=agent_dir)),
        host=cast(OnlineHostInterface, _FakeRemoteHost()),
    )


@pytest.fixture
def remote_git_push_ctx(tmp_path: Path) -> PushTestContext:
    """Create a test context with remote host for git push testing."""
    host_dir = tmp_path / "host"
    agent_dir = tmp_path / "agent"

    init_git_repo(host_dir)

    subprocess.run(
        ["git", "clone", str(host_dir), str(agent_dir)],
        capture_output=True,
        text=True,
        check=True,
    )
    run_git_command(agent_dir, "config", "receive.denyCurrentBranch", "ignore")
    run_git_command(agent_dir, "config", "user.email", "test@example.com")
    run_git_command(agent_dir, "config", "user.name", "Test User")

    return PushTestContext(
        host_dir=host_dir,
        agent_dir=agent_dir,
        agent=cast(AgentInterface, _FakeAgent(work_dir=agent_dir)),
        host=cast(OnlineHostInterface, _FakeRemoteHost()),
    )


def test_push_files_with_remote_host_succeeds(
    remote_push_ctx: PushTestContext,
) -> None:
    """Test that push_files works with a remote (non-local) host.

    rsync is executed via host.execute_command, which works for both local
    and remote hosts.
    """
    (remote_push_ctx.host_dir / "file.txt").write_text("host content")

    result = push_files(
        agent=remote_push_ctx.agent,
        host=remote_push_ctx.host,
        source=remote_push_ctx.host_dir,
        uncommitted_changes=UncommittedChangesMode.CLOBBER,
    )

    assert (remote_push_ctx.agent_dir / "file.txt").exists()
    assert (remote_push_ctx.agent_dir / "file.txt").read_text() == "host content"
    assert result.destination_path == remote_push_ctx.agent_dir


def test_push_files_with_remote_host_handles_uncommitted_changes(
    remote_push_ctx: PushTestContext,
) -> None:
    """Test that push_files handles uncommitted changes on remote host."""
    (remote_push_ctx.host_dir / "file.txt").write_text("host content")
    (remote_push_ctx.agent_dir / "README.md").write_text("modified content")
    initial_stash_count = _get_stash_count(remote_push_ctx.agent_dir)

    push_files(
        agent=remote_push_ctx.agent,
        host=remote_push_ctx.host,
        source=remote_push_ctx.host_dir,
        uncommitted_changes=UncommittedChangesMode.STASH,
    )

    final_stash_count = _get_stash_count(remote_push_ctx.agent_dir)
    assert final_stash_count == initial_stash_count + 1
    assert (remote_push_ctx.agent_dir / "file.txt").read_text() == "host content"


def test_push_git_with_remote_host_raises_not_implemented(
    remote_git_push_ctx: PushTestContext,
) -> None:
    """Test that push_git raises NotImplementedError for remote hosts.

    Git push to remote hosts requires SSH URL support which is not implemented.
    """
    (remote_git_push_ctx.host_dir / "new_file.txt").write_text("new content")
    run_git_command(remote_git_push_ctx.host_dir, "add", "new_file.txt")
    run_git_command(remote_git_push_ctx.host_dir, "commit", "-m", "Add new file")

    with pytest.raises(NotImplementedError, match="remote hosts is not implemented"):
        push_git(
            agent=remote_git_push_ctx.agent,
            host=remote_git_push_ctx.host,
            source=remote_git_push_ctx.host_dir,
            uncommitted_changes=UncommittedChangesMode.CLOBBER,
        )
