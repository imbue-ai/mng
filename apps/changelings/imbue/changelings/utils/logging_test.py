# Tests for the changelings logging setup.

from pathlib import Path

from loguru import logger

from imbue.changelings.data_types import OutputOptions
from imbue.changelings.primitives import LogLevel
from imbue.changelings.primitives import OutputFormat
from imbue.changelings.utils.logging import _format_user_message
from imbue.changelings.utils.logging import _get_default_log_dir
from imbue.changelings.utils.logging import _rotate_old_logs
from imbue.changelings.utils.logging import register_build_level
from imbue.changelings.utils.logging import setup_logging


def test_register_build_level_is_idempotent() -> None:
    """Calling register_build_level multiple times should not raise."""
    register_build_level()
    register_build_level()

    # Verify the BUILD level exists
    level = logger.level("BUILD")
    assert level.no == 15


def test_format_user_message_warning() -> None:
    """WARNING messages should get the WARNING prefix and gold color."""
    record = {"level": type("Level", (), {"name": "WARNING"})()}
    result = _format_user_message(record)
    assert "WARNING:" in result
    assert "{message}" in result


def test_format_user_message_error() -> None:
    """ERROR messages should get the ERROR prefix and red color."""
    record = {"level": type("Level", (), {"name": "ERROR"})()}
    result = _format_user_message(record)
    assert "ERROR:" in result
    assert "{message}" in result


def test_format_user_message_build() -> None:
    """BUILD messages should get gray color formatting."""
    record = {"level": type("Level", (), {"name": "BUILD"})()}
    result = _format_user_message(record)
    assert "{message}" in result
    # BUILD messages have gray color but no prefix
    assert "BUILD" not in result


def test_format_user_message_debug() -> None:
    """DEBUG messages should get blue color formatting."""
    record = {"level": type("Level", (), {"name": "DEBUG"})()}
    result = _format_user_message(record)
    assert "{message}" in result


def test_format_user_message_trace() -> None:
    """TRACE messages should get purple color formatting."""
    record = {"level": type("Level", (), {"name": "TRACE"})()}
    result = _format_user_message(record)
    assert "{message}" in result


def test_format_user_message_info() -> None:
    """INFO messages should get plain formatting (no color prefix)."""
    record = {"level": type("Level", (), {"name": "INFO"})()}
    result = _format_user_message(record)
    assert result == "{message}\n"


def test_get_default_log_dir() -> None:
    """The default log directory should be under ~/.changelings/logs."""
    log_dir = _get_default_log_dir()
    assert log_dir == Path.home() / ".changelings" / "logs"


def test_setup_logging_creates_log_file(tmp_path: Path) -> None:
    """setup_logging should create a log file in the default log directory."""
    output_opts = OutputOptions(
        output_format=OutputFormat.HUMAN,
        console_level=LogLevel.BUILD,
        log_file_path=None,
    )

    setup_logging(output_opts)

    # Log directory should have been created (in HOME which is tmp_path for tests)
    log_dir = Path.home() / ".changelings" / "logs"
    assert log_dir.exists()

    # There should be a .json log file
    json_files = list(log_dir.glob("*.json"))
    assert len(json_files) >= 1


def test_setup_logging_uses_custom_log_file(tmp_path: Path) -> None:
    """When log_file_path is set, logging should write to that path."""
    custom_log_path = tmp_path / "custom" / "test.json"
    output_opts = OutputOptions(
        output_format=OutputFormat.HUMAN,
        console_level=LogLevel.BUILD,
        log_file_path=custom_log_path,
    )

    setup_logging(output_opts)

    # The parent directory should have been created
    assert custom_log_path.parent.exists()


def test_setup_logging_with_none_console_level(tmp_path: Path) -> None:
    """When console_level is NONE, no console handler should be added."""
    output_opts = OutputOptions(
        output_format=OutputFormat.HUMAN,
        console_level=LogLevel.NONE,
        log_file_path=None,
    )

    setup_logging(output_opts)

    # Should not raise; logging is configured but console output is suppressed


def test_rotate_old_logs_removes_excess_files(tmp_path: Path) -> None:
    """Rotation should remove oldest log files when exceeding max_files."""
    # Create more files than the max
    for i in range(5):
        log_file = tmp_path / f"test-{i:04d}.json"
        log_file.write_text("{}")

    _rotate_old_logs(tmp_path, max_files=2)

    remaining = list(tmp_path.glob("*.json"))
    assert len(remaining) == 2


def test_rotate_old_logs_does_nothing_when_under_limit(tmp_path: Path) -> None:
    """Rotation should not remove files when count is under max_files."""
    for i in range(3):
        log_file = tmp_path / f"test-{i:04d}.json"
        log_file.write_text("{}")

    _rotate_old_logs(tmp_path, max_files=10)

    remaining = list(tmp_path.glob("*.json"))
    assert len(remaining) == 3


def test_rotate_old_logs_handles_nonexistent_directory() -> None:
    """Rotation should handle a nonexistent directory gracefully."""
    _rotate_old_logs(Path("/nonexistent/path"), max_files=10)
    # Should not raise
