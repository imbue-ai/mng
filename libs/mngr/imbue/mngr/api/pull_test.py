"""Unit tests for pull API functions."""

from pathlib import Path
from typing import Generator
from unittest.mock import MagicMock
from unittest.mock import patch

import pytest

from imbue.mngr.api.pull import PullResult
from imbue.mngr.api.pull import UncommittedChangesError
from imbue.mngr.api.pull import _parse_rsync_output
from imbue.mngr.api.pull import pull_files
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


@pytest.fixture(autouse=True)
def patch_no_uncommitted_changes() -> Generator[MagicMock, None, None]:
    """Patch _has_uncommitted_changes to return False by default.

    This prevents tests from actually running git status on test paths.
    Tests that need uncommitted changes behavior should use patch_has_uncommitted_changes.
    """
    with patch("imbue.mngr.api.pull._has_uncommitted_changes", return_value=False) as mock:
        yield mock


@pytest.fixture
def patch_has_uncommitted_changes(
    patch_no_uncommitted_changes: MagicMock,
) -> Generator[MagicMock, None, None]:
    """Override the autouse fixture to return True for uncommitted changes."""
    patch_no_uncommitted_changes.return_value = True
    yield patch_no_uncommitted_changes


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


def test_parse_rsync_output_with_subdirectory() -> None:
    """Test parsing rsync output with subdirectories."""
    output = """sending incremental file list
src/
src/main.py
src/utils.py
tests/
tests/test_main.py

sent 5,000 bytes  received 200 bytes  5,200.00 bytes/sec
total size is 15,000  speedup is 2.88
"""
    files, bytes_transferred = _parse_rsync_output(output)
    assert files == 5
    assert bytes_transferred == 5000


def test_pull_result_model() -> None:
    """Test PullResult model creation and serialization."""
    result = PullResult(
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


def test_pull_result_model_dry_run() -> None:
    """Test PullResult model with dry run flag."""
    result = PullResult(
        files_transferred=5,
        bytes_transferred=0,
        source_path=Path("/source"),
        destination_path=Path("/dest"),
        is_dry_run=True,
    )

    assert result.is_dry_run is True


def test_pull_result_model_serialization() -> None:
    """Test PullResult model can be serialized to dict."""
    result = PullResult(
        files_transferred=3,
        bytes_transferred=500,
        source_path=Path("/src"),
        destination_path=Path("/dst"),
        is_dry_run=False,
    )

    data = result.model_dump()
    assert data["files_transferred"] == 3
    assert data["bytes_transferred"] == 500
    assert data["source_path"] == Path("/src")
    assert data["destination_path"] == Path("/dst")
    assert data["is_dry_run"] is False


def test_parse_rsync_output_with_no_bytes_line() -> None:
    """Test parsing rsync output when bytes line is missing."""
    output = """sending incremental file list
file1.txt
file2.txt
"""
    files, bytes_transferred = _parse_rsync_output(output)
    assert files == 2
    assert bytes_transferred == 0


def test_parse_rsync_output_with_malformed_bytes() -> None:
    """Test parsing rsync output with malformed bytes line."""
    output = """sending incremental file list
file1.txt

sent abc bytes  received def bytes
total size is 1,000
"""
    files, bytes_transferred = _parse_rsync_output(output)
    assert files == 1
    assert bytes_transferred == 0


def test_parse_rsync_output_empty_string() -> None:
    """Test parsing empty rsync output."""
    output = ""
    files, bytes_transferred = _parse_rsync_output(output)
    assert files == 0
    assert bytes_transferred == 0


def test_parse_rsync_output_whitespace_only() -> None:
    """Test parsing rsync output with only whitespace."""
    output = "   \n  \n   "
    files, bytes_transferred = _parse_rsync_output(output)
    assert files == 0
    assert bytes_transferred == 0


def test_pull_files_uses_agent_work_dir_as_default_source(
    mock_agent: MagicMock,
    mock_host_success: MagicMock,
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
    assert "--progress" in call_args
    assert "/src/" in call_args
    assert "/dst" in call_args


def test_pull_files_returns_correct_result_with_file_count(
    mock_agent: MagicMock,
) -> None:
    """Test that pull_files returns the correct result with file count from rsync output."""
    mock_agent.work_dir = Path("/agent/work/dir")

    mock_host = MagicMock()
    mock_host.execute_command.return_value = MagicMock(
        success=True,
        stdout="""sending incremental file list
file1.txt
file2.py
file3.md

sent 5,000 bytes  received 200 bytes  5,200.00 bytes/sec
total size is 15,000  speedup is 2.88
""",
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
    result = pull_files(
        agent=mock_agent,
        host=mock_host_success,
        destination=Path("/dest"),
        source_path=None,
        dry_run=False,
        delete=False,
        uncommitted_changes=UncommittedChangesMode.CLOBBER,
    )

    assert result.files_transferred == 0
    assert result.bytes_transferred == 100


def test_uncommitted_changes_error_has_user_help_text() -> None:
    """Test that UncommittedChangesError has helpful user text."""
    error = UncommittedChangesError(Path("/some/path"))
    assert "stash" in error.user_help_text
    assert "clobber" in error.user_help_text
    assert "merge" in error.user_help_text
    assert error.destination == Path("/some/path")


def test_pull_files_default_uncommitted_changes_mode_is_fail(
    mock_agent: MagicMock,
    mock_host_success: MagicMock,
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

    assert result.files_transferred == 0


def test_pull_files_fail_mode_raises_when_uncommitted_changes_exist(
    mock_agent: MagicMock,
    mock_host_success: MagicMock,
    patch_has_uncommitted_changes: MagicMock,
) -> None:
    """Test that FAIL mode raises UncommittedChangesError when uncommitted changes exist."""
    with pytest.raises(UncommittedChangesError) as exc_info:
        pull_files(
            agent=mock_agent,
            host=mock_host_success,
            destination=Path("/dest"),
            source_path=None,
            dry_run=False,
            delete=False,
            uncommitted_changes=UncommittedChangesMode.FAIL,
        )

    assert exc_info.value.destination == Path("/dest")


def test_pull_files_stash_mode_stashes_and_leaves_stashed(
    mock_agent: MagicMock,
    mock_host_success: MagicMock,
    patch_has_uncommitted_changes: MagicMock,
) -> None:
    """Test that STASH mode stashes changes and leaves them stashed after pull."""
    with patch("imbue.mngr.api.pull._git_stash", return_value=True) as mock_stash:
        with patch("imbue.mngr.api.pull._git_stash_pop") as mock_pop:
            result = pull_files(
                agent=mock_agent,
                host=mock_host_success,
                destination=Path("/dest"),
                source_path=None,
                dry_run=False,
                delete=False,
                uncommitted_changes=UncommittedChangesMode.STASH,
            )

    mock_stash.assert_called_once_with(Path("/dest"))
    mock_pop.assert_not_called()
    assert result.files_transferred == 0


def test_pull_files_merge_mode_stashes_and_restores(
    mock_agent: MagicMock,
    mock_host_success: MagicMock,
    patch_has_uncommitted_changes: MagicMock,
) -> None:
    """Test that MERGE mode stashes changes before pull and restores them after."""
    with patch("imbue.mngr.api.pull._git_stash", return_value=True) as mock_stash:
        with patch("imbue.mngr.api.pull._git_stash_pop") as mock_pop:
            result = pull_files(
                agent=mock_agent,
                host=mock_host_success,
                destination=Path("/dest"),
                source_path=None,
                dry_run=False,
                delete=False,
                uncommitted_changes=UncommittedChangesMode.MERGE,
            )

    mock_stash.assert_called_once_with(Path("/dest"))
    mock_pop.assert_called_once_with(Path("/dest"))
    assert result.files_transferred == 0


def test_pull_files_merge_mode_restores_stash_on_rsync_failure(
    mock_agent: MagicMock,
    mock_host_failure: MagicMock,
    patch_has_uncommitted_changes: MagicMock,
) -> None:
    """Test that MERGE mode attempts to restore stash when rsync fails."""
    with patch("imbue.mngr.api.pull._git_stash", return_value=True) as mock_stash:
        with patch("imbue.mngr.api.pull._git_stash_pop") as mock_pop:
            with pytest.raises(MngrError, match="rsync failed"):
                pull_files(
                    agent=mock_agent,
                    host=mock_host_failure,
                    destination=Path("/dest"),
                    source_path=None,
                    dry_run=False,
                    delete=False,
                    uncommitted_changes=UncommittedChangesMode.MERGE,
                )

    mock_stash.assert_called_once_with(Path("/dest"))
    mock_pop.assert_called_once_with(Path("/dest"))


def test_pull_files_stash_mode_does_not_restore_on_rsync_failure(
    mock_agent: MagicMock,
    mock_host_failure: MagicMock,
    patch_has_uncommitted_changes: MagicMock,
) -> None:
    """Test that STASH mode does NOT restore stash when rsync fails (leaves stashed)."""
    with patch("imbue.mngr.api.pull._git_stash", return_value=True) as mock_stash:
        with patch("imbue.mngr.api.pull._git_stash_pop") as mock_pop:
            with pytest.raises(MngrError, match="rsync failed"):
                pull_files(
                    agent=mock_agent,
                    host=mock_host_failure,
                    destination=Path("/dest"),
                    source_path=None,
                    dry_run=False,
                    delete=False,
                    uncommitted_changes=UncommittedChangesMode.STASH,
                )

    mock_stash.assert_called_once_with(Path("/dest"))
    mock_pop.assert_not_called()
