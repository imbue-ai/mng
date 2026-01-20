"""Tests for logging utilities."""

import tempfile
from pathlib import Path

from imbue.mngr.config.data_types import LoggingConfig
from imbue.mngr.config.data_types import MngrConfig
from imbue.mngr.config.data_types import MngrContext
from imbue.mngr.config.data_types import OutputOptions
from imbue.mngr.primitives import LogLevel
from imbue.mngr.primitives import OutputFormat
from imbue.mngr.utils.logging import _format_arg_value
from imbue.mngr.utils.logging import _resolve_log_dir
from imbue.mngr.utils.logging import _rotate_old_logs
from imbue.mngr.utils.logging import log_call
from imbue.mngr.utils.logging import setup_logging


def test_resolve_log_dir_uses_absolute_path(mngr_test_prefix: str) -> None:
    """Absolute log_dir should be used as-is."""
    config = MngrConfig(
        prefix=mngr_test_prefix,
        default_host_dir=Path("/custom/mngr"),
        logging=LoggingConfig(log_dir=Path("/absolute/path/logs")),
    )

    resolved = _resolve_log_dir(config)

    assert resolved == Path("/absolute/path/logs")


def test_resolve_log_dir_uses_default_host_dir_for_relative(mngr_test_prefix: str) -> None:
    """Relative log_dir should be resolved relative to default_host_dir."""
    config = MngrConfig(
        prefix=mngr_test_prefix,
        default_host_dir=Path("/custom/mngr"),
        logging=LoggingConfig(log_dir=Path("my_logs")),
    )

    resolved = _resolve_log_dir(config)

    assert resolved == Path("/custom/mngr/my_logs")


def test_rotate_old_logs_removes_oldest_files() -> None:
    """Should remove oldest files when exceeding max_files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        log_dir = Path(tmpdir)

        # Create 5 log files
        for i in range(5):
            log_file = log_dir / f"log{i}.json"
            log_file.write_text(f"log {i}")

        # Keep only 3 most recent
        _rotate_old_logs(log_dir, max_files=3)

        remaining = sorted(log_dir.glob("*.json"))
        assert len(remaining) == 3


def test_rotate_old_logs_keeps_all_if_under_limit() -> None:
    """Should not remove files if under max_files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        log_dir = Path(tmpdir)

        # Create 3 log files
        for i in range(3):
            log_file = log_dir / f"log{i}.json"
            log_file.write_text(f"log {i}")

        # Max is 10, so should keep all
        _rotate_old_logs(log_dir, max_files=10)

        remaining = list(log_dir.glob("*.json"))
        assert len(remaining) == 3


def test_rotate_old_logs_handles_nonexistent_dir() -> None:
    """Should not error when log_dir doesn't exist."""
    _rotate_old_logs(Path("/nonexistent/path"), max_files=10)


def test_setup_logging_creates_log_dir(temp_mngr_ctx: MngrContext) -> None:
    """setup_logging should create the log directory if it doesn't exist."""
    log_dir = temp_mngr_ctx.config.default_host_dir / temp_mngr_ctx.config.logging.log_dir
    assert not log_dir.exists()

    output_opts = OutputOptions(
        output_format=OutputFormat.HUMAN,
        console_level=LogLevel.INFO,
        is_log_commands=True,
        is_log_command_output=False,
    )

    setup_logging(output_opts, temp_mngr_ctx)

    assert log_dir.exists()
    assert log_dir.is_dir()


def test_setup_logging_creates_log_file(temp_mngr_ctx: MngrContext) -> None:
    """setup_logging should create a log file."""
    log_dir = temp_mngr_ctx.config.default_host_dir / temp_mngr_ctx.config.logging.log_dir
    output_opts = OutputOptions(
        output_format=OutputFormat.HUMAN,
        console_level=LogLevel.INFO,
        is_log_commands=True,
        is_log_command_output=False,
    )

    setup_logging(output_opts, temp_mngr_ctx)

    log_files = list(log_dir.glob("*.json"))
    assert len(log_files) >= 1


# =============================================================================
# Tests for _format_arg_value
# =============================================================================


def test_format_arg_value_short_value() -> None:
    """_format_arg_value should return short values unchanged."""
    result = _format_arg_value("hello")
    assert result == "'hello'"


def test_format_arg_value_truncates_long_value() -> None:
    """_format_arg_value should truncate values over 200 chars."""
    long_value = "x" * 300
    result = _format_arg_value(long_value)
    assert len(result) == 200
    assert result.endswith("...")


def test_format_arg_value_handles_complex_objects() -> None:
    """_format_arg_value should handle complex objects."""
    complex_obj = {"key": "value", "list": [1, 2, 3]}
    result = _format_arg_value(complex_obj)
    assert "key" in result
    assert "value" in result


# =============================================================================
# Tests for log_call
# =============================================================================


def test_log_call_preserves_function_name() -> None:
    """log_call decorator should preserve function name."""

    @log_call
    def my_function() -> int:
        return 42

    assert my_function.__name__ == "my_function"


def test_log_call_returns_correct_value() -> None:
    """log_call decorator should return the function's return value."""

    @log_call
    def add(a: int, b: int) -> int:
        return a + b

    result = add(3, 5)
    assert result == 8


def test_log_call_handles_kwargs() -> None:
    """log_call decorator should handle keyword arguments."""

    @log_call
    def greet(name: str, greeting: str = "Hello") -> str:
        return f"{greeting}, {name}!"

    result = greet("World", greeting="Hi")
    assert result == "Hi, World!"
