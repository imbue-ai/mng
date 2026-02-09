import subprocess
from pathlib import Path
from typing import Any
from typing import cast

import pytest
from pydantic import Field

from imbue.imbue_common.frozen_model import FrozenModel
from imbue.mngr.api.pull import pull_files
from imbue.mngr.api.pull import pull_git
from imbue.mngr.api.sync import LocalGitContext
from imbue.mngr.api.sync import UncommittedChangesError
from imbue.mngr.api.test_fixtures import FakeAgent
from imbue.mngr.api.test_fixtures import FakeHost
from imbue.mngr.interfaces.agent import AgentInterface
from imbue.mngr.interfaces.host import HostInterface
from imbue.mngr.interfaces.host import OnlineHostInterface
from imbue.mngr.primitives import UncommittedChangesMode
from imbue.mngr.utils.git_utils import get_current_branch
from imbue.mngr.utils.testing import get_stash_count
from imbue.mngr.utils.testing import init_git_repo_with_config
from imbue.mngr.utils.testing import run_git_command


def _has_uncommitted_changes(path: Path) -> bool:
    """Helper to check for uncommitted changes using LocalGitContext."""
    return LocalGitContext().has_uncommitted_changes(path)


class PullTestContext(FrozenModel):
    """Shared test context for pull_files integration tests."""

    agent_dir: Path = Field(description="Agent working directory")
    host_dir: Path = Field(description="Host destination directory")
    # Use Any to avoid pydantic validation since our test doubles don't inherit from the interfaces
    agent: Any = Field(description="Test agent")
    host: Any = Field(description="Test host")


@pytest.fixture
def pull_ctx(tmp_path: Path) -> PullTestContext:
    """Create a test context with agent and host directories."""
    agent_dir = tmp_path / "agent"
    host_dir = tmp_path / "host"
    agent_dir.mkdir(parents=True)
    init_git_repo_with_config(host_dir)
    return PullTestContext(
        agent_dir=agent_dir,
        host_dir=host_dir,
        agent=cast(AgentInterface, FakeAgent(work_dir=agent_dir)),
        host=cast(HostInterface, FakeHost()),
    )


# =============================================================================
# Test: FAIL mode (default)
# =============================================================================


def test_pull_files_fail_mode_with_no_uncommitted_changes_succeeds(
    pull_ctx: PullTestContext,
) -> None:
    """Test that FAIL mode succeeds when there are no uncommitted changes."""
    (pull_ctx.agent_dir / "file.txt").write_text("agent content")
    assert not _has_uncommitted_changes(pull_ctx.host_dir)

    result = pull_files(
        agent=pull_ctx.agent,
        host=pull_ctx.host,
        destination=pull_ctx.host_dir,
        uncommitted_changes=UncommittedChangesMode.FAIL,
    )

    assert (pull_ctx.host_dir / "file.txt").exists()
    assert (pull_ctx.host_dir / "file.txt").read_text() == "agent content"
    assert result.destination_path == pull_ctx.host_dir
    assert result.source_path == pull_ctx.agent_dir


def test_pull_files_fail_mode_with_uncommitted_changes_raises_error(
    pull_ctx: PullTestContext,
) -> None:
    """Test that FAIL mode raises UncommittedChangesError when changes exist."""
    (pull_ctx.agent_dir / "file.txt").write_text("agent content")
    (pull_ctx.host_dir / "uncommitted.txt").write_text("uncommitted content")
    assert _has_uncommitted_changes(pull_ctx.host_dir)

    with pytest.raises(UncommittedChangesError) as exc_info:
        pull_files(
            agent=pull_ctx.agent,
            host=pull_ctx.host,
            destination=pull_ctx.host_dir,
            uncommitted_changes=UncommittedChangesMode.FAIL,
        )

    assert exc_info.value.destination == pull_ctx.host_dir


# =============================================================================
# Test: CLOBBER mode
# =============================================================================


def test_pull_files_clobber_mode_overwrites_host_changes(
    pull_ctx: PullTestContext,
) -> None:
    """Test that CLOBBER mode overwrites uncommitted changes in the host."""
    (pull_ctx.agent_dir / "shared.txt").write_text("agent version")
    (pull_ctx.host_dir / "shared.txt").write_text("host version")
    assert _has_uncommitted_changes(pull_ctx.host_dir)

    result = pull_files(
        agent=pull_ctx.agent,
        host=pull_ctx.host,
        destination=pull_ctx.host_dir,
        uncommitted_changes=UncommittedChangesMode.CLOBBER,
    )

    assert (pull_ctx.host_dir / "shared.txt").read_text() == "agent version"
    assert result.destination_path == pull_ctx.host_dir


def test_pull_files_clobber_mode_when_only_host_has_changes(
    pull_ctx: PullTestContext,
) -> None:
    """Test CLOBBER mode when only the host has a modified file."""
    (pull_ctx.agent_dir / "agent_only.txt").write_text("agent file")
    (pull_ctx.host_dir / "host_only.txt").write_text("host uncommitted content")
    assert _has_uncommitted_changes(pull_ctx.host_dir)

    pull_files(
        agent=pull_ctx.agent,
        host=pull_ctx.host,
        destination=pull_ctx.host_dir,
        uncommitted_changes=UncommittedChangesMode.CLOBBER,
    )

    # rsync doesn't delete by default
    assert (pull_ctx.host_dir / "host_only.txt").exists()
    assert (pull_ctx.host_dir / "agent_only.txt").read_text() == "agent file"


def test_pull_files_clobber_mode_with_delete_flag_removes_host_only_files(
    pull_ctx: PullTestContext,
) -> None:
    """Test CLOBBER mode with delete=True removes files not in agent."""
    (pull_ctx.agent_dir / "agent_file.txt").write_text("agent content")
    (pull_ctx.host_dir / "host_extra.txt").write_text("this should be deleted")
    run_git_command(pull_ctx.host_dir, "add", "host_extra.txt")
    run_git_command(pull_ctx.host_dir, "commit", "-m", "Add host extra file")

    pull_files(
        agent=pull_ctx.agent,
        host=pull_ctx.host,
        destination=pull_ctx.host_dir,
        delete=True,
        uncommitted_changes=UncommittedChangesMode.CLOBBER,
    )

    assert not (pull_ctx.host_dir / "host_extra.txt").exists()
    assert (pull_ctx.host_dir / "agent_file.txt").read_text() == "agent content"


# =============================================================================
# Test: STASH mode
# =============================================================================


def test_pull_files_stash_mode_stashes_changes_and_leaves_stashed(
    pull_ctx: PullTestContext,
) -> None:
    """Test that STASH mode stashes uncommitted changes and leaves them stashed."""
    (pull_ctx.agent_dir / "agent_file.txt").write_text("agent content")
    # Modify a tracked file (README.md was created by _init_git_repo)
    (pull_ctx.host_dir / "README.md").write_text("modified content")
    initial_stash_count = get_stash_count(pull_ctx.host_dir)
    assert _has_uncommitted_changes(pull_ctx.host_dir)

    pull_files(
        agent=pull_ctx.agent,
        host=pull_ctx.host,
        destination=pull_ctx.host_dir,
        uncommitted_changes=UncommittedChangesMode.STASH,
    )

    final_stash_count = get_stash_count(pull_ctx.host_dir)
    assert final_stash_count == initial_stash_count + 1
    # The modified tracked file should be reverted to its committed state
    assert (pull_ctx.host_dir / "README.md").read_text() == "Initial content"
    assert (pull_ctx.host_dir / "agent_file.txt").read_text() == "agent content"


def test_pull_files_stash_mode_when_both_agent_and_host_modify_same_file(
    pull_ctx: PullTestContext,
) -> None:
    """Test STASH mode when both agent and host have modified the same file."""
    # Add and commit a shared file in host
    (pull_ctx.host_dir / "shared.txt").write_text("original content")
    run_git_command(pull_ctx.host_dir, "add", "shared.txt")
    run_git_command(pull_ctx.host_dir, "commit", "-m", "Add shared file")

    # Modify the shared file (uncommitted change to a tracked file)
    (pull_ctx.host_dir / "shared.txt").write_text("host version of shared")
    assert _has_uncommitted_changes(pull_ctx.host_dir)

    # Agent has a different version
    (pull_ctx.agent_dir / "shared.txt").write_text("agent version of shared")

    pull_files(
        agent=pull_ctx.agent,
        host=pull_ctx.host,
        destination=pull_ctx.host_dir,
        uncommitted_changes=UncommittedChangesMode.STASH,
    )

    assert (pull_ctx.host_dir / "shared.txt").read_text() == "agent version of shared"
    assert get_stash_count(pull_ctx.host_dir) == 1


def test_pull_files_stash_mode_stashes_untracked_files(
    pull_ctx: PullTestContext,
) -> None:
    """Test that STASH mode properly stashes untracked files (not just tracked modifications)."""
    (pull_ctx.agent_dir / "agent_file.txt").write_text("agent content")
    # Create an UNTRACKED file (git status --porcelain includes these)
    (pull_ctx.host_dir / "untracked_file.txt").write_text("untracked content")
    initial_stash_count = get_stash_count(pull_ctx.host_dir)
    assert _has_uncommitted_changes(pull_ctx.host_dir)

    pull_files(
        agent=pull_ctx.agent,
        host=pull_ctx.host,
        destination=pull_ctx.host_dir,
        uncommitted_changes=UncommittedChangesMode.STASH,
    )

    # Untracked file should be stashed with -u flag
    final_stash_count = get_stash_count(pull_ctx.host_dir)
    assert final_stash_count == initial_stash_count + 1
    assert not (pull_ctx.host_dir / "untracked_file.txt").exists()
    assert (pull_ctx.host_dir / "agent_file.txt").read_text() == "agent content"


def test_pull_files_merge_mode_restores_untracked_files(
    pull_ctx: PullTestContext,
) -> None:
    """Test that MERGE mode properly stashes and restores untracked files."""
    (pull_ctx.agent_dir / "agent_file.txt").write_text("agent content")
    (pull_ctx.host_dir / "untracked_file.txt").write_text("untracked content")
    initial_stash_count = get_stash_count(pull_ctx.host_dir)
    assert _has_uncommitted_changes(pull_ctx.host_dir)

    pull_files(
        agent=pull_ctx.agent,
        host=pull_ctx.host,
        destination=pull_ctx.host_dir,
        uncommitted_changes=UncommittedChangesMode.MERGE,
    )

    # Stash should be created and popped
    final_stash_count = get_stash_count(pull_ctx.host_dir)
    assert final_stash_count == initial_stash_count
    assert (pull_ctx.host_dir / "untracked_file.txt").exists()
    assert (pull_ctx.host_dir / "untracked_file.txt").read_text() == "untracked content"
    assert (pull_ctx.host_dir / "agent_file.txt").read_text() == "agent content"


def test_pull_files_stash_mode_with_no_uncommitted_changes_does_not_stash(
    pull_ctx: PullTestContext,
) -> None:
    """Test that STASH mode does not create a stash when no changes exist."""
    (pull_ctx.agent_dir / "agent_file.txt").write_text("agent content")
    assert not _has_uncommitted_changes(pull_ctx.host_dir)
    initial_stash_count = get_stash_count(pull_ctx.host_dir)

    pull_files(
        agent=pull_ctx.agent,
        host=pull_ctx.host,
        destination=pull_ctx.host_dir,
        uncommitted_changes=UncommittedChangesMode.STASH,
    )

    final_stash_count = get_stash_count(pull_ctx.host_dir)
    assert final_stash_count == initial_stash_count
    assert (pull_ctx.host_dir / "agent_file.txt").read_text() == "agent content"


# =============================================================================
# Test: MERGE mode
# =============================================================================


def test_pull_files_merge_mode_stashes_and_restores_changes(
    pull_ctx: PullTestContext,
) -> None:
    """Test that MERGE mode stashes changes, pulls, then restores changes."""
    (pull_ctx.agent_dir / "agent_file.txt").write_text("agent content")
    # Modify the tracked README.md file
    (pull_ctx.host_dir / "README.md").write_text("host modified content")
    initial_stash_count = get_stash_count(pull_ctx.host_dir)
    assert _has_uncommitted_changes(pull_ctx.host_dir)

    pull_files(
        agent=pull_ctx.agent,
        host=pull_ctx.host,
        destination=pull_ctx.host_dir,
        uncommitted_changes=UncommittedChangesMode.MERGE,
    )

    final_stash_count = get_stash_count(pull_ctx.host_dir)
    assert final_stash_count == initial_stash_count
    assert (pull_ctx.host_dir / "README.md").read_text() == "host modified content"
    assert (pull_ctx.host_dir / "agent_file.txt").read_text() == "agent content"


def test_pull_files_merge_mode_when_only_agent_file_is_modified(
    pull_ctx: PullTestContext,
) -> None:
    """Test MERGE mode when only the agent has changed a file."""
    (pull_ctx.agent_dir / "shared.txt").write_text("agent modified content")
    # Add and commit the file in host first
    (pull_ctx.host_dir / "shared.txt").write_text("original content")
    run_git_command(pull_ctx.host_dir, "add", "shared.txt")
    run_git_command(pull_ctx.host_dir, "commit", "-m", "Add shared file")
    assert not _has_uncommitted_changes(pull_ctx.host_dir)

    pull_files(
        agent=pull_ctx.agent,
        host=pull_ctx.host,
        destination=pull_ctx.host_dir,
        uncommitted_changes=UncommittedChangesMode.MERGE,
    )

    assert (pull_ctx.host_dir / "shared.txt").read_text() == "agent modified content"


def test_pull_files_merge_mode_when_only_host_has_changes(
    pull_ctx: PullTestContext,
) -> None:
    """Test MERGE mode when only the host has uncommitted changes."""
    (pull_ctx.agent_dir / "agent_file.txt").write_text("agent content")
    (pull_ctx.host_dir / "README.md").write_text("host modified content")
    assert _has_uncommitted_changes(pull_ctx.host_dir)

    pull_files(
        agent=pull_ctx.agent,
        host=pull_ctx.host,
        destination=pull_ctx.host_dir,
        uncommitted_changes=UncommittedChangesMode.MERGE,
    )

    assert (pull_ctx.host_dir / "README.md").read_text() == "host modified content"
    assert (pull_ctx.host_dir / "agent_file.txt").read_text() == "agent content"


def test_pull_files_merge_mode_when_both_modify_different_files(
    pull_ctx: PullTestContext,
) -> None:
    """Test MERGE mode when agent and host modify different files."""
    (pull_ctx.agent_dir / "agent_only.txt").write_text("agent content")
    (pull_ctx.host_dir / "README.md").write_text("host modified content")
    initial_stash_count = get_stash_count(pull_ctx.host_dir)
    assert _has_uncommitted_changes(pull_ctx.host_dir)

    pull_files(
        agent=pull_ctx.agent,
        host=pull_ctx.host,
        destination=pull_ctx.host_dir,
        uncommitted_changes=UncommittedChangesMode.MERGE,
    )

    assert (pull_ctx.host_dir / "agent_only.txt").read_text() == "agent content"
    assert (pull_ctx.host_dir / "README.md").read_text() == "host modified content"
    final_stash_count = get_stash_count(pull_ctx.host_dir)
    assert final_stash_count == initial_stash_count


def test_pull_files_merge_mode_with_no_uncommitted_changes(
    pull_ctx: PullTestContext,
) -> None:
    """Test that MERGE mode works correctly when there are no uncommitted changes."""
    (pull_ctx.agent_dir / "agent_file.txt").write_text("agent content")
    assert not _has_uncommitted_changes(pull_ctx.host_dir)
    initial_stash_count = get_stash_count(pull_ctx.host_dir)

    pull_files(
        agent=pull_ctx.agent,
        host=pull_ctx.host,
        destination=pull_ctx.host_dir,
        uncommitted_changes=UncommittedChangesMode.MERGE,
    )

    final_stash_count = get_stash_count(pull_ctx.host_dir)
    assert final_stash_count == initial_stash_count
    assert (pull_ctx.host_dir / "agent_file.txt").read_text() == "agent content"


# =============================================================================
# Test: .git directory exclusion
# =============================================================================


def test_pull_files_excludes_git_directory(
    pull_ctx: PullTestContext,
) -> None:
    """Test that pull_files excludes the .git directory from rsync."""
    # Make the agent directory a git repo too
    run_git_command(pull_ctx.agent_dir, "init")
    run_git_command(pull_ctx.agent_dir, "config", "user.email", "test@example.com")
    run_git_command(pull_ctx.agent_dir, "config", "user.name", "Test User")
    (pull_ctx.agent_dir / "file.txt").write_text("agent content")
    run_git_command(pull_ctx.agent_dir, "add", "file.txt")
    run_git_command(pull_ctx.agent_dir, "commit", "-m", "Add file")

    host_commit_before = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=pull_ctx.host_dir,
        capture_output=True,
        text=True,
    ).stdout.strip()

    pull_files(
        agent=pull_ctx.agent,
        host=pull_ctx.host,
        destination=pull_ctx.host_dir,
        uncommitted_changes=UncommittedChangesMode.CLOBBER,
    )

    # The host's .git directory should be unchanged
    host_commit_after = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=pull_ctx.host_dir,
        capture_output=True,
        text=True,
    ).stdout.strip()
    assert host_commit_before == host_commit_after
    assert (pull_ctx.host_dir / "file.txt").read_text() == "agent content"


# =============================================================================
# Test: dry_run flag
# =============================================================================


def test_pull_files_dry_run_does_not_modify_files(
    pull_ctx: PullTestContext,
) -> None:
    """Test that dry_run=True shows what would be transferred without modifying files."""
    (pull_ctx.agent_dir / "new_file.txt").write_text("agent content")
    assert not (pull_ctx.host_dir / "new_file.txt").exists()

    result = pull_files(
        agent=pull_ctx.agent,
        host=pull_ctx.host,
        destination=pull_ctx.host_dir,
        dry_run=True,
    )

    assert not (pull_ctx.host_dir / "new_file.txt").exists()
    assert result.is_dry_run is True


# =============================================================================
# Test: source_path parameter
# =============================================================================


def test_pull_files_with_custom_source_path(
    pull_ctx: PullTestContext,
) -> None:
    """Test that pull_files can use a custom source path instead of work_dir."""
    custom_source = pull_ctx.agent_dir / "subdir"
    custom_source.mkdir(parents=True)
    (custom_source / "file_in_subdir.txt").write_text("content from subdir")
    (pull_ctx.agent_dir / "file_in_root.txt").write_text("content from root")

    result = pull_files(
        agent=pull_ctx.agent,
        host=pull_ctx.host,
        destination=pull_ctx.host_dir,
        source_path=custom_source,
    )

    assert (pull_ctx.host_dir / "file_in_subdir.txt").read_text() == "content from subdir"
    assert not (pull_ctx.host_dir / "file_in_root.txt").exists()
    assert result.source_path == custom_source


# =============================================================================
# Test: Remote (non-local) host behavior
# =============================================================================


@pytest.fixture
def remote_pull_ctx(tmp_path: Path) -> PullTestContext:
    """Create a test context with a remote (non-local) host."""
    agent_dir = tmp_path / "agent"
    host_dir = tmp_path / "host"
    agent_dir.mkdir(parents=True)
    init_git_repo_with_config(host_dir)
    return PullTestContext(
        agent_dir=agent_dir,
        host_dir=host_dir,
        agent=cast(AgentInterface, FakeAgent(work_dir=agent_dir)),
        host=cast(HostInterface, FakeHost(is_local=False)),
    )


@pytest.fixture
def remote_git_pull_ctx(tmp_path: Path) -> PullTestContext:
    """Create a test context with remote host for git pull testing.

    Both agent and host directories are git repos with shared history.
    """
    agent_dir = tmp_path / "agent"
    host_dir = tmp_path / "host"

    # Initialize agent repo (the source for pull)
    init_git_repo_with_config(agent_dir)

    # Clone agent to create host (so they share history)
    subprocess.run(
        ["git", "clone", str(agent_dir), str(host_dir)],
        capture_output=True,
        text=True,
        check=True,
    )
    run_git_command(host_dir, "config", "user.email", "test@example.com")
    run_git_command(host_dir, "config", "user.name", "Test User")

    return PullTestContext(
        agent_dir=agent_dir,
        host_dir=host_dir,
        agent=cast(AgentInterface, FakeAgent(work_dir=agent_dir)),
        host=cast(OnlineHostInterface, FakeHost(is_local=False)),
    )


def test_pull_files_with_remote_host_succeeds(
    remote_pull_ctx: PullTestContext,
) -> None:
    """Test that pull_files works with a remote (non-local) host.

    rsync is executed via host.execute_command, which works for both local
    and remote hosts.
    """
    (remote_pull_ctx.agent_dir / "file.txt").write_text("agent content")

    result = pull_files(
        agent=remote_pull_ctx.agent,
        host=remote_pull_ctx.host,
        destination=remote_pull_ctx.host_dir,
        uncommitted_changes=UncommittedChangesMode.CLOBBER,
    )

    assert (remote_pull_ctx.host_dir / "file.txt").exists()
    assert (remote_pull_ctx.host_dir / "file.txt").read_text() == "agent content"
    assert result.source_path == remote_pull_ctx.agent_dir


def test_pull_files_with_remote_host_handles_uncommitted_changes(
    remote_pull_ctx: PullTestContext,
) -> None:
    """Test that pull_files handles uncommitted changes when pulling from remote host."""
    (remote_pull_ctx.agent_dir / "file.txt").write_text("agent content")
    (remote_pull_ctx.host_dir / "README.md").write_text("modified content")
    initial_stash_count = get_stash_count(remote_pull_ctx.host_dir)

    pull_files(
        agent=remote_pull_ctx.agent,
        host=remote_pull_ctx.host,
        destination=remote_pull_ctx.host_dir,
        uncommitted_changes=UncommittedChangesMode.STASH,
    )

    final_stash_count = get_stash_count(remote_pull_ctx.host_dir)
    assert final_stash_count == initial_stash_count + 1
    assert (remote_pull_ctx.host_dir / "file.txt").read_text() == "agent content"


def test_pull_git_with_local_path_from_remote_host_works(
    remote_git_pull_ctx: PullTestContext,
) -> None:
    """Test that pull_git works when the agent path is locally accessible.

    Even when the host is marked as non-local (is_local=False), if the agent's
    work_dir is actually a local path, git operations will succeed. This is
    the case for our test environment where we simulate remote hosts locally.

    In a real remote scenario (where the path is on a different machine),
    this would fail because git fetch cannot access the remote path directly.
    """
    # Create a new commit on the agent
    (remote_git_pull_ctx.agent_dir / "new_file.txt").write_text("agent content")
    run_git_command(remote_git_pull_ctx.agent_dir, "add", "new_file.txt")
    run_git_command(remote_git_pull_ctx.agent_dir, "commit", "-m", "Add new file")

    result = pull_git(
        agent=remote_git_pull_ctx.agent,
        host=remote_git_pull_ctx.host,
        destination=remote_git_pull_ctx.host_dir,
        uncommitted_changes=UncommittedChangesMode.CLOBBER,
    )

    # The new file should now exist in the host directory
    assert (remote_git_pull_ctx.host_dir / "new_file.txt").exists()
    assert (remote_git_pull_ctx.host_dir / "new_file.txt").read_text() == "agent content"
    assert result.is_dry_run is False


def test_pull_git_merge_mode_with_different_branch_restores_stash_on_original(
    remote_git_pull_ctx: PullTestContext,
) -> None:
    """Test that pull_git with MERGE mode restores stash on original branch.

    When pulling to a different target branch, uncommitted changes should be
    stashed on the original branch, and after the merge, the stash should be
    restored on the original branch (not the target branch).
    """
    host_dir = remote_git_pull_ctx.host_dir
    agent_dir = remote_git_pull_ctx.agent_dir

    # Create a target branch on the agent with a new commit
    run_git_command(agent_dir, "checkout", "-b", "feature-branch")
    (agent_dir / "feature.txt").write_text("feature content")
    run_git_command(agent_dir, "add", "feature.txt")
    run_git_command(agent_dir, "commit", "-m", "Add feature")

    # Create the same branch name on the host (so checkout can succeed)
    original_branch = get_current_branch(host_dir)
    run_git_command(host_dir, "checkout", "-b", "feature-branch")
    run_git_command(host_dir, "checkout", original_branch)

    # Make uncommitted changes on the host's original branch
    (host_dir / "README.md").write_text("uncommitted change")
    assert _has_uncommitted_changes(host_dir)

    result = pull_git(
        agent=remote_git_pull_ctx.agent,
        host=remote_git_pull_ctx.host,
        destination=host_dir,
        source_branch="feature-branch",
        target_branch="feature-branch",
        uncommitted_changes=UncommittedChangesMode.MERGE,
    )

    # Verify the merge happened
    assert result.commits_transferred > 0

    # Verify we're back on the original branch with uncommitted changes restored
    current_branch = get_current_branch(host_dir)
    assert current_branch == original_branch
    assert (host_dir / "README.md").read_text() == "uncommitted change"
