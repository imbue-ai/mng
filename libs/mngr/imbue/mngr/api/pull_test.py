"""Unit tests for pull API functions."""

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from imbue.mngr.api.pull import PullResult
from imbue.mngr.api.pull import _parse_rsync_output
from imbue.mngr.api.pull import pull_files
from imbue.mngr.errors import MngrError


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
    # src/, src/main.py, src/utils.py, tests/, tests/test_main.py = 5 entries
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


def test_pull_files_uses_agent_work_dir_as_default_source() -> None:
    """Test that pull_files uses agent work_dir when source_path is None."""
    mock_agent = MagicMock()
    mock_agent.work_dir = Path("/agent/work/dir")

    mock_host = MagicMock()
    mock_host.execute_command.return_value = MagicMock(
        success=True,
        stdout="sending incremental file list\nsent 100 bytes  received 50 bytes\ntotal size is 1000",
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

    # Verify the rsync command was called with agent's work_dir
    call_args = mock_host.execute_command.call_args[0][0]
    assert "/agent/work/dir/" in call_args
    assert result.source_path == Path("/agent/work/dir")


def test_pull_files_uses_provided_source_path() -> None:
    """Test that pull_files uses provided source_path when given."""
    mock_agent = MagicMock()
    mock_agent.work_dir = Path("/agent/work/dir")

    mock_host = MagicMock()
    mock_host.execute_command.return_value = MagicMock(
        success=True,
        stdout="sending incremental file list\nsent 100 bytes  received 50 bytes\ntotal size is 1000",
        stderr="",
    )

    custom_source = Path("/custom/source/path")
    result = pull_files(
        agent=mock_agent,
        host=mock_host,
        destination=Path("/local/dest"),
        source_path=custom_source,
        dry_run=False,
        delete=False,
    )

    # Verify the rsync command was called with custom source path
    call_args = mock_host.execute_command.call_args[0][0]
    assert "/custom/source/path/" in call_args
    assert result.source_path == custom_source


def test_pull_files_with_dry_run_flag() -> None:
    """Test that pull_files adds --dry-run flag when dry_run=True."""
    mock_agent = MagicMock()
    mock_agent.work_dir = Path("/agent/work/dir")

    mock_host = MagicMock()
    mock_host.execute_command.return_value = MagicMock(
        success=True,
        stdout="sending incremental file list\nsent 100 bytes  received 50 bytes\ntotal size is 1000 (DRY RUN)",
        stderr="",
    )

    result = pull_files(
        agent=mock_agent,
        host=mock_host,
        destination=Path("/local/dest"),
        source_path=None,
        dry_run=True,
        delete=False,
    )

    # Verify the rsync command includes --dry-run
    call_args = mock_host.execute_command.call_args[0][0]
    assert "--dry-run" in call_args
    assert result.is_dry_run is True


def test_pull_files_with_delete_flag() -> None:
    """Test that pull_files adds --delete flag when delete=True."""
    mock_agent = MagicMock()
    mock_agent.work_dir = Path("/agent/work/dir")

    mock_host = MagicMock()
    mock_host.execute_command.return_value = MagicMock(
        success=True,
        stdout="sending incremental file list\nsent 100 bytes  received 50 bytes\ntotal size is 1000",
        stderr="",
    )

    pull_files(
        agent=mock_agent,
        host=mock_host,
        destination=Path("/local/dest"),
        source_path=None,
        dry_run=False,
        delete=True,
    )

    # Verify the rsync command includes --delete
    call_args = mock_host.execute_command.call_args[0][0]
    assert "--delete" in call_args


def test_pull_files_raises_on_rsync_failure() -> None:
    """Test that pull_files raises MngrError when rsync fails."""
    mock_agent = MagicMock()
    mock_agent.work_dir = Path("/agent/work/dir")

    mock_host = MagicMock()
    mock_host.execute_command.return_value = MagicMock(
        success=False,
        stdout="",
        stderr="rsync: connection refused",
    )

    with pytest.raises(MngrError, match="rsync failed"):
        pull_files(
            agent=mock_agent,
            host=mock_host,
            destination=Path("/local/dest"),
            source_path=None,
            dry_run=False,
            delete=False,
        )


def test_pull_files_rsync_command_format() -> None:
    """Test that pull_files builds the correct rsync command format."""
    mock_agent = MagicMock()
    mock_agent.work_dir = Path("/src")

    mock_host = MagicMock()
    mock_host.execute_command.return_value = MagicMock(
        success=True,
        stdout="sending incremental file list\nsent 100 bytes  received 50 bytes\ntotal size is 1000",
        stderr="",
    )

    pull_files(
        agent=mock_agent,
        host=mock_host,
        destination=Path("/dst"),
        source_path=None,
        dry_run=False,
        delete=False,
    )

    # Verify rsync command structure
    call_args = mock_host.execute_command.call_args[0][0]
    assert call_args.startswith("rsync")
    assert "-avz" in call_args
    assert "--progress" in call_args
    assert "/src/" in call_args
    assert "/dst" in call_args


def test_pull_files_returns_correct_result_with_file_count() -> None:
    """Test that pull_files returns the correct result with file count from rsync output."""
    mock_agent = MagicMock()
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


def test_pull_files_with_all_flags() -> None:
    """Test that pull_files works with both dry_run and delete flags."""
    mock_agent = MagicMock()
    mock_agent.work_dir = Path("/agent/work")

    mock_host = MagicMock()
    mock_host.execute_command.return_value = MagicMock(
        success=True,
        stdout="sending incremental file list\nsent 100 bytes  received 50 bytes\ntotal size is 1000 (DRY RUN)",
        stderr="",
    )

    result = pull_files(
        agent=mock_agent,
        host=mock_host,
        destination=Path("/dest"),
        source_path=None,
        dry_run=True,
        delete=True,
    )

    # Verify the rsync command includes both flags
    call_args = mock_host.execute_command.call_args[0][0]
    assert "--dry-run" in call_args
    assert "--delete" in call_args
    assert result.is_dry_run is True
