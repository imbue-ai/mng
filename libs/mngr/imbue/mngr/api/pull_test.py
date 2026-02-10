"""Unit tests for pull API functions."""

from pathlib import Path
from typing import Generator
from unittest.mock import MagicMock
from unittest.mock import patch

import pytest

from imbue.mngr.api.pull import pull_files
from imbue.mngr.api.pull import pull_git
from imbue.mngr.api.sync import LocalGitContext
from imbue.mngr.api.sync import NotAGitRepositoryError
from imbue.mngr.errors import MngrError
from imbue.mngr.primitives import UncommittedChangesMode

# Standard rsync --stats output used across tests
RSYNC_SUCCESS_OUTPUT = (
    "Number of files: 1\n"
    "Number of files transferred: 1\n"
    "Total file size: 100 B\n"
    "Total transferred file size: 100 B\n"
    "sent 100 bytes  received 50 bytes\n"
    "total size is 100"
)


@pytest.fixture
def mock_agent() -> MagicMock:
    """Create a mock agent with a standard work_dir."""
    agent = MagicMock()
    agent.work_dir = Path("/agent/work")
    return agent


@pytest.fixture
def mock_host_success() -> MagicMock:
    """Create a mock host that returns successful rsync output."""
    host = MagicMock()
    host.execute_command.return_value = MagicMock(
        success=True,
        stdout=RSYNC_SUCCESS_OUTPUT,
        stderr="",
    )
    return host


@pytest.fixture
def mock_host_failure() -> MagicMock:
    """Create a mock host that returns failed rsync output."""
    host = MagicMock()
    host.execute_command.return_value = MagicMock(
        success=False,
        stdout="",
        stderr="rsync: connection refused",
    )
    return host


@pytest.fixture
def patch_no_uncommitted_changes() -> Generator[MagicMock, None, None]:
    """Patch LocalGitContext.has_uncommitted_changes to return False by default.

    This prevents tests from actually running git status on test paths.
    Tests that need uncommitted changes behavior should use patch_has_uncommitted_changes.
    """
    with patch.object(LocalGitContext, "has_uncommitted_changes", return_value=False) as mock:
        yield mock


@pytest.fixture
def patch_has_uncommitted_changes(
    patch_no_uncommitted_changes: MagicMock,
) -> Generator[MagicMock, None, None]:
    """Override the autouse fixture to return True for uncommitted changes."""
    patch_no_uncommitted_changes.return_value = True
    yield patch_no_uncommitted_changes


def test_pull_files_uses_agent_work_dir_as_default_source(
    mock_agent: MagicMock,
    mock_host_success: MagicMock,
    patch_no_uncommitted_changes: MagicMock,
) -> None:
    """Test that pull_files uses agent work_dir when source_path is None."""
    mock_agent.work_dir = Path("/agent/work/dir")

    result = pull_files(
        agent=mock_agent,
        host=mock_host_success,
        destination=Path("/local/dest"),
        source_path=None,
        dry_run=False,
        delete=False,
    )

    call_args = mock_host_success.execute_command.call_args[0][0]
    assert "/agent/work/dir/" in call_args
    assert result.source_path == Path("/agent/work/dir")


def test_pull_files_uses_provided_source_path(
    mock_agent: MagicMock,
    mock_host_success: MagicMock,
    patch_no_uncommitted_changes: MagicMock,
) -> None:
    """Test that pull_files uses provided source_path when given."""
    custom_source = Path("/custom/source/path")
    result = pull_files(
        agent=mock_agent,
        host=mock_host_success,
        destination=Path("/local/dest"),
        source_path=custom_source,
        dry_run=False,
        delete=False,
    )

    call_args = mock_host_success.execute_command.call_args[0][0]
    assert "/custom/source/path/" in call_args
    assert result.source_path == custom_source


def test_pull_files_with_dry_run_flag(
    mock_agent: MagicMock,
    mock_host_success: MagicMock,
    patch_no_uncommitted_changes: MagicMock,
) -> None:
    """Test that pull_files adds --dry-run flag when dry_run=True."""
    result = pull_files(
        agent=mock_agent,
        host=mock_host_success,
        destination=Path("/local/dest"),
        source_path=None,
        dry_run=True,
        delete=False,
    )

    call_args = mock_host_success.execute_command.call_args[0][0]
    assert "--dry-run" in call_args
    assert result.is_dry_run is True


def test_pull_files_with_delete_flag(
    mock_agent: MagicMock,
    mock_host_success: MagicMock,
    patch_no_uncommitted_changes: MagicMock,
) -> None:
    """Test that pull_files adds --delete flag when delete=True."""
    pull_files(
        agent=mock_agent,
        host=mock_host_success,
        destination=Path("/local/dest"),
        source_path=None,
        dry_run=False,
        delete=True,
    )

    call_args = mock_host_success.execute_command.call_args[0][0]
    assert "--delete" in call_args


def test_pull_files_raises_on_rsync_failure(
    mock_agent: MagicMock,
    mock_host_failure: MagicMock,
    patch_no_uncommitted_changes: MagicMock,
) -> None:
    """Test that pull_files raises MngrError when rsync fails."""
    with pytest.raises(MngrError, match="rsync failed"):
        pull_files(
            agent=mock_agent,
            host=mock_host_failure,
            destination=Path("/local/dest"),
            source_path=None,
            dry_run=False,
            delete=False,
        )


def test_pull_files_rsync_command_format(
    mock_agent: MagicMock,
    mock_host_success: MagicMock,
    patch_no_uncommitted_changes: MagicMock,
) -> None:
    """Test that pull_files builds the correct rsync command format."""
    mock_agent.work_dir = Path("/src")

    pull_files(
        agent=mock_agent,
        host=mock_host_success,
        destination=Path("/dst"),
        source_path=None,
        dry_run=False,
        delete=False,
    )

    call_args = mock_host_success.execute_command.call_args[0][0]
    assert call_args.startswith("rsync")
    assert "-avz" in call_args
    assert "--stats" in call_args
    assert "/src/" in call_args
    assert "/dst" in call_args


def test_pull_files_returns_correct_result_with_file_count(
    mock_agent: MagicMock,
    patch_no_uncommitted_changes: MagicMock,
) -> None:
    """Test that pull_files returns the correct result with file count from rsync output."""
    mock_agent.work_dir = Path("/agent/work/dir")

    mock_host = MagicMock()
    mock_host.execute_command.return_value = MagicMock(
        success=True,
        stdout=(
            "Number of files: 5\n"
            "Number of files transferred: 3\n"
            "Total file size: 15,000 B\n"
            "Total transferred file size: 5,000 B\n"
        ),
        stderr="",
    )

    result = pull_files(
        agent=mock_agent,
        host=mock_host,
        destination=Path("/local/dest"),
        source_path=None,
        dry_run=False,
        delete=False,
    )

    assert result.files_transferred == 3
    assert result.bytes_transferred == 5000
    assert result.source_path == Path("/agent/work/dir")
    assert result.destination_path == Path("/local/dest")
    assert result.is_dry_run is False


def test_pull_files_with_all_flags(
    mock_agent: MagicMock,
    mock_host_success: MagicMock,
    patch_no_uncommitted_changes: MagicMock,
) -> None:
    """Test that pull_files works with both dry_run and delete flags."""
    result = pull_files(
        agent=mock_agent,
        host=mock_host_success,
        destination=Path("/dest"),
        source_path=None,
        dry_run=True,
        delete=True,
    )

    call_args = mock_host_success.execute_command.call_args[0][0]
    assert "--dry-run" in call_args
    assert "--delete" in call_args
    assert result.is_dry_run is True


def test_pull_files_excludes_git_directory(
    mock_agent: MagicMock,
    mock_host_success: MagicMock,
    patch_no_uncommitted_changes: MagicMock,
) -> None:
    """Test that pull_files excludes .git directory from rsync."""
    pull_files(
        agent=mock_agent,
        host=mock_host_success,
        destination=Path("/dest"),
        source_path=None,
        dry_run=False,
        delete=False,
    )

    call_args = mock_host_success.execute_command.call_args[0][0]
    assert "--exclude=.git" in call_args


def test_pull_files_with_clobber_mode_ignores_uncommitted_changes(
    mock_agent: MagicMock,
    mock_host_success: MagicMock,
    patch_has_uncommitted_changes: MagicMock,
) -> None:
    """Test that clobber mode proceeds even when uncommitted changes exist."""
    with patch.object(LocalGitContext, "git_reset_hard"):
        result = pull_files(
            agent=mock_agent,
            host=mock_host_success,
            destination=Path("/dest"),
            source_path=None,
            dry_run=False,
            delete=False,
            uncommitted_changes=UncommittedChangesMode.CLOBBER,
        )

    assert result.files_transferred == 1
    assert result.bytes_transferred == 100


def test_pull_files_default_uncommitted_changes_mode_is_fail(
    mock_agent: MagicMock,
    mock_host_success: MagicMock,
    patch_no_uncommitted_changes: MagicMock,
) -> None:
    """Test that the default uncommitted changes mode is FAIL."""
    # When there are no uncommitted changes, FAIL mode should succeed
    result = pull_files(
        agent=mock_agent,
        host=mock_host_success,
        destination=Path("/nonexistent/dest"),
        source_path=None,
        dry_run=False,
        delete=False,
    )

    assert result.files_transferred == 1


# ============================================================================
# pull_git tests
# ============================================================================


def test_pull_git_raises_when_destination_not_git_repo(
    mock_agent: MagicMock,
    mock_host_success: MagicMock,
    patch_no_uncommitted_changes: MagicMock,
) -> None:
    """Test that pull_git raises NotAGitRepositoryError when destination is not a git repo."""
    with patch.object(LocalGitContext, "is_git_repository", return_value=False):
        with pytest.raises(NotAGitRepositoryError) as exc_info:
            pull_git(
                agent=mock_agent,
                host=mock_host_success,
                destination=Path("/dest"),
            )
        assert exc_info.value.path == Path("/dest")


def test_pull_git_raises_when_source_not_git_repo(
    mock_agent: MagicMock,
    mock_host_success: MagicMock,
    patch_no_uncommitted_changes: MagicMock,
) -> None:
    """Test that pull_git raises NotAGitRepositoryError when source is not a git repo."""
    # Local destination is a git repo, remote source is not
    with patch.object(LocalGitContext, "is_git_repository", return_value=True):
        mock_host_success.execute_command.return_value = MagicMock(success=False)
        with pytest.raises(NotAGitRepositoryError) as exc_info:
            pull_git(
                agent=mock_agent,
                host=mock_host_success,
                destination=Path("/dest"),
            )
        assert exc_info.value.path == Path("/agent/work")
