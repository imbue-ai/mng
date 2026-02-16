import json
import sys
from collections.abc import Mapping
from typing import Any
from typing import assert_never

from loguru import logger

from imbue.imbue_common.pure import pure
from imbue.mngr.api.sync import SyncFilesResult
from imbue.mngr.api.sync import SyncGitResult
from imbue.mngr.primitives import ErrorBehavior
from imbue.mngr.primitives import OutputFormat
from imbue.mngr.primitives import SyncMode


def _write_json_line(data: Mapping[str, Any]) -> None:
    """Write a JSON object as a line to stdout.

    This is used for JSON and JSONL output formats where we need raw JSON
    without any logger formatting.
    """
    sys.stdout.write(json.dumps(data) + "\n")
    sys.stdout.flush()


@pure
def format_size(size_bytes: int) -> str:
    """Format bytes into a human-readable size string."""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    if size_bytes < 1024**2:
        return f"{size_bytes / 1024:.1f} KB"
    if size_bytes < 1024**3:
        return f"{size_bytes / 1024**2:.1f} MB"
    if size_bytes < 1024**4:
        return f"{size_bytes / 1024**3:.2f} GB"
    return f"{size_bytes / 1024**4:.2f} TB"


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
    data: Mapping[str, Any],
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


def emit_final_json(data: Mapping[str, Any]) -> None:
    """Emit final JSON output (for JSON format only)."""
    _write_json_line(data)


def output_sync_files_result(
    result: SyncFilesResult,
    output_format: OutputFormat,
) -> None:
    """Output a file sync result in the appropriate format.

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
    mode_label = "Push" if result.mode == SyncMode.PUSH else "Pull"
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
    result: SyncGitResult,
    output_format: OutputFormat,
) -> None:
    """Output a git sync result in the appropriate format.

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
    is_push = result.mode == SyncMode.PUSH
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
