"""Tests for logging module."""

import io
import json
from datetime import datetime
from datetime import timezone
from typing import Any

from loguru import logger

from imbue.imbue_common.logging import format_nanosecond_iso_timestamp
from imbue.imbue_common.logging import generate_log_event_id
from imbue.imbue_common.logging import log_span
from imbue.imbue_common.logging import make_envelope_patcher
from imbue.imbue_common.logging import setup_logging
from imbue.mng.errors import BaseMngError


def test_setup_logging_does_not_raise() -> None:
    """setup_logging should configure logging without raising."""
    setup_logging()


def test_setup_logging_with_custom_level() -> None:
    """setup_logging should accept custom log levels."""
    setup_logging(level="DEBUG")
    setup_logging(level="info")


# =============================================================================
# Tests for log_span
# =============================================================================


def test_log_span_emits_debug_on_entry_and_trace_on_exit() -> None:
    """log_span should emit a debug message on entry and a trace message on exit."""
    captured_messages: list[str] = []
    captured_levels: list[str] = []

    def sink(message: Any) -> None:
        record = message.record
        captured_messages.append(record["message"])
        captured_levels.append(record["level"].name)

    handler_id = logger.add(sink, level="TRACE", format="{message}")
    try:
        with log_span("processing items"):
            pass

        assert len(captured_messages) == 2
        assert captured_messages[0] == "processing items"
        assert captured_levels[0] == "DEBUG"
        assert "processing items [done in " in captured_messages[1]
        assert " sec]" in captured_messages[1]
        assert captured_levels[1] == "TRACE"
    finally:
        logger.remove(handler_id)


def test_log_span_passes_format_args_to_messages() -> None:
    """log_span should pass positional format args to both entry and exit messages."""
    captured_messages: list[str] = []

    def sink(message: Any) -> None:
        captured_messages.append(message.record["message"])

    handler_id = logger.add(sink, level="TRACE", format="{message}")
    try:
        with log_span("creating agent {} on host {}", "agent-1", "host-1"):
            pass

        assert captured_messages[0] == "creating agent agent-1 on host host-1"
        assert "creating agent agent-1 on host host-1 [done in " in captured_messages[1]
    finally:
        logger.remove(handler_id)


def test_log_span_passes_context_kwargs_via_contextualize() -> None:
    """log_span should set context kwargs via logger.contextualize."""
    captured_extras: list[dict] = []

    def sink(message: Any) -> None:
        captured_extras.append(dict(message.record["extra"]))

    handler_id = logger.add(sink, level="TRACE", format="{message}")
    try:
        with log_span("writing env vars", count=5, path="/tmp"):
            pass

        # Both entry and exit messages should have the context
        assert captured_extras[0]["count"] == 5
        assert captured_extras[0]["path"] == "/tmp"
        assert captured_extras[1]["count"] == 5
        assert captured_extras[1]["path"] == "/tmp"
    finally:
        logger.remove(handler_id)


def test_log_span_measures_elapsed_time() -> None:
    """log_span should include a non-negative elapsed time in the exit message."""
    captured_messages: list[str] = []

    def sink(message: Any) -> None:
        captured_messages.append(message.record["message"])

    handler_id = logger.add(sink, level="TRACE", format="{message}")
    try:
        with log_span("doing work"):
            # Do some trivial computation to take a non-zero amount of time
            _result = sum(range(1000))

        # Extract the timing from the trace message
        trace_message = captured_messages[1]
        assert "[done in " in trace_message
        timing_str = trace_message.split("[done in ")[1].split(" sec]")[0]
        elapsed = float(timing_str)
        assert elapsed >= 0.0
        assert elapsed < 1.0
    finally:
        logger.remove(handler_id)


def test_log_span_logs_timing_even_on_exception() -> None:
    """log_span should emit the trace message even when an exception occurs."""
    captured_messages: list[str] = []
    captured_levels: list[str] = []

    def sink(message: Any) -> None:
        captured_messages.append(message.record["message"])
        captured_levels.append(message.record["level"].name)

    handler_id = logger.add(sink, level="TRACE", format="{message}")
    try:
        try:
            with log_span("risky operation"):
                raise BaseMngError("test error")
        except BaseMngError:
            pass

        assert len(captured_messages) == 2
        assert captured_messages[0] == "risky operation"
        assert captured_levels[0] == "DEBUG"
        assert "risky operation [failed after " in captured_messages[1]
        assert captured_levels[1] == "TRACE"
    finally:
        logger.remove(handler_id)


def test_log_span_context_does_not_leak_outside_span() -> None:
    """Context kwargs should not be present in log records after the span exits."""
    captured_extras: list[dict] = []

    def sink(message: Any) -> None:
        captured_extras.append(dict(message.record["extra"]))

    handler_id = logger.add(sink, level="TRACE", format="{message}")
    try:
        with log_span("scoped operation", scope_var="inside"):
            pass

        # Log something after the span
        logger.debug("after span")

        # The message after the span should not have the context
        assert "scope_var" not in captured_extras[2]
    finally:
        logger.remove(handler_id)


# =============================================================================
# Tests for JSONL event formatting
# =============================================================================


def test_format_nanosecond_iso_timestamp_produces_correct_format() -> None:
    dt = datetime(2026, 3, 1, 12, 30, 45, 123456, tzinfo=timezone.utc)
    result = format_nanosecond_iso_timestamp(dt)
    assert result == "2026-03-01T12:30:45.123456000Z"


def test_format_nanosecond_iso_timestamp_zero_microseconds() -> None:
    dt = datetime(2026, 1, 1, 0, 0, 0, 0, tzinfo=timezone.utc)
    result = format_nanosecond_iso_timestamp(dt)
    assert result == "2026-01-01T00:00:00.000000000Z"


def test_generate_log_event_id_returns_unique_ids() -> None:
    id_a = generate_log_event_id()
    id_b = generate_log_event_id()
    assert id_a != id_b
    assert id_a.startswith("evt-")
    assert id_b.startswith("evt-")
    # Should be evt- prefix + 32 hex chars (uuid4)
    assert len(id_a) == 4 + 32


def test_make_envelope_patcher_injects_fields_into_record_extra() -> None:
    """The patcher should inject envelope fields into the loguru record's extra dict."""
    captured_extras: list[dict[str, Any]] = []

    def sink(message: Any) -> None:
        captured_extras.append(dict(message.record["extra"]))

    patcher = make_envelope_patcher(event_type="mng", event_source="mng", command="create")
    logger.configure(patcher=patcher)
    handler_id = logger.add(sink, level="TRACE", format="{message}")
    try:
        logger.info("Created agent {}", "test-agent")
    finally:
        logger.remove(handler_id)
        logger.configure(patcher=lambda r: None)

    assert len(captured_extras) == 1
    extra = captured_extras[0]
    assert extra["type"] == "mng"
    assert extra["source"] == "mng"
    assert extra["command"] == "create"
    assert extra["event_id"].startswith("evt-")
    assert "timestamp" in extra
    assert "pid" in extra


def test_make_envelope_patcher_omits_command_when_none() -> None:
    """When command is None, the patcher should not add a command key to extra."""
    captured_extras: list[dict[str, Any]] = []

    def sink(message: Any) -> None:
        captured_extras.append(dict(message.record["extra"]))

    patcher = make_envelope_patcher(event_type="event_watcher", event_source="event_watcher", command=None)
    logger.configure(patcher=patcher)
    handler_id = logger.add(sink, level="TRACE", format="{message}")
    try:
        logger.debug("Watching events")
    finally:
        logger.remove(handler_id)
        logger.configure(patcher=lambda r: None)

    extra = captured_extras[0]
    assert extra["type"] == "event_watcher"
    assert "command" not in extra


def test_make_envelope_patcher_works_with_serialize_true() -> None:
    """The patcher should produce valid serialized JSON via loguru's serialize=True."""
    buf = io.StringIO()
    patcher = make_envelope_patcher(event_type="mng", event_source="mng", command="list")
    logger.configure(patcher=patcher)
    handler_id = logger.add(buf, level="TRACE", format="{message}", serialize=True)
    try:
        logger.info('Path with "quotes" and {{braces}}')
    finally:
        logger.remove(handler_id)
        logger.configure(patcher=lambda r: None)

    parsed = json.loads(buf.getvalue())
    record = parsed["record"]
    extra = record["extra"]

    assert extra["type"] == "mng"
    assert extra["source"] == "mng"
    assert extra["command"] == "list"
    assert extra["event_id"].startswith("evt-")
    # Standard loguru fields should still be present
    assert "function" in record
    assert "level" in record
    assert "message" in record
