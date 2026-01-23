import functools
import inspect
import os
import sys
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any
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
WARNING_COLOR = "\x1b[1;38;5;178m"
ERROR_COLOR = "\x1b[1;38;5;196m"
RESET_COLOR = "\x1b[0m"


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
    return "{message}\n"


def setup_logging(output_opts: OutputOptions, mngr_ctx: MngrContext) -> None:
    """Configure logging based on output options and mngr context.

    Sets up:
    - stdout logging for user-facing messages (clean format)
    - stderr logging for structured diagnostic messages (detailed format)
    - File logging to ~/.mngr/logs/<timestamp>-<pid>.json
    - Log rotation based on config
    """
    # Remove default handler
    logger.remove()

    # Map our LogLevel enum to loguru levels
    level_map = {
        LogLevel.TRACE: "TRACE",
        LogLevel.DEBUG: "DEBUG",
        LogLevel.INFO: "INFO",
        LogLevel.WARN: "WARNING",
        LogLevel.ERROR: "ERROR",
        LogLevel.NONE: "CRITICAL",
    }

    # Set up stdout logging for user messages (clean format, with colored WARNING prefix).
    # We set colorize=False because we handle colors manually in _format_user_message.
    if output_opts.console_level != LogLevel.NONE:
        logger.add(
            sys.stdout,
            level=output_opts.console_level,
            format=_format_user_message,
            colorize=False,
            diagnose=False,
        )

    # Set up stderr logging for diagnostics (structured format)
    # Shows all messages at console_level with detailed formatting
    if output_opts.log_level != LogLevel.NONE:
        console_level = level_map[output_opts.log_level]
        logger.add(
            sys.stderr,
            level=console_level,
            format="<level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan> - <level>{message}</level>",
            colorize=True,
            diagnose=False,
        )

    # Set up file logging
    log_dir = _resolve_log_dir(mngr_ctx.config)
    log_dir.mkdir(parents=True, exist_ok=True)

    # Create log file path
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

    # Rotate old logs if needed (do explicit rotation for better control)
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

    Logs the function name, all arguments (with values truncated if too long),
    and the return value. Useful for API entry points to trace execution.
    """
    # Get the function name once at decoration time
    func_name = getattr(func, "__name__", repr(func))

    @functools.wraps(func)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
        # Get the function signature to map positional args to names
        sig = inspect.signature(func)
        bound_args = sig.bind(*args, **kwargs)
        bound_args.apply_defaults()

        # Format arguments for logging
        arg_strs = [f"{name}={_format_arg_value(value)}" for name, value in bound_args.arguments.items()]
        args_str = ", ".join(arg_strs)

        logger.debug("Calling {}({})", func_name, args_str)

        result = func(*args, **kwargs)

        logger.debug("{} returned {}", func_name, _format_arg_value(result))

        return result

    return wrapper
