"""Tests for CLI output helpers."""

import json

import pytest

from imbue.mngr.cli.output_helpers import AbortError
from imbue.mngr.cli.output_helpers import emit_event
from imbue.mngr.cli.output_helpers import emit_final_json
from imbue.mngr.cli.output_helpers import emit_info
from imbue.mngr.cli.output_helpers import format_mngr_error_for_cli
from imbue.mngr.cli.output_helpers import on_error
from imbue.mngr.primitives import ErrorBehavior
from imbue.mngr.primitives import OutputFormat

# =============================================================================
# Tests for AbortError
# =============================================================================


def test_abort_error_stores_message() -> None:
    """AbortError should store the message."""
    error = AbortError("test message")
    assert error.message == "test message"
    assert str(error) == "test message"


def test_abort_error_stores_original_exception() -> None:
    """AbortError should store the original exception."""
    original = ValueError("original error")
    error = AbortError("test message", original_exception=original)
    assert error.original_exception is original


def test_abort_error_is_base_exception() -> None:
    """AbortError should be a BaseException."""
    error = AbortError("test")
    assert isinstance(error, BaseException)
    assert not isinstance(error, Exception)


# =============================================================================
# Tests for emit_info
# =============================================================================


def test_emit_info_human_format(capsys) -> None:
    """emit_info with HUMAN format should output to logger."""
    # HUMAN format outputs via logger, which uses stdout
    emit_info("test message", OutputFormat.HUMAN)
    # We don't capture logger output in this test - just verify no exception


def test_emit_info_jsonl_format(capsys) -> None:
    """emit_info with JSONL format should output JSON line."""
    emit_info("test message", OutputFormat.JSONL)
    captured = capsys.readouterr()
    output = json.loads(captured.out.strip())
    assert output["event"] == "info"
    assert output["message"] == "test message"


def test_emit_info_json_format(capsys) -> None:
    """emit_info with JSON format should be silent."""
    emit_info("test message", OutputFormat.JSON)
    captured = capsys.readouterr()
    assert captured.out == ""


# =============================================================================
# Tests for emit_event
# =============================================================================


def test_emit_event_human_format_with_message(capsys) -> None:
    """emit_event with HUMAN format should output message via logger."""
    emit_event("destroyed", {"message": "Agent destroyed"}, OutputFormat.HUMAN)
    # We don't capture logger output in this test - just verify no exception


def test_emit_event_human_format_without_message(capsys) -> None:
    """emit_event with HUMAN format without message should not output."""
    emit_event("destroyed", {"other": "data"}, OutputFormat.HUMAN)
    # No exception should be raised


def test_emit_event_jsonl_format(capsys) -> None:
    """emit_event with JSONL format should output JSON line with event type."""
    emit_event("destroyed", {"agent_id": "agent-123"}, OutputFormat.JSONL)
    captured = capsys.readouterr()
    output = json.loads(captured.out.strip())
    assert output["event"] == "destroyed"
    assert output["agent_id"] == "agent-123"


def test_emit_event_json_format(capsys) -> None:
    """emit_event with JSON format should be silent."""
    emit_event("destroyed", {"agent_id": "agent-123"}, OutputFormat.JSON)
    captured = capsys.readouterr()
    assert captured.out == ""


# =============================================================================
# Tests for on_error
# =============================================================================


def test_on_error_human_format_continue() -> None:
    """on_error with HUMAN format and CONTINUE should not raise."""
    # Should not raise
    on_error("test error", ErrorBehavior.CONTINUE, OutputFormat.HUMAN)


def test_on_error_human_format_abort() -> None:
    """on_error with HUMAN format and ABORT should raise AbortError."""
    with pytest.raises(AbortError) as exc_info:
        on_error("test error", ErrorBehavior.ABORT, OutputFormat.HUMAN)
    assert exc_info.value.message == "test error"


def test_on_error_jsonl_format(capsys) -> None:
    """on_error with JSONL format should output error event."""
    on_error("test error", ErrorBehavior.CONTINUE, OutputFormat.JSONL)
    captured = capsys.readouterr()
    output = json.loads(captured.out.strip())
    assert output["event"] == "error"
    assert output["message"] == "test error"


def test_on_error_json_format_continue(capsys) -> None:
    """on_error with JSON format and CONTINUE should be silent."""
    on_error("test error", ErrorBehavior.CONTINUE, OutputFormat.JSON)
    captured = capsys.readouterr()
    assert captured.out == ""


def test_on_error_stores_original_exception() -> None:
    """on_error with ABORT should include original exception in AbortError."""
    original = ValueError("original")
    with pytest.raises(AbortError) as exc_info:
        on_error("test error", ErrorBehavior.ABORT, OutputFormat.HUMAN, exc=original)
    assert exc_info.value.original_exception is original


# =============================================================================
# Tests for emit_final_json
# =============================================================================


def test_emit_final_json_outputs_json(capsys) -> None:
    """emit_final_json should output JSON data."""
    emit_final_json({"status": "success", "count": 5})
    captured = capsys.readouterr()
    output = json.loads(captured.out.strip())
    assert output["status"] == "success"
    assert output["count"] == 5


# =============================================================================
# Tests for format_mngr_error_for_cli
# =============================================================================


def test_format_mngr_error_for_cli_without_help_text() -> None:
    """format_mngr_error_for_cli should format error message without help text."""
    error = ValueError("Something went wrong")
    result = format_mngr_error_for_cli(error, None)
    # No "Error:" prefix - Click adds that when displaying MngrError exceptions
    assert result == "Something went wrong"


def test_format_mngr_error_for_cli_with_help_text() -> None:
    """format_mngr_error_for_cli should include help text when provided."""
    error = ValueError("Agent not found")
    help_text = "Use 'mngr list' to see available agents."
    result = format_mngr_error_for_cli(error, help_text)
    # No "Error:" prefix - Click adds that when displaying MngrError exceptions
    assert "Agent not found" in result
    assert "Use 'mngr list' to see available agents." in result


def test_format_mngr_error_for_cli_with_multiline_help_text() -> None:
    """format_mngr_error_for_cli should handle multiline help text."""
    error = ValueError("Test error")
    help_text = "Line 1\nLine 2"
    result = format_mngr_error_for_cli(error, help_text)
    # No "Error:" prefix - Click adds that when displaying MngrError exceptions
    assert "Test error" in result
    assert "Line 1\nLine 2" in result
