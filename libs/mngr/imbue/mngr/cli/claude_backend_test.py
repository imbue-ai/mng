import json

from imbue.mngr.cli.claude_backend import _build_claude_command
from imbue.mngr.cli.claude_backend import _extract_text_delta
from imbue.mngr.cli.claude_backend import accumulate_chunks


def test_extract_text_delta_valid_event() -> None:
    """A valid content_block_delta event should return the text."""
    event = json.dumps(
        {
            "type": "stream_event",
            "event": {
                "type": "content_block_delta",
                "index": 0,
                "delta": {"type": "text_delta", "text": "hello"},
            },
        }
    )
    assert _extract_text_delta(event) == "hello"


def test_extract_text_delta_non_delta_event() -> None:
    """Non-delta events should return None."""
    event = json.dumps(
        {
            "type": "stream_event",
            "event": {"type": "content_block_start", "index": 0},
        }
    )
    assert _extract_text_delta(event) is None


def test_extract_text_delta_malformed_json() -> None:
    """Malformed JSON should return None, not raise."""
    assert _extract_text_delta("not valid json {{{") is None


def test_extract_text_delta_non_stream_event() -> None:
    """Events that are not stream_event type should return None."""
    event = json.dumps({"type": "result", "subtype": "success"})
    assert _extract_text_delta(event) is None


def test_extract_text_delta_missing_delta() -> None:
    """content_block_delta without a delta field should return None."""
    event = json.dumps(
        {
            "type": "stream_event",
            "event": {"type": "content_block_delta", "index": 0},
        }
    )
    assert _extract_text_delta(event) is None


def test_accumulate_chunks_combines_all_chunks() -> None:
    """accumulate_chunks should join all yielded strings into one."""
    chunks = iter(["hello", " ", "world"])
    assert accumulate_chunks(chunks) == "hello world"


def test_accumulate_chunks_returns_empty_for_no_chunks() -> None:
    """accumulate_chunks with empty iterator should return empty string."""
    chunks = iter([])
    assert accumulate_chunks(chunks) == ""


def test_extract_text_delta_event_field_not_dict() -> None:
    """When the event field is not a dict (e.g. a string), should return None."""
    event = json.dumps(
        {
            "type": "stream_event",
            "event": "not_a_dict",
        }
    )
    assert _extract_text_delta(event) is None


def test_extract_text_delta_wrong_delta_type() -> None:
    """When delta.type is not text_delta (e.g. input_json_delta), should return None."""
    event = json.dumps(
        {
            "type": "stream_event",
            "event": {
                "type": "content_block_delta",
                "index": 0,
                "delta": {"type": "input_json_delta", "partial_json": '{"key":'},
            },
        }
    )
    assert _extract_text_delta(event) is None


def test_extract_text_delta_text_field_not_string() -> None:
    """When delta.text is not a string (e.g. an integer), should return None."""
    event = json.dumps(
        {
            "type": "stream_event",
            "event": {
                "type": "content_block_delta",
                "index": 0,
                "delta": {"type": "text_delta", "text": 42},
            },
        }
    )
    assert _extract_text_delta(event) is None


def test_build_claude_command_no_tools_disables_all() -> None:
    """When no tools are allowed, --tools "" should be passed."""
    cmd = _build_claude_command(prompt="hello", system_prompt="sys", allowed_tools=())
    assert "--tools" in cmd
    assert "" in cmd
    assert "--allowedTools" not in cmd


def test_build_claude_command_with_allowed_tools() -> None:
    """When tools are specified, --allowedTools should be passed instead of --tools."""
    cmd = _build_claude_command(prompt="hello", system_prompt="sys", allowed_tools=("Read", "Glob", "Grep"))
    assert "--allowedTools" in cmd
    assert "Read,Glob,Grep" in cmd
    assert "--tools" not in cmd
