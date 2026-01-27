import functools
import inspect
import os
import sys
from collections import deque
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any
from typing import Final
from typing import NamedTuple
from typing import ParamSpec
from typing import TypeVar

import deal
from loguru import logger

from imbue.mngr.config.data_types import MngrConfig
from imbue.mngr.config.data_types import MngrContext
from imbue.mngr.config.data_types import OutputOptions
from imbue.mngr.primitives import LogLevel


# ANSI color codes that work well on both light and dark backgrounds.
# Using 256-color palette codes with bold for better visibility.
# Falls back gracefully in terminals that don't support 256 colors.
# WARNING_COLOR: Bold gold/orange (256-color code 178)
# ERROR_COLOR: Bold red (256-color code 196)
# BUILD_COLOR: Medium gray (256-color code 245) - visible on both black and white backgrounds
# DEBUG_COLOR: Solid blue (256-color code 33)
WARNING_COLOR = "\x1b[1;38;5;178m"
ERROR_COLOR = "\x1b[1;38;5;196m"
BUILD_COLOR = "\x1b[38;5;245m"
DEBUG_COLOR = "\x1b[38;5;33m"
RESET_COLOR = "\x1b[0m"

# Custom loguru log level number for BUILD (between DEBUG=10 and INFO=20)
BUILD_LEVEL_NO: Final[int] = 15


def register_build_level() -> None:
    """Register the custom BUILD log level with loguru.

    This is called at module import time to ensure the BUILD level is always
    available when using logger.log("BUILD", ...). The function is idempotent
    and can be called multiple times safely.

    The BUILD level (severity 15) sits between DEBUG (10) and INFO (20),
    intended for image build output (Modal, Docker, etc).
    """
    try:
        logger.level("BUILD")
    except ValueError:
        # Level doesn't exist, create it
        logger.level("BUILD", no=BUILD_LEVEL_NO, color="<white>")


# Register BUILD level at module import time
register_build_level()

# Default buffer size for suppressed log messages
DEFAULT_BUFFER_SIZE: Final[int] = 500

# ANSI escape codes for screen control
CLEAR_SCREEN: Final[str] = "\x1b[2J\x1b[H"

# Module-level storage for console handler IDs (used by LoggingSuppressor)
_console_handler_ids: dict[str, int] = {}


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
    return "{message}\n"


def setup_logging(output_opts: OutputOptions, mngr_ctx: MngrContext) -> None:
    """Configure logging based on output options and mngr context.

    Sets up:
    - stdout logging for user-facing messages (clean format)
    - stderr logging for structured diagnostic messages (detailed format)
    - File logging to custom path (if log_file_path provided) or
      ~/.mngr/logs/<timestamp>-<pid>.json (default)
    - Log rotation based on config (only for default log directory)
    """
    # Remove default handler
    logger.remove()

    # BUILD level is registered at module import time via register_build_level()

    # Map our LogLevel enum to loguru levels
    level_map = {
        LogLevel.TRACE: "TRACE",
        LogLevel.DEBUG: "DEBUG",
        LogLevel.BUILD: "BUILD",
        LogLevel.INFO: "INFO",
        LogLevel.WARN: "WARNING",
        LogLevel.ERROR: "ERROR",
        LogLevel.NONE: "CRITICAL",
    }

    # Clear stored handler IDs from previous setup (if any)
    _console_handler_ids.clear()

    # Set up stdout logging for user messages (clean format, with colored WARNING prefix).
    # We set colorize=False because we handle colors manually in _format_user_message.
    if output_opts.console_level != LogLevel.NONE:
        handler_id = logger.add(
            sys.stdout,
            level=output_opts.console_level,
            format=_format_user_message,
            colorize=False,
            diagnose=False,
        )
        _console_handler_ids["stdout"] = handler_id

    # Set up stderr logging for diagnostics (structured format)
    # Shows all messages at console_level with detailed formatting
    if output_opts.log_level != LogLevel.NONE:
        console_level = level_map[output_opts.log_level]
        handler_id = logger.add(
            sys.stderr,
            level=console_level,
            format="<level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan> - <level>{message}</level>",
            colorize=True,
            diagnose=False,
        )
        _console_handler_ids["stderr"] = handler_id

    # Set up file logging
    # Use provided log file path if specified, otherwise use default directory
    is_using_custom_log_path = output_opts.log_file_path is not None
    if is_using_custom_log_path:
        log_file = output_opts.log_file_path.expanduser()
        # Ensure parent directory exists
        log_file.parent.mkdir(parents=True, exist_ok=True)
    else:
        log_dir = _resolve_log_dir(mngr_ctx.config)
        log_dir.mkdir(parents=True, exist_ok=True)
        # Create log file path with timestamp and PID
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        pid = os.getpid()
        log_file = log_dir / f"{timestamp}-{pid}.json"

    file_level = level_map[mngr_ctx.config.logging.file_level]
    logger.add(
        log_file,
        level=file_level,
        format="{message}",
        serialize=True,
        diagnose=False,
        rotation=f"{mngr_ctx.config.logging.max_log_size_mb} MB",
    )

    # Rotate old logs if needed (only for default log directory to avoid
    # accidentally deleting unrelated .json files when custom path is used)
    if not is_using_custom_log_path:
        _rotate_old_logs(log_dir, mngr_ctx.config.logging.max_log_files)


def _resolve_log_dir(config: MngrConfig) -> Path:
    """Resolve the log directory path.

    If log_dir is relative, it's relative to default_host_dir.
    """
    log_dir = config.logging.log_dir

    if not log_dir.is_absolute():
        # Resolve relative to host dir
        host_dir = config.default_host_dir.expanduser()
        log_dir = host_dir / log_dir

    return log_dir.expanduser()


def _rotate_old_logs(log_dir: Path, max_files: int) -> None:
    """Remove oldest log files if we exceed max_files.

    Uses least-recently-modified strategy. Robust to concurrent access
    from multiple mngr instances - failures during deletion are silently
    ignored.
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
                # File might have been deleted by another mngr instance, or
                # we might not have permission - either way, ignore and continue
                pass


P = ParamSpec("P")
R = TypeVar("R")


@deal.has()
def _format_arg_value(value: Any) -> str:
    """Format an argument value for logging, truncating if too long."""
    str_value = repr(value)
    max_len = 200
    if len(str_value) > max_len:
        return str_value[: max_len - 3] + "..."
    return str_value


def log_call(func: Callable[P, R]) -> Callable[P, R]:
    """Decorator that logs function calls with inputs and outputs at debug level.

    Logs the function name and binds arguments as structured logging fields.
    Useful for API entry points to trace execution.
    """
    # Get the function name once at decoration time
    func_name = getattr(func, "__name__", repr(func))

    @functools.wraps(func)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
        # Get the function signature to map positional args to names
        sig = inspect.signature(func)
        bound_args = sig.bind(*args, **kwargs)
        bound_args.apply_defaults()

        # Build structured logging fields from arguments
        log_fields = {name: _format_arg_value(value) for name, value in bound_args.arguments.items()}
        logger.debug("Calling {}", func_name, **log_fields)

        result = func(*args, **kwargs)

        logger.debug("{} returned", func_name, result=_format_arg_value(result))

        return result

    return wrapper


class BufferedMessage(NamedTuple):
    """A buffered log message with its formatted output and destination."""

    formatted_message: str
    is_stderr: bool


class LoggingSuppressor:
    """Manages temporary suppression and buffering of console log output.

    When suppression is enabled, console log messages (stdout/stderr) are
    buffered instead of being written immediately. File logging is not affected.

    Use as a context manager or call enable/disable explicitly.
    """

    # Class-level state for the singleton suppressor
    _is_suppressed: bool = False
    _buffer: deque[BufferedMessage] = deque(maxlen=DEFAULT_BUFFER_SIZE)
    _stdout_handler_id: int | None = None
    _stderr_handler_id: int | None = None
    _suppressed_stdout_handler_id: int | None = None
    _suppressed_stderr_handler_id: int | None = None
    _output_opts: OutputOptions | None = None

    @classmethod
    def is_suppressed(cls) -> bool:
        """Check if logging suppression is currently active."""
        return cls._is_suppressed

    @classmethod
    def enable(cls, output_opts: OutputOptions, buffer_size: int = DEFAULT_BUFFER_SIZE) -> None:
        """Enable logging suppression and start buffering console output.

        The buffer will keep the most recent buffer_size messages. File logging
        is not affected - only stdout and stderr console handlers are suppressed.
        """
        if cls._is_suppressed:
            return

        cls._output_opts = output_opts
        cls._buffer = deque(maxlen=buffer_size)
        cls._is_suppressed = True

        # Remove only the console handlers (preserving file logging)
        # The handler IDs are stored in _console_handler_ids by setup_logging()
        if "stdout" in _console_handler_ids:
            try:
                logger.remove(_console_handler_ids["stdout"])
            except ValueError:
                pass
        if "stderr" in _console_handler_ids:
            try:
                logger.remove(_console_handler_ids["stderr"])
            except ValueError:
                pass

        # Add buffering handlers that capture messages instead of writing to console
        if output_opts.console_level != LogLevel.NONE:
            cls._suppressed_stdout_handler_id = logger.add(
                cls._buffered_stdout_sink,
                level=output_opts.console_level,
                format=_format_user_message,
                colorize=False,
                diagnose=False,
            )

        if output_opts.log_level != LogLevel.NONE:
            level_map = {
                LogLevel.TRACE: "TRACE",
                LogLevel.DEBUG: "DEBUG",
                LogLevel.BUILD: "BUILD",
                LogLevel.INFO: "INFO",
                LogLevel.WARN: "WARNING",
                LogLevel.ERROR: "ERROR",
                LogLevel.NONE: "CRITICAL",
            }
            cls._suppressed_stderr_handler_id = logger.add(
                cls._buffered_stderr_sink,
                level=level_map[output_opts.log_level],
                format="<level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan> - <level>{message}</level>",
                colorize=True,
                diagnose=False,
            )

    @classmethod
    def _buffered_stdout_sink(cls, message: Any) -> None:
        """Sink function that buffers messages intended for stdout."""
        cls._buffer.append(BufferedMessage(str(message), is_stderr=False))

    @classmethod
    def _buffered_stderr_sink(cls, message: Any) -> None:
        """Sink function that buffers messages intended for stderr."""
        cls._buffer.append(BufferedMessage(str(message), is_stderr=True))

    @classmethod
    def disable_and_replay(cls, clear_screen: bool = True) -> None:
        """Disable suppression and replay buffered messages.

        If clear_screen is True, clears the terminal before replaying messages.
        """
        if not cls._is_suppressed:
            return

        cls._is_suppressed = False
        output_opts = cls._output_opts

        # Remove the buffering handlers
        if cls._suppressed_stdout_handler_id is not None:
            logger.remove(cls._suppressed_stdout_handler_id)
            cls._suppressed_stdout_handler_id = None
        if cls._suppressed_stderr_handler_id is not None:
            logger.remove(cls._suppressed_stderr_handler_id)
            cls._suppressed_stderr_handler_id = None

        # Clear the screen if requested
        if clear_screen:
            sys.stdout.write(CLEAR_SCREEN)
            sys.stdout.flush()

        # Replay buffered messages to their original destinations
        for buffered_msg in cls._buffer:
            if buffered_msg.is_stderr:
                sys.stderr.write(buffered_msg.formatted_message)
            else:
                sys.stdout.write(buffered_msg.formatted_message)

        # Flush both streams
        sys.stdout.flush()
        sys.stderr.flush()

        # Clear the buffer
        cls._buffer.clear()

        # Re-add the normal console handlers and store their IDs
        if output_opts is not None:
            if output_opts.console_level != LogLevel.NONE:
                handler_id = logger.add(
                    sys.stdout,
                    level=output_opts.console_level,
                    format=_format_user_message,
                    colorize=False,
                    diagnose=False,
                )
                _console_handler_ids["stdout"] = handler_id

            if output_opts.log_level != LogLevel.NONE:
                level_map = {
                    LogLevel.TRACE: "TRACE",
                    LogLevel.DEBUG: "DEBUG",
                    LogLevel.BUILD: "BUILD",
                    LogLevel.INFO: "INFO",
                    LogLevel.WARN: "WARNING",
                    LogLevel.ERROR: "ERROR",
                    LogLevel.NONE: "CRITICAL",
                }
                handler_id = logger.add(
                    sys.stderr,
                    level=level_map[output_opts.log_level],
                    format="<level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan> - <level>{message}</level>",
                    colorize=True,
                    diagnose=False,
                )
                _console_handler_ids["stderr"] = handler_id

        cls._output_opts = None

    @classmethod
    def get_buffered_messages(cls) -> list[BufferedMessage]:
        """Get a copy of the current buffer contents."""
        return list(cls._buffer)
