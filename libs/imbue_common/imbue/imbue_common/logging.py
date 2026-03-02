import functools
import inspect
import os
import sys
import time
from collections.abc import Callable
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime
from datetime import timezone
from typing import Any
from typing import Final
from typing import ParamSpec
from typing import TypeVar
from uuid import uuid4

from loguru import logger

from imbue.imbue_common.pure import pure


def setup_logging(level: str = "INFO") -> None:
    """Configure loguru logging with the specified level."""
    logger.remove()
    logger.add(
        sys.stderr,
        level=level.upper(),
        format="<level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
    )


P = ParamSpec("P")
R = TypeVar("R")


_MAX_LOG_VALUE_REPR_LENGTH: Final[int] = 200


@pure
def _format_arg_value(value: Any) -> str:
    """Format an argument value for logging, truncating if too long."""
    str_value = repr(value)
    if len(str_value) > _MAX_LOG_VALUE_REPR_LENGTH:
        return str_value[: _MAX_LOG_VALUE_REPR_LENGTH - 3] + "..."
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

        start_time = time.monotonic()

        result = func(*args, **kwargs)

        elapsed = time.monotonic() - start_time
        done_message = f"Calling {func_name} [done in {elapsed:.5f} sec]"
        logger.trace(done_message, result=_format_arg_value(result))

        return result

    return wrapper


@contextmanager
def log_span(message: str, *args: Any, **context: Any) -> Iterator[None]:
    """Context manager that logs a debug message on entry and a trace message with timing on exit.

    On entry, emits logger.debug(message, *args).
    On exit, emits logger.trace(message + " [done in X.XXXXX sec]", *args, elapsed).

    Keyword arguments are passed to logger.contextualize so that all log messages
    within the span include the extra context fields.
    """
    with logger.contextualize(**context):
        logger.debug(message, *args)
        start_time = time.monotonic()
        try:
            yield
        except BaseException:
            elapsed = time.monotonic() - start_time
            failed_message = message + " [failed after {:.5f} sec]"
            logger.trace(failed_message, *args, elapsed)
            raise
        else:
            elapsed = time.monotonic() - start_time
            done_message = message + " [done in {:.5f} sec]"
            logger.trace(done_message, *args, elapsed)


@contextmanager
def trace_span(message: str, *args: Any, _is_trace_span_enabled: bool = True, **context: Any) -> Iterator[None]:
    """Context manager that logs a trace message on entry and a trace message with timing on exit.

    On entry, emits logger.trace(message, *args).
    On exit, emits logger.trace(message + " [done in X.XXXXX sec]", *args, elapsed).

    Keyword arguments are passed to logger.contextualize so that all log messages
    within the span include the extra context fields.
    """
    if not _is_trace_span_enabled:
        yield
    else:
        with logger.contextualize(**context):
            logger.trace(message, *args)
            start_time = time.monotonic()
            try:
                yield
            except BaseException:
                elapsed = time.monotonic() - start_time
                failed_message = message + " [failed after {:.5f} sec]"
                logger.trace(failed_message, *args, elapsed)
                raise
            else:
                elapsed = time.monotonic() - start_time
                done_message = message + " [done in {:.5f} sec]"
                logger.trace(done_message, *args, elapsed)


# -- Event envelope patcher for loguru's built-in JSON serialization --


@pure
def format_nanosecond_iso_timestamp(dt: datetime) -> str:
    """Format a datetime as ISO 8601 with nanosecond precision in UTC.

    Converts to UTC first so the trailing 'Z' is always correct, even when
    loguru provides a local-timezone datetime.
    """
    utc_dt = dt.astimezone(timezone.utc)
    return utc_dt.strftime("%Y-%m-%dT%H:%M:%S.") + f"{utc_dt.microsecond * 1000:09d}Z"


def generate_log_event_id() -> str:
    """Generate a unique event ID using a random UUID4 hex with 'evt-' prefix."""
    return f"evt-{uuid4().hex}"


def make_envelope_patcher(
    event_type: str,
    event_source: str,
    command: str | None,
) -> Callable[..., None]:
    """Create a loguru patcher that injects event envelope fields into record['extra'].

    The patcher adds timestamp, type, event_id, source, pid (and optionally
    command) to every log record's extra dict. When loguru serializes the
    record with serialize=True, these fields appear inside record.extra
    alongside all standard loguru fields (level, message, function, line, etc).
    """
    bound_type = event_type
    bound_source = event_source
    bound_command = command

    def patcher(record: Any) -> None:
        dt = record["time"]
        record["extra"]["timestamp"] = format_nanosecond_iso_timestamp(dt)
        record["extra"]["type"] = bound_type
        record["extra"]["event_id"] = generate_log_event_id()
        record["extra"]["source"] = bound_source
        record["extra"]["pid"] = os.getpid()
        if bound_command is not None:
            record["extra"]["command"] = bound_command

    return patcher
