"""Tests for CLI output helpers."""

import json

import pytest

from imbue.mngr.cli.output_helpers import AbortError
from imbue.mngr.cli.output_helpers import emit_event
from imbue.mngr.cli.output_helpers import emit_final_json
from imbue.mngr.cli.output_helpers import emit_info
from imbue.mngr.cli.output_helpers import format_size
from imbue.mngr.cli.output_helpers import on_error
from imbue.mngr.errors import MngrError
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
# Tests for format_size
# =============================================================================


def test_format_size_bytes() -> None:
    """format_size should format small sizes in bytes."""
    assert format_size(0) == "0 B"
    assert format_size(1) == "1 B"
    assert format_size(512) == "512 B"
    assert format_size(1023) == "1023 B"


def test_format_size_kilobytes() -> None:
    """format_size should format sizes in kilobytes."""
    assert format_size(1024) == "1.0 KB"
    assert format_size(1536) == "1.5 KB"
    assert format_size(10240) == "10.0 KB"
    assert format_size(1024 * 1024 - 1) == "1024.0 KB"


def test_format_size_megabytes() -> None:
    """format_size should format sizes in megabytes."""
    assert format_size(1024**2) == "1.0 MB"
    assert format_size(int(1.5 * 1024**2)) == "1.5 MB"
    assert format_size(100 * 1024**2) == "100.0 MB"


def test_format_size_gigabytes() -> None:
    """format_size should format sizes in gigabytes with two decimal places."""
    assert format_size(1024**3) == "1.00 GB"
    assert format_size(int(1.5 * 1024**3)) == "1.50 GB"
    assert format_size(10 * 1024**3) == "10.00 GB"


def test_format_size_terabytes() -> None:
    """format_size should format sizes in terabytes with two decimal places."""
    assert format_size(1024**4) == "1.00 TB"
    assert format_size(int(2.5 * 1024**4)) == "2.50 TB"


@pytest.mark.parametrize(
    ("size_bytes", "expected"),
    [
        (0, "0 B"),
        (100, "100 B"),
        (1024, "1.0 KB"),
        (1024 * 500, "500.0 KB"),
        (1024 * 1024, "1.0 MB"),
        (1024 * 1024 * 1024, "1.00 GB"),
        (1024 * 1024 * 1024 * 1024, "1.00 TB"),
    ],
)
def test_format_size_parametrized(size_bytes: int, expected: str) -> None:
    """format_size should format various byte sizes correctly."""
    assert format_size(size_bytes) == expected


# =============================================================================
# Tests for MngrError.format_message
# =============================================================================


def test_mngr_error_format_message_without_help_text() -> None:
    """MngrError.format_message should format error message without help text."""
    error = MngrError("Something went wrong")
    result = error.format_message()
    # No "Error:" prefix - Click adds that when displaying MngrError exceptions
    assert result == "Something went wrong"


def test_mngr_error_format_message_with_help_text() -> None:
    """MngrError.format_message should include help text when provided."""
    error = MngrError("Agent not found")
    error.user_help_text = "Use 'mngr list' to see available agents."
    result = error.format_message()
    # No "Error:" prefix - Click adds that when displaying MngrError exceptions
    assert "Agent not found" in result
    assert "Use 'mngr list' to see available agents." in result


def test_mngr_error_format_message_with_multiline_help_text() -> None:
    """MngrError.format_message should handle multiline help text."""
    error = MngrError("Test error")
    error.user_help_text = "Line 1\nLine 2"
    result = error.format_message()
    # No "Error:" prefix - Click adds that when displaying MngrError exceptions
    assert "Test error" in result
    assert "Line 1\nLine 2" in result
