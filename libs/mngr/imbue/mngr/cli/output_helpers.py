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


def output_sync_files_result(
    # result is SyncFilesResult; typed as Any to avoid circular imports
    # (sync -> errors -> output_helpers)
    result: Any,
    output_format: OutputFormat,
) -> None:
    """Output a file sync result (SyncFilesResult) in the appropriate format.

    Works for both push and pull operations, using result.mode to determine
    the event name and human-readable message.
    """
    result_data = {
        "files_transferred": result.files_transferred,
        "bytes_transferred": result.bytes_transferred,
        "source_path": str(result.source_path),
        "destination_path": str(result.destination_path),
        "is_dry_run": result.is_dry_run,
    }
    # SyncMode is a UpperCaseStrEnum, so we can compare directly with string values
    # to avoid circular imports (sync -> errors -> output_helpers)
    mode_label = "Push" if result.mode == "PUSH" else "Pull"
    event_name = f"{mode_label.lower()}_complete"

    match output_format:
        case OutputFormat.JSON:
            emit_final_json(result_data)
        case OutputFormat.JSONL:
            emit_event(event_name, result_data, OutputFormat.JSONL)
        case OutputFormat.HUMAN:
            if result.is_dry_run:
                logger.info("Dry run complete: {} files would be transferred", result.files_transferred)
            else:
                logger.info(
                    "{} complete: {} files, {} bytes transferred",
                    mode_label,
                    result.files_transferred,
                    result.bytes_transferred,
                )
        case _ as unreachable:
            assert_never(unreachable)


def output_sync_git_result(
    # result is SyncGitResult; typed as Any to avoid circular imports
    # (sync -> errors -> output_helpers)
    result: Any,
    output_format: OutputFormat,
) -> None:
    """Output a git sync result (SyncGitResult) in the appropriate format.

    Works for both push and pull operations, using result.mode to determine
    the event name and human-readable message.
    """
    result_data = {
        "source_branch": result.source_branch,
        "target_branch": result.target_branch,
        "source_path": str(result.source_path),
        "destination_path": str(result.destination_path),
        "is_dry_run": result.is_dry_run,
        "commits_transferred": result.commits_transferred,
    }
    # SyncMode is a UpperCaseStrEnum, so we can compare directly with string values
    # to avoid circular imports (sync -> errors -> output_helpers)
    is_push = result.mode == "PUSH"
    event_name = "push_git_complete" if is_push else "pull_git_complete"
    verb = "push" if is_push else "merge"
    verb_past = "pushed" if is_push else "merged"
    preposition = "to" if is_push else "into"

    match output_format:
        case OutputFormat.JSON:
            emit_final_json(result_data)
        case OutputFormat.JSONL:
            emit_event(event_name, result_data, OutputFormat.JSONL)
        case OutputFormat.HUMAN:
            if result.is_dry_run:
                logger.info(
                    "Dry run complete: would {} {} commits from {} {} {}",
                    verb,
                    result.commits_transferred,
                    result.source_branch,
                    preposition,
                    result.target_branch,
                )
            else:
                logger.info(
                    "Git {} complete: {} {} commits from {} {} {}",
                    verb,
                    verb_past,
                    result.commits_transferred,
                    result.source_branch,
                    preposition,
                    result.target_branch,
                )
        case _ as unreachable:
            assert_never(unreachable)


def format_mngr_error_for_cli(error: Exception, user_help_text: str | None) -> str:
    """Format an error for display in the CLI.

    Produces a user-friendly error message without a stack trace.
    If the error has user_help_text, it is appended on a new line after the error message.
    """
    if user_help_text:
        return str(error) + "  [" + user_help_text + "]"
    else:
        return str(error)
