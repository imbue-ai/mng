import json
import sys
from typing import Any
from typing import assert_never

from loguru import logger

from imbue.mngr.primitives import ErrorBehavior
from imbue.mngr.primitives import OutputFormat


def _write_json_line(data: dict[str, Any]) -> None:
    """Write a JSON object as a line to stdout.

    This is used for JSON and JSONL output formats where we need raw JSON
    without any logger formatting.
    """
    sys.stdout.write(json.dumps(data) + "\n")
    sys.stdout.flush()


class AbortError(BaseException):
    """Exception raised when error behavior is ABORT.

    Inherits from BaseException (not Exception) so it cannot be caught
    by generic Exception handlers, ensuring it propagates to the top level.
    """

    def __init__(
        self,
        message: str,
        # The original exception that caused the abort, if any
        original_exception: Exception | None = None,
    ):
        super().__init__(message)
        self.message = message
        self.original_exception = original_exception


def emit_info(message: str, output_format: OutputFormat) -> None:
    """Emit an informational message in the appropriate format."""
    match output_format:
        case OutputFormat.HUMAN:
            logger.info(message)
        case OutputFormat.JSONL:
            event = {"event": "info", "message": message}
            _write_json_line(event)
        case OutputFormat.JSON:
            # JSON mode: silent until final output
            pass
        case _ as unreachable:
            assert_never(unreachable)


def emit_event(
    # The type of event (e.g., "destroyed", "created")
    event_type: str,
    # Event data dictionary. For HUMAN format, should include "message" key.
    data: dict[str, Any],
    output_format: OutputFormat,
) -> None:
    """Emit an event in the appropriate format."""
    match output_format:
        case OutputFormat.HUMAN:
            if "message" in data:
                logger.info(data["message"])
        case OutputFormat.JSONL:
            event = {"event": event_type, **data}
            _write_json_line(event)
        case OutputFormat.JSON:
            # JSON mode: silent until final output
            pass
        case _ as unreachable:
            assert_never(unreachable)


def on_error(
    error_msg: str,
    # How to handle the error: ABORT raises AbortError, CONTINUE logs and continues
    error_behavior: ErrorBehavior,
    output_format: OutputFormat,
    # Optional exception that caused the error
    exc: Exception | None = None,
) -> None:
    """Handle an error by emitting it and optionally aborting."""
    # Emit the error in the appropriate format
    match output_format:
        case OutputFormat.HUMAN:
            logger.error(error_msg)
        case OutputFormat.JSONL:
            event = {"event": "error", "message": error_msg}
            _write_json_line(event)
        case OutputFormat.JSON:
            # JSON mode: errors collected and shown in final output
            pass
        case _ as unreachable:
            assert_never(unreachable)

    # Abort if requested
    if error_behavior == ErrorBehavior.ABORT:
        raise AbortError(error_msg, original_exception=exc)


def emit_final_json(data: dict[str, Any]) -> None:
    """Emit final JSON output (for JSON format only)."""
    _write_json_line(data)
