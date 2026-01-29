"""Integration tests for pull_files with real git repositories and file operations."""

import subprocess
from pathlib import Path
from typing import cast
from uuid import uuid4

import pytest

from imbue.imbue_common.frozen_model import FrozenModel
from imbue.imbue_common.mutable_model import MutableModel
from imbue.mngr.api.pull import UncommittedChangesError
from imbue.mngr.api.pull import pull_files
from imbue.mngr.interfaces.agent import AgentInterface
from imbue.mngr.interfaces.data_types import CommandResult
from imbue.mngr.interfaces.host import HostInterface
from imbue.mngr.primitives import UncommittedChangesMode
from pydantic import Field


class _FakeAgent(FrozenModel):
    """Minimal test double for AgentInterface.

    Only implements work_dir, which is all pull_files actually uses.
    """

    work_dir: Path = Field(description="Working directory for this agent")


class _FakeHost(MutableModel):
    """Minimal test double for HostInterface.

    Only implements execute_command, which is all pull_files actually uses.
    Executes commands locally via subprocess.
    """

    def execute_command(self, command: str) -> CommandResult:
        """Execute a shell command locally and return the result."""
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
        )
        return CommandResult(
            stdout=result.stdout,
            stderr=result.stderr,
            success=result.returncode == 0,
        )


def _create_agent(work_dir: Path) -> AgentInterface:
    """Create a test agent with the given work directory."""
    return cast(AgentInterface, _FakeAgent(work_dir=work_dir))


def _create_host() -> HostInterface:
    """Create a test host that executes commands locally."""
    return cast(HostInterface, _FakeHost())


def _run_git(cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    """Run a git command in the given directory."""
    result = subprocess.run(
        ["git", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {result.stderr}")
    return result


def _init_git_repo(path: Path) -> None:
    """Initialize a git repository with an initial commit."""
    path.mkdir(parents=True, exist_ok=True)
    _run_git(path, "init")
    _run_git(path, "config", "user.email", "test@example.com")
    _run_git(path, "config", "user.name", "Test User")
    # Create an initial file and commit
    (path / "README.md").write_text("Initial content")
    _run_git(path, "add", "README.md")
    _run_git(path, "commit", "-m", "Initial commit")


def _has_uncommitted_changes(path: Path) -> bool:
    """Check if the repository has uncommitted changes."""
    result = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=path,
        capture_output=True,
        text=True,
    )
    return len(result.stdout.strip()) > 0


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


def _unique_name() -> str:
    """Generate a unique name for test isolation."""
    return uuid4().hex[:8]


# =============================================================================
# Test: FAIL mode (default)
# =============================================================================


def test_pull_files_fail_mode_with_no_uncommitted_changes_succeeds(
    tmp_path: Path,
) -> None:
    """Test that FAIL mode succeeds when there are no uncommitted changes."""
    unique = _unique_name()
    agent_dir = tmp_path / f"agent_{unique}"
    host_dir = tmp_path / f"host_{unique}"

    # Set up agent directory with a file
    agent_dir.mkdir(parents=True)
    (agent_dir / "file.txt").write_text("agent content")

    # Set up host as a git repo with no uncommitted changes
    _init_git_repo(host_dir)
    assert not _has_uncommitted_changes(host_dir)

    # Perform the pull with FAIL mode (default)
    agent = _create_agent(agent_dir)
    host = _create_host()
    result = pull_files(
        agent=agent,
        host=host,
        destination=host_dir,
        uncommitted_changes=UncommittedChangesMode.FAIL,
    )

    # Verify the file was transferred
    assert (host_dir / "file.txt").exists()
    assert (host_dir / "file.txt").read_text() == "agent content"
    assert result.destination_path == host_dir
    assert result.source_path == agent_dir


def test_pull_files_fail_mode_with_uncommitted_changes_raises_error(
    tmp_path: Path,
) -> None:
    """Test that FAIL mode raises UncommittedChangesError when changes exist."""
    unique = _unique_name()
    agent_dir = tmp_path / f"agent_{unique}"
    host_dir = tmp_path / f"host_{unique}"

    # Set up agent directory
    agent_dir.mkdir(parents=True)
    (agent_dir / "file.txt").write_text("agent content")

    # Set up host as a git repo with uncommitted changes
    _init_git_repo(host_dir)
    (host_dir / "uncommitted.txt").write_text("uncommitted content")
    assert _has_uncommitted_changes(host_dir)

    # Attempt the pull with FAIL mode - should raise
    agent = _create_agent(agent_dir)
    host = _create_host()
    with pytest.raises(UncommittedChangesError) as exc_info:
        pull_files(
            agent=agent,
            host=host,
            destination=host_dir,
            uncommitted_changes=UncommittedChangesMode.FAIL,
        )

    assert exc_info.value.destination == host_dir


# =============================================================================
# Test: CLOBBER mode
# =============================================================================


def test_pull_files_clobber_mode_overwrites_host_changes(
    tmp_path: Path,
) -> None:
    """Test that CLOBBER mode overwrites uncommitted changes in the host."""
    unique = _unique_name()
    agent_dir = tmp_path / f"agent_{unique}"
    host_dir = tmp_path / f"host_{unique}"

    # Set up agent directory with a file
    agent_dir.mkdir(parents=True)
    (agent_dir / "shared.txt").write_text("agent version")

    # Set up host as a git repo with the same file modified
    _init_git_repo(host_dir)
    (host_dir / "shared.txt").write_text("host version")
    assert _has_uncommitted_changes(host_dir)

    # Perform the pull with CLOBBER mode
    agent = _create_agent(agent_dir)
    host = _create_host()
    result = pull_files(
        agent=agent,
        host=host,
        destination=host_dir,
        uncommitted_changes=UncommittedChangesMode.CLOBBER,
    )

    # Verify the host file was overwritten with agent content
    assert (host_dir / "shared.txt").read_text() == "agent version"
    assert result.destination_path == host_dir


def test_pull_files_clobber_mode_when_only_host_has_changes(
    tmp_path: Path,
) -> None:
    """Test CLOBBER mode when only the host has a modified file."""
    unique = _unique_name()
    agent_dir = tmp_path / f"agent_{unique}"
    host_dir = tmp_path / f"host_{unique}"

    # Set up agent directory (no shared.txt)
    agent_dir.mkdir(parents=True)
    (agent_dir / "agent_only.txt").write_text("agent file")

    # Set up host with an uncommitted file
    _init_git_repo(host_dir)
    (host_dir / "host_only.txt").write_text("host uncommitted content")
    assert _has_uncommitted_changes(host_dir)

    # Perform the pull with CLOBBER mode
    agent = _create_agent(agent_dir)
    host = _create_host()
    pull_files(
        agent=agent,
        host=host,
        destination=host_dir,
        uncommitted_changes=UncommittedChangesMode.CLOBBER,
    )

    # The host_only.txt should still exist (rsync doesn't delete by default)
    assert (host_dir / "host_only.txt").exists()
    # The agent file should be transferred
    assert (host_dir / "agent_only.txt").read_text() == "agent file"


def test_pull_files_clobber_mode_with_delete_flag_removes_host_only_files(
    tmp_path: Path,
) -> None:
    """Test CLOBBER mode with delete=True removes files not in agent."""
    unique = _unique_name()
    agent_dir = tmp_path / f"agent_{unique}"
    host_dir = tmp_path / f"host_{unique}"

    # Set up agent directory
    agent_dir.mkdir(parents=True)
    (agent_dir / "agent_file.txt").write_text("agent content")

    # Set up host with an extra file
    _init_git_repo(host_dir)
    (host_dir / "host_extra.txt").write_text("this should be deleted")
    _run_git(host_dir, "add", "host_extra.txt")
    _run_git(host_dir, "commit", "-m", "Add host extra file")

    # Perform the pull with CLOBBER mode and delete flag
    agent = _create_agent(agent_dir)
    host = _create_host()
    pull_files(
        agent=agent,
        host=host,
        destination=host_dir,
        delete=True,
        uncommitted_changes=UncommittedChangesMode.CLOBBER,
    )

    # The host_extra.txt should be deleted
    assert not (host_dir / "host_extra.txt").exists()
    # The agent file should be transferred
    assert (host_dir / "agent_file.txt").read_text() == "agent content"


# =============================================================================
# Test: STASH mode
# =============================================================================


def test_pull_files_stash_mode_stashes_changes_and_leaves_stashed(
    tmp_path: Path,
) -> None:
    """Test that STASH mode stashes uncommitted changes and leaves them stashed."""
    unique = _unique_name()
    agent_dir = tmp_path / f"agent_{unique}"
    host_dir = tmp_path / f"host_{unique}"

    # Set up agent directory
    agent_dir.mkdir(parents=True)
    (agent_dir / "agent_file.txt").write_text("agent content")

    # Set up host with uncommitted changes to a TRACKED file
    _init_git_repo(host_dir)
    # Modify a tracked file (README.md was created by _init_git_repo)
    (host_dir / "README.md").write_text("modified content")
    initial_stash_count = _get_stash_count(host_dir)
    assert _has_uncommitted_changes(host_dir)

    # Perform the pull with STASH mode
    agent = _create_agent(agent_dir)
    host = _create_host()
    pull_files(
        agent=agent,
        host=host,
        destination=host_dir,
        uncommitted_changes=UncommittedChangesMode.STASH,
    )

    # Verify the stash was created and NOT popped
    final_stash_count = _get_stash_count(host_dir)
    assert final_stash_count == initial_stash_count + 1

    # The modified tracked file should be reverted to its committed state
    assert (host_dir / "README.md").read_text() == "Initial content"

    # The agent file should be transferred
    assert (host_dir / "agent_file.txt").read_text() == "agent content"


def test_pull_files_stash_mode_when_both_agent_and_host_modify_same_file(
    tmp_path: Path,
) -> None:
    """Test STASH mode when both agent and host have modified the same file."""
    unique = _unique_name()
    agent_dir = tmp_path / f"agent_{unique}"
    host_dir = tmp_path / f"host_{unique}"

    # Set up host first with a committed shared file
    _init_git_repo(host_dir)
    (host_dir / "shared.txt").write_text("original content")
    _run_git(host_dir, "add", "shared.txt")
    _run_git(host_dir, "commit", "-m", "Add shared file")

    # Now modify the shared file (uncommitted change to a tracked file)
    (host_dir / "shared.txt").write_text("host version of shared")
    assert _has_uncommitted_changes(host_dir)

    # Set up agent directory with a different version of the shared file
    agent_dir.mkdir(parents=True)
    (agent_dir / "shared.txt").write_text("agent version of shared")

    # Perform the pull with STASH mode
    agent = _create_agent(agent_dir)
    host = _create_host()
    pull_files(
        agent=agent,
        host=host,
        destination=host_dir,
        uncommitted_changes=UncommittedChangesMode.STASH,
    )

    # After pull, the file should have the agent's version
    assert (host_dir / "shared.txt").read_text() == "agent version of shared"

    # The stash should contain the host's version
    stash_count = _get_stash_count(host_dir)
    assert stash_count == 1


def test_pull_files_stash_mode_with_no_uncommitted_changes_does_not_stash(
    tmp_path: Path,
) -> None:
    """Test that STASH mode does not create a stash when no changes exist."""
    unique = _unique_name()
    agent_dir = tmp_path / f"agent_{unique}"
    host_dir = tmp_path / f"host_{unique}"

    # Set up agent directory
    agent_dir.mkdir(parents=True)
    (agent_dir / "agent_file.txt").write_text("agent content")

    # Set up host with NO uncommitted changes
    _init_git_repo(host_dir)
    assert not _has_uncommitted_changes(host_dir)
    initial_stash_count = _get_stash_count(host_dir)

    # Perform the pull with STASH mode
    agent = _create_agent(agent_dir)
    host = _create_host()
    pull_files(
        agent=agent,
        host=host,
        destination=host_dir,
        uncommitted_changes=UncommittedChangesMode.STASH,
    )

    # No stash should be created
    final_stash_count = _get_stash_count(host_dir)
    assert final_stash_count == initial_stash_count

    # The agent file should be transferred
    assert (host_dir / "agent_file.txt").read_text() == "agent content"


# =============================================================================
# Test: MERGE mode
# =============================================================================


def test_pull_files_merge_mode_stashes_and_restores_changes(
    tmp_path: Path,
) -> None:
    """Test that MERGE mode stashes changes, pulls, then restores changes."""
    unique = _unique_name()
    agent_dir = tmp_path / f"agent_{unique}"
    host_dir = tmp_path / f"host_{unique}"

    # Set up agent directory with its own file
    agent_dir.mkdir(parents=True)
    (agent_dir / "agent_file.txt").write_text("agent content")

    # Set up host with an uncommitted change to a tracked file
    _init_git_repo(host_dir)
    # Modify the tracked README.md file (created by _init_git_repo)
    (host_dir / "README.md").write_text("host modified content")
    initial_stash_count = _get_stash_count(host_dir)
    assert _has_uncommitted_changes(host_dir)

    # Perform the pull with MERGE mode
    agent = _create_agent(agent_dir)
    host = _create_host()
    pull_files(
        agent=agent,
        host=host,
        destination=host_dir,
        uncommitted_changes=UncommittedChangesMode.MERGE,
    )

    # Verify the stash was created and then popped (count should be same)
    final_stash_count = _get_stash_count(host_dir)
    assert final_stash_count == initial_stash_count

    # The host's uncommitted changes should be restored
    assert (host_dir / "README.md").read_text() == "host modified content"

    # The agent file should also be transferred
    assert (host_dir / "agent_file.txt").read_text() == "agent content"


def test_pull_files_merge_mode_when_only_agent_file_is_modified(
    tmp_path: Path,
) -> None:
    """Test MERGE mode when only the agent has changed a file."""
    unique = _unique_name()
    agent_dir = tmp_path / f"agent_{unique}"
    host_dir = tmp_path / f"host_{unique}"

    # Set up agent directory with modified file
    agent_dir.mkdir(parents=True)
    (agent_dir / "shared.txt").write_text("agent modified content")

    # Set up host with clean state (no uncommitted changes)
    _init_git_repo(host_dir)
    (host_dir / "shared.txt").write_text("original content")
    _run_git(host_dir, "add", "shared.txt")
    _run_git(host_dir, "commit", "-m", "Add shared file")
    assert not _has_uncommitted_changes(host_dir)

    # Perform the pull with MERGE mode
    agent = _create_agent(agent_dir)
    host = _create_host()
    pull_files(
        agent=agent,
        host=host,
        destination=host_dir,
        uncommitted_changes=UncommittedChangesMode.MERGE,
    )

    # The file should have the agent's content
    assert (host_dir / "shared.txt").read_text() == "agent modified content"


def test_pull_files_merge_mode_when_only_host_has_changes(
    tmp_path: Path,
) -> None:
    """Test MERGE mode when only the host has uncommitted changes."""
    unique = _unique_name()
    agent_dir = tmp_path / f"agent_{unique}"
    host_dir = tmp_path / f"host_{unique}"

    # Set up agent directory (empty except for one file)
    agent_dir.mkdir(parents=True)
    (agent_dir / "agent_file.txt").write_text("agent content")

    # Set up host with uncommitted changes to a tracked file
    _init_git_repo(host_dir)
    # Modify the tracked README.md file
    (host_dir / "README.md").write_text("host modified content")
    assert _has_uncommitted_changes(host_dir)

    # Perform the pull with MERGE mode
    agent = _create_agent(agent_dir)
    host = _create_host()
    pull_files(
        agent=agent,
        host=host,
        destination=host_dir,
        uncommitted_changes=UncommittedChangesMode.MERGE,
    )

    # The host's uncommitted changes should be preserved
    assert (host_dir / "README.md").read_text() == "host modified content"

    # The agent file should be transferred
    assert (host_dir / "agent_file.txt").read_text() == "agent content"


def test_pull_files_merge_mode_when_both_modify_different_files(
    tmp_path: Path,
) -> None:
    """Test MERGE mode when agent and host modify different files."""
    unique = _unique_name()
    agent_dir = tmp_path / f"agent_{unique}"
    host_dir = tmp_path / f"host_{unique}"

    # Set up agent with one file
    agent_dir.mkdir(parents=True)
    (agent_dir / "agent_only.txt").write_text("agent content")

    # Set up host with uncommitted changes to a tracked file
    _init_git_repo(host_dir)
    # Modify the tracked README.md file
    (host_dir / "README.md").write_text("host modified content")
    initial_stash_count = _get_stash_count(host_dir)
    assert _has_uncommitted_changes(host_dir)

    # Perform the pull with MERGE mode
    agent = _create_agent(agent_dir)
    host = _create_host()
    pull_files(
        agent=agent,
        host=host,
        destination=host_dir,
        uncommitted_changes=UncommittedChangesMode.MERGE,
    )

    # Both modifications should exist
    assert (host_dir / "agent_only.txt").read_text() == "agent content"
    assert (host_dir / "README.md").read_text() == "host modified content"

    # Stash should be empty (was created and popped)
    final_stash_count = _get_stash_count(host_dir)
    assert final_stash_count == initial_stash_count


def test_pull_files_merge_mode_with_no_uncommitted_changes(
    tmp_path: Path,
) -> None:
    """Test that MERGE mode works correctly when there are no uncommitted changes."""
    unique = _unique_name()
    agent_dir = tmp_path / f"agent_{unique}"
    host_dir = tmp_path / f"host_{unique}"

    # Set up agent directory
    agent_dir.mkdir(parents=True)
    (agent_dir / "agent_file.txt").write_text("agent content")

    # Set up host with no uncommitted changes
    _init_git_repo(host_dir)
    assert not _has_uncommitted_changes(host_dir)
    initial_stash_count = _get_stash_count(host_dir)

    # Perform the pull with MERGE mode
    agent = _create_agent(agent_dir)
    host = _create_host()
    pull_files(
        agent=agent,
        host=host,
        destination=host_dir,
        uncommitted_changes=UncommittedChangesMode.MERGE,
    )

    # No stash should be created
    final_stash_count = _get_stash_count(host_dir)
    assert final_stash_count == initial_stash_count

    # The agent file should be transferred
    assert (host_dir / "agent_file.txt").read_text() == "agent content"


# =============================================================================
# Test: .git directory exclusion
# =============================================================================


def test_pull_files_excludes_git_directory(
    tmp_path: Path,
) -> None:
    """Test that pull_files excludes the .git directory from rsync."""
    unique = _unique_name()
    agent_dir = tmp_path / f"agent_{unique}"
    host_dir = tmp_path / f"host_{unique}"

    # Set up agent as a git repo
    _init_git_repo(agent_dir)
    (agent_dir / "file.txt").write_text("agent content")
    _run_git(agent_dir, "add", "file.txt")
    _run_git(agent_dir, "commit", "-m", "Add file")

    # Set up host as a different git repo
    _init_git_repo(host_dir)

    # Get the original host git commit hash
    host_commit_before = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=host_dir,
        capture_output=True,
        text=True,
    ).stdout.strip()

    # Perform the pull
    agent = _create_agent(agent_dir)
    host = _create_host()
    pull_files(
        agent=agent,
        host=host,
        destination=host_dir,
        uncommitted_changes=UncommittedChangesMode.CLOBBER,
    )

    # The host's .git directory should be unchanged (same commit hash)
    host_commit_after = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=host_dir,
        capture_output=True,
        text=True,
    ).stdout.strip()
    assert host_commit_before == host_commit_after

    # The file should be transferred
    assert (host_dir / "file.txt").read_text() == "agent content"


# =============================================================================
# Test: dry_run flag
# =============================================================================


def test_pull_files_dry_run_does_not_modify_files(
    tmp_path: Path,
) -> None:
    """Test that dry_run=True shows what would be transferred without modifying files."""
    unique = _unique_name()
    agent_dir = tmp_path / f"agent_{unique}"
    host_dir = tmp_path / f"host_{unique}"

    # Set up agent directory with a file
    agent_dir.mkdir(parents=True)
    (agent_dir / "new_file.txt").write_text("agent content")

    # Set up host directory (clean)
    _init_git_repo(host_dir)
    assert not (host_dir / "new_file.txt").exists()

    # Perform a dry run
    agent = _create_agent(agent_dir)
    host = _create_host()
    result = pull_files(
        agent=agent,
        host=host,
        destination=host_dir,
        dry_run=True,
    )

    # The file should NOT be created
    assert not (host_dir / "new_file.txt").exists()

    # Result should indicate dry run
    assert result.is_dry_run is True


# =============================================================================
# Test: source_path parameter
# =============================================================================


def test_pull_files_with_custom_source_path(
    tmp_path: Path,
) -> None:
    """Test that pull_files can use a custom source path instead of work_dir."""
    unique = _unique_name()
    agent_dir = tmp_path / f"agent_{unique}"
    custom_source = agent_dir / "subdir"
    host_dir = tmp_path / f"host_{unique}"

    # Set up agent directory with a subdirectory
    agent_dir.mkdir(parents=True)
    custom_source.mkdir(parents=True)
    (custom_source / "file_in_subdir.txt").write_text("content from subdir")
    (agent_dir / "file_in_root.txt").write_text("content from root")

    # Set up host directory
    _init_git_repo(host_dir)

    # Perform the pull from the subdirectory only
    agent = _create_agent(agent_dir)
    host = _create_host()
    result = pull_files(
        agent=agent,
        host=host,
        destination=host_dir,
        source_path=custom_source,
    )

    # Only the file from subdir should be transferred
    assert (host_dir / "file_in_subdir.txt").read_text() == "content from subdir"
    # The file from root should NOT be transferred
    assert not (host_dir / "file_in_root.txt").exists()

    # Result should reflect the custom source path
    assert result.source_path == custom_source
