"""Unit tests for push API functions."""

from pathlib import Path
from unittest.mock import MagicMock
from unittest.mock import patch

import pytest

from imbue.mngr.api.push import PushGitResult
from imbue.mngr.api.push import PushResult
from imbue.mngr.api.push import _handle_uncommitted_changes_in_agent
from imbue.mngr.api.push import _parse_rsync_output
from imbue.mngr.api.push import push_files
from imbue.mngr.api.push import push_git
from imbue.mngr.errors import MngrError
from imbue.mngr.primitives import UncommittedChangesMode


# Standard rsync output used across tests
RSYNC_SUCCESS_OUTPUT = "sending incremental file list\nsent 100 bytes  received 50 bytes\ntotal size is 1000"


@pytest.fixture
def mock_agent() -> MagicMock:
    """Create a mock agent with a standard work_dir."""
    agent = MagicMock()
    agent.work_dir = Path("/agent/work")
    return agent


@pytest.fixture
def mock_host_local() -> MagicMock:
    """Create a mock local host."""
    host = MagicMock()
    host.is_local = True
    host.execute_command.return_value = MagicMock(
        success=True,
        stdout="",
        stderr="",
    )
    return host


@pytest.fixture
def mock_host_no_uncommitted() -> MagicMock:
    """Create a mock local host that reports no uncommitted changes."""
    host = MagicMock()
    host.is_local = True
    # git status --porcelain returns empty for no changes
    host.execute_command.return_value = MagicMock(
        success=True,
        stdout="",
        stderr="",
    )
    return host


def test_parse_rsync_output_with_files() -> None:
    """Test parsing rsync output with file transfers."""
    output = """sending incremental file list
file1.txt
file2.py
subdir/file3.md

sent 1,234 bytes  received 567 bytes  1,801.00 bytes/sec
total size is 5,678  speedup is 3.15
"""
    files, bytes_transferred = _parse_rsync_output(output)
    assert files == 3
    assert bytes_transferred == 1234


def test_parse_rsync_output_empty() -> None:
    """Test parsing rsync output with no files transferred."""
    output = """sending incremental file list

sent 100 bytes  received 50 bytes  150.00 bytes/sec
total size is 1,000  speedup is 6.67
"""
    files, bytes_transferred = _parse_rsync_output(output)
    assert files == 0
    assert bytes_transferred == 100


def test_parse_rsync_output_dry_run() -> None:
    """Test parsing rsync output in dry run mode."""
    output = """sending incremental file list
file1.txt
file2.py
file3.md

sent 345 bytes  received 12 bytes  238.00 bytes/sec
total size is 10,000  speedup is 28.01 (DRY RUN)
"""
    files, bytes_transferred = _parse_rsync_output(output)
    assert files == 3
    assert bytes_transferred == 345


def test_parse_rsync_output_large_numbers() -> None:
    """Test parsing rsync output with large byte counts."""
    output = """sending incremental file list
large_file.bin

sent 1,234,567,890 bytes  received 123 bytes  1,234,568,013.00 bytes/sec
total size is 2,000,000,000  speedup is 1.62
"""
    files, bytes_transferred = _parse_rsync_output(output)
    assert files == 1
    assert bytes_transferred == 1234567890


def test_push_result_model() -> None:
    """Test PushResult model creation and serialization."""
    result = PushResult(
        files_transferred=10,
        bytes_transferred=1024,
        source_path=Path("/source/dir"),
        destination_path=Path("/dest/dir"),
        is_dry_run=False,
    )

    assert result.files_transferred == 10
    assert result.bytes_transferred == 1024
    assert result.source_path == Path("/source/dir")
    assert result.destination_path == Path("/dest/dir")
    assert result.is_dry_run is False


def test_push_result_model_dry_run() -> None:
    """Test PushResult model with dry run flag."""
    result = PushResult(
        files_transferred=5,
        bytes_transferred=0,
        source_path=Path("/source"),
        destination_path=Path("/dest"),
        is_dry_run=True,
    )

    assert result.is_dry_run is True


def test_push_git_result_model() -> None:
    """Test PushGitResult model creation."""
    result = PushGitResult(
        source_branch="main",
        target_branch="main",
        source_path=Path("/local/repo"),
        destination_path=Path("/agent/work"),
        is_dry_run=False,
        commits_pushed=5,
    )

    assert result.source_branch == "main"
    assert result.target_branch == "main"
    assert result.commits_pushed == 5
    assert result.is_dry_run is False


def test_handle_uncommitted_changes_no_changes(mock_agent: MagicMock, mock_host_no_uncommitted: MagicMock) -> None:
    """Test handling uncommitted changes when there are none."""
    did_stash = _handle_uncommitted_changes_in_agent(
        mock_agent,
        mock_host_no_uncommitted,
        UncommittedChangesMode.FAIL,
    )
    assert did_stash is False


def test_handle_uncommitted_changes_fail_mode(mock_agent: MagicMock, mock_host_local: MagicMock) -> None:
    """Test that FAIL mode raises when there are uncommitted changes."""
    from imbue.mngr.api.push import UncommittedChangesError

    # Simulate uncommitted changes
    mock_host_local.execute_command.return_value = MagicMock(
        success=True,
        stdout="M modified_file.py\n",
        stderr="",
    )

    with pytest.raises(UncommittedChangesError):
        _handle_uncommitted_changes_in_agent(
            mock_agent,
            mock_host_local,
            UncommittedChangesMode.FAIL,
        )


def test_handle_uncommitted_changes_stash_mode(mock_agent: MagicMock, mock_host_local: MagicMock) -> None:
    """Test that STASH mode stashes uncommitted changes."""
    # First call: git status --porcelain (has changes)
    # Second call: git stash push
    mock_host_local.execute_command.side_effect = [
        MagicMock(success=True, stdout="M modified_file.py\n", stderr=""),
        MagicMock(success=True, stdout="Saved working directory", stderr=""),
    ]

    did_stash = _handle_uncommitted_changes_in_agent(
        mock_agent,
        mock_host_local,
        UncommittedChangesMode.STASH,
    )

    assert did_stash is True
    # Verify git stash was called
    assert mock_host_local.execute_command.call_count == 2


def test_handle_uncommitted_changes_clobber_mode(mock_agent: MagicMock, mock_host_local: MagicMock) -> None:
    """Test that CLOBBER mode resets uncommitted changes."""
    # First call: git status --porcelain (has changes)
    # Second call: git reset --hard HEAD
    # Third call: git clean -fd
    mock_host_local.execute_command.side_effect = [
        MagicMock(success=True, stdout="M modified_file.py\n", stderr=""),
        MagicMock(success=True, stdout="", stderr=""),
        MagicMock(success=True, stdout="", stderr=""),
    ]

    did_stash = _handle_uncommitted_changes_in_agent(
        mock_agent,
        mock_host_local,
        UncommittedChangesMode.CLOBBER,
    )

    assert did_stash is False
    assert mock_host_local.execute_command.call_count == 3


@patch("imbue.mngr.api.push.subprocess.run")
def test_push_files_basic(
    mock_subprocess: MagicMock,
    mock_agent: MagicMock,
    mock_host_no_uncommitted: MagicMock,
) -> None:
    """Test basic push_files operation."""
    mock_subprocess.return_value = MagicMock(
        returncode=0,
        stdout=RSYNC_SUCCESS_OUTPUT,
        stderr="",
    )

    result = push_files(
        agent=mock_agent,
        host=mock_host_no_uncommitted,
        source=Path("/local/source"),
    )

    assert result.source_path == Path("/local/source")
    assert result.destination_path == mock_agent.work_dir
    assert result.is_dry_run is False


@patch("imbue.mngr.api.push.subprocess.run")
def test_push_files_dry_run(
    mock_subprocess: MagicMock,
    mock_agent: MagicMock,
    mock_host_no_uncommitted: MagicMock,
) -> None:
    """Test push_files with dry run flag."""
    mock_subprocess.return_value = MagicMock(
        returncode=0,
        stdout=RSYNC_SUCCESS_OUTPUT,
        stderr="",
    )

    result = push_files(
        agent=mock_agent,
        host=mock_host_no_uncommitted,
        source=Path("/local/source"),
        dry_run=True,
    )

    assert result.is_dry_run is True
    # Verify --dry-run was passed to rsync
    call_args = mock_subprocess.call_args
    assert "--dry-run" in call_args[0][0]


@patch("imbue.mngr.api.push.subprocess.run")
def test_push_files_with_delete(
    mock_subprocess: MagicMock,
    mock_agent: MagicMock,
    mock_host_no_uncommitted: MagicMock,
) -> None:
    """Test push_files with delete flag."""
    mock_subprocess.return_value = MagicMock(
        returncode=0,
        stdout=RSYNC_SUCCESS_OUTPUT,
        stderr="",
    )

    push_files(
        agent=mock_agent,
        host=mock_host_no_uncommitted,
        source=Path("/local/source"),
        delete=True,
    )

    # Verify --delete was passed to rsync
    call_args = mock_subprocess.call_args
    assert "--delete" in call_args[0][0]


@patch("imbue.mngr.api.push.subprocess.run")
def test_push_files_failure(
    mock_subprocess: MagicMock,
    mock_agent: MagicMock,
    mock_host_no_uncommitted: MagicMock,
) -> None:
    """Test push_files handles rsync failure."""
    mock_subprocess.return_value = MagicMock(
        returncode=1,
        stdout="",
        stderr="rsync: connection refused",
    )

    with pytest.raises(MngrError, match="rsync failed"):
        push_files(
            agent=mock_agent,
            host=mock_host_no_uncommitted,
            source=Path("/local/source"),
        )


@patch("imbue.mngr.api.push._is_git_repository")
def test_push_git_not_a_git_repo(
    mock_is_git: MagicMock,
    mock_agent: MagicMock,
    mock_host_local: MagicMock,
) -> None:
    """Test push_git fails when source is not a git repo."""
    from imbue.mngr.api.push import NotAGitRepositoryError

    mock_is_git.return_value = False

    with pytest.raises(NotAGitRepositoryError):
        push_git(
            agent=mock_agent,
            host=mock_host_local,
            source=Path("/not/a/repo"),
        )


@patch("imbue.mngr.api.push._get_current_branch")
@patch("imbue.mngr.api.push._is_git_repository")
def test_push_git_basic(
    mock_is_git: MagicMock,
    mock_get_branch: MagicMock,
    mock_agent: MagicMock,
    mock_host_no_uncommitted: MagicMock,
) -> None:
    """Test basic push_git operation."""
    mock_is_git.return_value = True
    mock_get_branch.return_value = "main"

    # Setup host command responses
    mock_host_no_uncommitted.execute_command.side_effect = [
        # git rev-parse --git-dir (check if agent is git repo)
        MagicMock(success=True, stdout=".git", stderr=""),
        # git rev-parse --abbrev-ref HEAD (get agent's current branch)
        MagicMock(success=True, stdout="main\n", stderr=""),
        # git status --porcelain (check uncommitted changes)
        MagicMock(success=True, stdout="", stderr=""),
        # git rev-parse HEAD (pre-push head)
        MagicMock(success=True, stdout="abc123\n", stderr=""),
        # git remote remove (cleanup old remote)
        MagicMock(success=True, stdout="", stderr=""),
        # git remote add
        MagicMock(success=True, stdout="", stderr=""),
        # git fetch
        MagicMock(success=True, stdout="", stderr=""),
        # git rev-list --count (count commits)
        MagicMock(success=True, stdout="3\n", stderr=""),
        # git rev-parse --abbrev-ref HEAD (get current branch)
        MagicMock(success=True, stdout="main\n", stderr=""),
        # git merge
        MagicMock(success=True, stdout="", stderr=""),
        # git rev-parse HEAD (post-push head)
        MagicMock(success=True, stdout="def456\n", stderr=""),
        # git rev-list --count (count merged commits)
        MagicMock(success=True, stdout="3\n", stderr=""),
        # git remote remove (cleanup)
        MagicMock(success=True, stdout="", stderr=""),
    ]

    result = push_git(
        agent=mock_agent,
        host=mock_host_no_uncommitted,
        source=Path("/local/repo"),
    )

    assert result.source_branch == "main"
    assert result.target_branch == "main"
    assert result.commits_pushed == 3
    assert result.is_dry_run is False


@patch("imbue.mngr.api.push._get_current_branch")
@patch("imbue.mngr.api.push._is_git_repository")
def test_push_git_dry_run(
    mock_is_git: MagicMock,
    mock_get_branch: MagicMock,
    mock_agent: MagicMock,
    mock_host_no_uncommitted: MagicMock,
) -> None:
    """Test push_git with dry run flag."""
    mock_is_git.return_value = True
    mock_get_branch.return_value = "main"

    # Setup host command responses for dry run
    mock_host_no_uncommitted.execute_command.side_effect = [
        # git rev-parse --git-dir (check if agent is git repo)
        MagicMock(success=True, stdout=".git", stderr=""),
        # git rev-parse --abbrev-ref HEAD (get agent's current branch)
        MagicMock(success=True, stdout="main\n", stderr=""),
        # git status --porcelain (check uncommitted changes)
        MagicMock(success=True, stdout="", stderr=""),
        # git rev-parse HEAD (pre-push head)
        MagicMock(success=True, stdout="abc123\n", stderr=""),
        # git remote remove (cleanup old remote)
        MagicMock(success=True, stdout="", stderr=""),
        # git remote add
        MagicMock(success=True, stdout="", stderr=""),
        # git fetch
        MagicMock(success=True, stdout="", stderr=""),
        # git rev-list --count (count commits)
        MagicMock(success=True, stdout="5\n", stderr=""),
        # git remote remove (cleanup)
        MagicMock(success=True, stdout="", stderr=""),
    ]

    result = push_git(
        agent=mock_agent,
        host=mock_host_no_uncommitted,
        source=Path("/local/repo"),
        dry_run=True,
    )

    assert result.is_dry_run is True
    assert result.commits_pushed == 5
