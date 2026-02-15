import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any
from typing import Final

from loguru import logger

from imbue.changelings.data_types import OutputOptions
from imbue.changelings.primitives import LogLevel

# ANSI color codes that work well on both light and dark backgrounds.
# Using 256-color palette codes with bold for better visibility.
# Falls back gracefully in terminals that don't support 256 colors.
# WARNING_COLOR: Bold gold/orange (256-color code 178)
# ERROR_COLOR: Bold red (256-color code 196)
# BUILD_COLOR: Medium gray (256-color code 245) - visible on both black and white backgrounds
# DEBUG_COLOR: Solid blue (256-color code 33)
# TRACE COLOR: Purple (256-color code 99)
WARNING_COLOR: Final[str] = "\x1b[1;38;5;178m"
ERROR_COLOR: Final[str] = "\x1b[1;38;5;196m"
BUILD_COLOR: Final[str] = "\x1b[38;5;245m"
DEBUG_COLOR: Final[str] = "\x1b[38;5;33m"
TRACE_COLOR: Final[str] = "\x1b[38;5;99m"
RESET_COLOR: Final[str] = "\x1b[0m"

# Custom loguru log level number for BUILD (between DEBUG=10 and INFO=20)
BUILD_LEVEL_NO: Final[int] = 15

# Default log directory lives under the changelings config dir
CONFIG_DIR_NAME: Final[str] = ".changelings"
DEFAULT_LOG_DIR_NAME: Final[str] = "logs"
DEFAULT_MAX_LOG_FILES: Final[int] = 100
DEFAULT_MAX_LOG_SIZE_MB: Final[int] = 10


def register_build_level() -> None:
    """Register the custom BUILD log level with loguru.

    This is called at module import time to ensure the BUILD level is always
    available when using logger.log("BUILD", ...). The function is idempotent
    and can be called multiple times safely.

    The BUILD level (severity 15) sits between DEBUG (10) and INFO (20),
    intended for build output.
    """
    try:
        logger.level("BUILD")
    except ValueError:
        # Level doesn't exist, create it
        logger.level("BUILD", no=BUILD_LEVEL_NO, color="<white>")


# Register BUILD level at module import time
register_build_level()


def _dynamic_stdout_sink(message: Any) -> None:
    """Loguru sink that always writes to the current sys.stdout.

    When loguru receives a stream via logger.add(sys.stdout), it captures the object
    reference at that moment. If the stream is later replaced (e.g., by pytest's capture
    mechanism) or closed, the handler writes to a stale/closed object, causing
    ValueError("I/O operation on closed file").

    This callable sink solves the problem by resolving sys.stdout at write time, so it
    always writes to whatever sys.stdout currently points to.
    """
    sys.stdout.write(str(message))
    sys.stdout.flush()


def _format_user_message(record: Any) -> str:
    """Format user-facing log messages, adding colored prefixes for warnings and errors.

    The record parameter is a loguru Record TypedDict, but the type is only available
    in type stubs so we use Any here.
    """
    level_name = record["level"].name
    if level_name == "WARNING":
        return f"{WARNING_COLOR}WARNING: {{message}}{RESET_COLOR}\n"
    if level_name == "ERROR":
        return f"{ERROR_COLOR}ERROR: {{message}}{RESET_COLOR}\n"
    if level_name == "BUILD":
        return f"{BUILD_COLOR}{{message}}{RESET_COLOR}\n"
    if level_name == "DEBUG":
        return f"{DEBUG_COLOR}{{message}}{RESET_COLOR}\n"
    if level_name == "TRACE":
        return f"{TRACE_COLOR}{{message}}{RESET_COLOR}\n"
    return "{message}\n"


def _get_default_log_dir() -> Path:
    """Get the default log directory (~/.changelings/logs/)."""
    return Path.home() / CONFIG_DIR_NAME / DEFAULT_LOG_DIR_NAME


def setup_logging(output_opts: OutputOptions) -> None:
    """Configure logging based on output options.

    Sets up:
    - stdout logging for user-facing messages (clean format with colored prefixes)
    - File logging to custom path (if log_file_path provided) or
      ~/.changelings/logs/<timestamp>-<pid>.json (default)
    - Log rotation based on defaults (only for default log directory)
    """
    # Remove default handler
    logger.remove()

    # BUILD level is registered at module import time via register_build_level()

    # Set up stdout logging for user messages (clean format, with colored WARNING prefix).
    # We set colorize=False because we handle colors manually in _format_user_message.
    # Use callable sink so the handler always writes to the current sys.stdout,
    # even if it gets replaced (e.g., by pytest's capture mechanism).
    if output_opts.console_level != LogLevel.NONE:
        logger.add(
            _dynamic_stdout_sink,
            level=output_opts.console_level,
            format=_format_user_message,
            colorize=False,
            diagnose=False,
        )

    # Set up file logging
    # Use provided log file path if specified, otherwise use default directory
    if output_opts.log_file_path is not None:
        log_file = output_opts.log_file_path.expanduser()
        # Ensure parent directory exists
        log_file.parent.mkdir(parents=True, exist_ok=True)
        is_using_custom_log_path = True
    else:
        is_using_custom_log_path = False
        log_dir = _get_default_log_dir()
        log_dir.mkdir(parents=True, exist_ok=True)
        # Create log file path with timestamp and PID
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        pid = os.getpid()
        log_file = log_dir / f"{timestamp}-{pid}.json"

    logger.add(
        log_file,
        level="DEBUG",
        format="{message}",
        serialize=True,
        diagnose=False,
        rotation=f"{DEFAULT_MAX_LOG_SIZE_MB} MB",
    )

    # Rotate old logs if needed (only for default log directory to avoid
    # accidentally deleting unrelated .json files when custom path is used)
    if not is_using_custom_log_path:
        _rotate_old_logs(log_dir, DEFAULT_MAX_LOG_FILES)


def _rotate_old_logs(log_dir: Path, max_files: int) -> None:
    """Remove oldest log files if we exceed max_files.

    Uses least-recently-modified strategy. Robust to concurrent access
    from multiple instances - failures during deletion are silently ignored.
    """
    if not log_dir.exists():
        return

    try:
        # Get all .json log files
        log_files = sorted(log_dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    except OSError:
        # If we can't read the directory, just skip rotation
        return

    # Remove oldest files if we exceed max_files
    if len(log_files) > max_files:
        for old_log in log_files[max_files:]:
            try:
                old_log.unlink()
            except (OSError, FileNotFoundError):
                # File might have been deleted by another instance, or
                # we might not have permission - either way, ignore and continue
                pass
