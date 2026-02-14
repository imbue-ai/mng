"""Tests for CLI list command helpers."""

import threading
from datetime import datetime
from datetime import timezone
from io import StringIO

from loguru import logger

from imbue.mngr.cli.conftest import make_test_agent_info
from imbue.mngr.cli.list import _StreamingHumanRenderer
from imbue.mngr.cli.list import _compute_column_widths
from imbue.mngr.cli.list import _format_streaming_agent_row
from imbue.mngr.cli.list import _format_streaming_header_row
from imbue.mngr.cli.list import _format_value_as_string
from imbue.mngr.cli.list import _get_field_value
from imbue.mngr.cli.list import _get_sortable_value
from imbue.mngr.cli.list import _parse_slice_spec
from imbue.mngr.cli.list import _should_use_streaming_mode
from imbue.mngr.cli.list import _sort_agents
from imbue.mngr.interfaces.data_types import SnapshotInfo
from imbue.mngr.primitives import AgentLifecycleState
from imbue.mngr.primitives import AgentName
from imbue.mngr.primitives import OutputFormat
from imbue.mngr.primitives import SnapshotId
from imbue.mngr.primitives import SnapshotName


def _create_test_snapshot(name: str, idx: int) -> SnapshotInfo:
    """Create a test SnapshotInfo for testing."""
    return SnapshotInfo(
        id=SnapshotId(f"snap-test-{idx}"),
        name=SnapshotName(name),
        created_at=datetime.now(timezone.utc),
        recency_idx=idx,
    )


# =============================================================================
# Tests for _parse_slice_spec
# =============================================================================


def test_parse_slice_spec_single_index_zero() -> None:
    """_parse_slice_spec should parse single index 0."""
    result = _parse_slice_spec("0")
    assert result == 0


def test_parse_slice_spec_single_index_positive() -> None:
    """_parse_slice_spec should parse positive index."""
    result = _parse_slice_spec("5")
    assert result == 5


def test_parse_slice_spec_single_index_negative() -> None:
    """_parse_slice_spec should parse negative index."""
    result = _parse_slice_spec("-1")
    assert result == -1


def test_parse_slice_spec_slice_start_only() -> None:
    """_parse_slice_spec should parse slice with start only."""
    result = _parse_slice_spec("2:")
    assert result == slice(2, None)


def test_parse_slice_spec_slice_stop_only() -> None:
    """_parse_slice_spec should parse slice with stop only."""
    result = _parse_slice_spec(":3")
    assert result == slice(None, 3)


def test_parse_slice_spec_slice_start_and_stop() -> None:
    """_parse_slice_spec should parse slice with start and stop."""
    result = _parse_slice_spec("1:4")
    assert result == slice(1, 4)


def test_parse_slice_spec_slice_with_step() -> None:
    """_parse_slice_spec should parse slice with step."""
    result = _parse_slice_spec("0:10:2")
    assert result == slice(0, 10, 2)


def test_parse_slice_spec_full_slice() -> None:
    """_parse_slice_spec should parse full slice (::)."""
    result = _parse_slice_spec("::")
    assert result == slice(None, None, None)


def test_parse_slice_spec_with_whitespace() -> None:
    """_parse_slice_spec should handle whitespace."""
    result = _parse_slice_spec(" 3 ")
    assert result == 3


def test_parse_slice_spec_invalid_too_many_colons() -> None:
    """_parse_slice_spec should return None for invalid spec with too many colons."""
    result = _parse_slice_spec("1:2:3:4")
    assert result is None


def test_parse_slice_spec_invalid_non_integer() -> None:
    """_parse_slice_spec should return None for non-integer spec."""
    result = _parse_slice_spec("abc")
    assert result is None


def test_parse_slice_spec_invalid_non_integer_in_slice() -> None:
    """_parse_slice_spec should return None for non-integer in slice."""
    result = _parse_slice_spec("1:abc")
    assert result is None


# =============================================================================
# Tests for _format_value_as_string
# =============================================================================


def test_format_value_as_string_none_returns_empty() -> None:
    """_format_value_as_string should return empty string for None."""
    assert _format_value_as_string(None) == ""


def test_format_value_as_string_enum_returns_uppercase_value() -> None:
    """_format_value_as_string should return uppercase enum value."""
    result = _format_value_as_string(AgentLifecycleState.RUNNING)
    assert result == AgentLifecycleState.RUNNING.value


def test_format_value_as_string_string_returns_unchanged() -> None:
    """_format_value_as_string should return string unchanged."""
    assert _format_value_as_string("hello") == "hello"


def test_format_value_as_string_int_returns_string() -> None:
    """_format_value_as_string should convert int to string."""
    assert _format_value_as_string(42) == "42"


def test_format_value_as_string_snapshot_uses_name() -> None:
    """_format_value_as_string should use name for SnapshotInfo."""
    snapshot = _create_test_snapshot("my-snapshot", 0)
    result = _format_value_as_string(snapshot)
    assert result == "my-snapshot"


# =============================================================================
# Tests for _get_field_value with bracket notation
# =============================================================================


def test_get_field_value_simple_field() -> None:
    """_get_field_value should extract simple field."""
    agent = make_test_agent_info()
    result = _get_field_value(agent, "name")
    assert result == "test-agent"


def test_get_field_value_nested_field() -> None:
    """_get_field_value should extract nested field."""
    agent = make_test_agent_info()
    result = _get_field_value(agent, "host.name")
    assert result == "test-host"


def test_get_field_value_with_alias() -> None:
    """_get_field_value should resolve field aliases."""
    agent = make_test_agent_info()
    result = _get_field_value(agent, "provider")
    assert result == "local"


def test_get_field_value_list_index_first() -> None:
    """_get_field_value should extract first element with [0]."""
    snapshots = [
        _create_test_snapshot("snap-first", 0),
        _create_test_snapshot("snap-second", 1),
        _create_test_snapshot("snap-third", 2),
    ]
    agent = make_test_agent_info(snapshots=snapshots)
    result = _get_field_value(agent, "host.snapshots[0]")
    assert result == "snap-first"


def test_get_field_value_list_index_last() -> None:
    """_get_field_value should extract last element with [-1]."""
    snapshots = [
        _create_test_snapshot("snap-first", 0),
        _create_test_snapshot("snap-second", 1),
        _create_test_snapshot("snap-third", 2),
    ]
    agent = make_test_agent_info(snapshots=snapshots)
    result = _get_field_value(agent, "host.snapshots[-1]")
    assert result == "snap-third"


def test_get_field_value_list_index_middle() -> None:
    """_get_field_value should extract middle element with index."""
    snapshots = [
        _create_test_snapshot("snap-first", 0),
        _create_test_snapshot("snap-second", 1),
        _create_test_snapshot("snap-third", 2),
    ]
    agent = make_test_agent_info(snapshots=snapshots)
    result = _get_field_value(agent, "host.snapshots[1]")
    assert result == "snap-second"


def test_get_field_value_list_slice_first_n() -> None:
    """_get_field_value should extract first N elements with [:N]."""
    snapshots = [
        _create_test_snapshot("snap-first", 0),
        _create_test_snapshot("snap-second", 1),
        _create_test_snapshot("snap-third", 2),
    ]
    agent = make_test_agent_info(snapshots=snapshots)
    result = _get_field_value(agent, "host.snapshots[:2]")
    assert result == "snap-first, snap-second"


def test_get_field_value_list_slice_last_n() -> None:
    """_get_field_value should extract last N elements with [-N:]."""
    snapshots = [
        _create_test_snapshot("snap-first", 0),
        _create_test_snapshot("snap-second", 1),
        _create_test_snapshot("snap-third", 2),
    ]
    agent = make_test_agent_info(snapshots=snapshots)
    result = _get_field_value(agent, "host.snapshots[-2:]")
    assert result == "snap-second, snap-third"


def test_get_field_value_list_slice_range() -> None:
    """_get_field_value should extract range with [start:stop]."""
    snapshots = [
        _create_test_snapshot("snap-0", 0),
        _create_test_snapshot("snap-1", 1),
        _create_test_snapshot("snap-2", 2),
        _create_test_snapshot("snap-3", 3),
    ]
    agent = make_test_agent_info(snapshots=snapshots)
    result = _get_field_value(agent, "host.snapshots[1:3]")
    assert result == "snap-1, snap-2"


def test_get_field_value_list_index_out_of_bounds() -> None:
    """_get_field_value should return empty string for out of bounds index."""
    snapshots = [_create_test_snapshot("snap-only", 0)]
    agent = make_test_agent_info(snapshots=snapshots)
    result = _get_field_value(agent, "host.snapshots[5]")
    assert result == ""


def test_get_field_value_list_empty() -> None:
    """_get_field_value should return empty string for empty list with index."""
    agent = make_test_agent_info(snapshots=[])
    result = _get_field_value(agent, "host.snapshots[0]")
    assert result == ""


def test_get_field_value_list_empty_slice() -> None:
    """_get_field_value should return empty string for empty list with slice."""
    agent = make_test_agent_info(snapshots=[])
    result = _get_field_value(agent, "host.snapshots[:3]")
    assert result == ""


def test_get_field_value_bracket_on_non_list() -> None:
    """_get_field_value should return empty string for bracket on non-list field."""
    agent = make_test_agent_info()
    result = _get_field_value(agent, "host.name[0]")
    # host.name is a string, but we explicitly exclude strings from bracket indexing
    # for clearer behavior (strings would return single characters which is confusing)
    assert result == ""


def test_get_field_value_invalid_field() -> None:
    """_get_field_value should return empty string for invalid field."""
    agent = make_test_agent_info()
    result = _get_field_value(agent, "nonexistent")
    assert result == ""


def test_get_field_value_invalid_nested_field() -> None:
    """_get_field_value should return empty string for invalid nested field."""
    agent = make_test_agent_info()
    result = _get_field_value(agent, "host.nonexistent")
    assert result == ""


def test_get_field_value_invalid_slice_syntax() -> None:
    """_get_field_value should return empty string for invalid slice syntax."""
    snapshots = [_create_test_snapshot("snap-only", 0)]
    agent = make_test_agent_info(snapshots=snapshots)
    result = _get_field_value(agent, "host.snapshots[abc]")
    assert result == ""


def test_get_field_value_too_many_colons_in_slice() -> None:
    """_get_field_value should return empty string for too many colons in slice."""
    snapshots = [_create_test_snapshot("snap-only", 0)]
    agent = make_test_agent_info(snapshots=snapshots)
    result = _get_field_value(agent, "host.snapshots[1:2:3:4]")
    assert result == ""


# =============================================================================
# Edge case tests for slicing
# =============================================================================


def test_get_field_value_step_zero_returns_empty() -> None:
    """_get_field_value should return empty string for step=0 (invalid slice)."""
    snapshots = [
        _create_test_snapshot("snap-0", 0),
        _create_test_snapshot("snap-1", 1),
    ]
    agent = make_test_agent_info(snapshots=snapshots)
    # [::0] is invalid in Python - slice step cannot be zero
    result = _get_field_value(agent, "host.snapshots[::0]")
    assert result == ""


def test_get_field_value_empty_brackets_returns_empty() -> None:
    """_get_field_value should return empty string for empty brackets []."""
    snapshots = [_create_test_snapshot("snap-0", 0)]
    agent = make_test_agent_info(snapshots=snapshots)
    result = _get_field_value(agent, "host.snapshots[]")
    assert result == ""


def test_get_field_value_multiple_brackets_returns_empty() -> None:
    """_get_field_value should return empty string for multiple brackets [0][1]."""
    snapshots = [_create_test_snapshot("snap-0", 0)]
    agent = make_test_agent_info(snapshots=snapshots)
    result = _get_field_value(agent, "host.snapshots[0][0]")
    assert result == ""


def test_get_field_value_reverse_slice() -> None:
    """_get_field_value should support reverse slice [::-1]."""
    snapshots = [
        _create_test_snapshot("snap-0", 0),
        _create_test_snapshot("snap-1", 1),
        _create_test_snapshot("snap-2", 2),
    ]
    agent = make_test_agent_info(snapshots=snapshots)
    result = _get_field_value(agent, "host.snapshots[::-1]")
    assert result == "snap-2, snap-1, snap-0"


def test_get_field_value_negative_slice_bounds() -> None:
    """_get_field_value should support negative slice bounds [-3:-1]."""
    snapshots = [
        _create_test_snapshot("snap-0", 0),
        _create_test_snapshot("snap-1", 1),
        _create_test_snapshot("snap-2", 2),
        _create_test_snapshot("snap-3", 3),
    ]
    agent = make_test_agent_info(snapshots=snapshots)
    result = _get_field_value(agent, "host.snapshots[-3:-1]")
    assert result == "snap-1, snap-2"


def test_get_field_value_slice_with_step() -> None:
    """_get_field_value should support slice with step [::2]."""
    snapshots = [
        _create_test_snapshot("snap-0", 0),
        _create_test_snapshot("snap-1", 1),
        _create_test_snapshot("snap-2", 2),
        _create_test_snapshot("snap-3", 3),
    ]
    agent = make_test_agent_info(snapshots=snapshots)
    result = _get_field_value(agent, "host.snapshots[::2]")
    assert result == "snap-0, snap-2"


def test_get_field_value_whitespace_in_brackets() -> None:
    """_get_field_value should handle whitespace inside brackets."""
    snapshots = [
        _create_test_snapshot("snap-0", 0),
        _create_test_snapshot("snap-1", 1),
    ]
    agent = make_test_agent_info(snapshots=snapshots)
    result = _get_field_value(agent, "host.snapshots[ 0 ]")
    assert result == "snap-0"


def test_get_field_value_float_index_returns_empty() -> None:
    """_get_field_value should return empty string for float index [1.5]."""
    snapshots = [_create_test_snapshot("snap-0", 0)]
    agent = make_test_agent_info(snapshots=snapshots)
    result = _get_field_value(agent, "host.snapshots[1.5]")
    assert result == ""


def test_get_field_value_slice_beyond_list_length() -> None:
    """_get_field_value should return available elements for slice beyond list."""
    snapshots = [
        _create_test_snapshot("snap-0", 0),
        _create_test_snapshot("snap-1", 1),
    ]
    agent = make_test_agent_info(snapshots=snapshots)
    # Slice [0:100] on a 2-element list should return both elements
    result = _get_field_value(agent, "host.snapshots[0:100]")
    assert result == "snap-0, snap-1"


def test_get_field_value_slice_no_match_returns_empty() -> None:
    """_get_field_value should return empty string for slice with no matching elements."""
    snapshots = [
        _create_test_snapshot("snap-0", 0),
        _create_test_snapshot("snap-1", 1),
    ]
    agent = make_test_agent_info(snapshots=snapshots)
    # Slice [10:20] on a 2-element list should return empty
    result = _get_field_value(agent, "host.snapshots[10:20]")
    assert result == ""


def test_parse_slice_spec_negative_step() -> None:
    """_parse_slice_spec should parse negative step."""
    result = _parse_slice_spec("::-1")
    assert result == slice(None, None, -1)


def test_parse_slice_spec_negative_start_and_stop() -> None:
    """_parse_slice_spec should parse negative start and stop."""
    result = _parse_slice_spec("-3:-1")
    assert result == slice(-3, -1)


# =============================================================================
# Tests for _get_field_value with host plugin dict access
# =============================================================================


def test_get_field_value_host_plugin_top_level() -> None:
    """_get_field_value should access host plugin data via dict key traversal."""
    agent = make_test_agent_info(host_plugin={"aws": {"iam_user": "admin"}})
    result = _get_field_value(agent, "host.plugin.aws.iam_user")
    assert result == "admin"


def test_get_field_value_host_plugin_nested() -> None:
    """_get_field_value should access nested host plugin data."""
    agent = make_test_agent_info(host_plugin={"monitoring": {"endpoint": "https://example.com", "enabled": True}})
    result = _get_field_value(agent, "host.plugin.monitoring.endpoint")
    assert result == "https://example.com"


def test_get_field_value_host_plugin_missing_plugin_name() -> None:
    """_get_field_value should return empty for nonexistent plugin name."""
    agent = make_test_agent_info(host_plugin={})
    result = _get_field_value(agent, "host.plugin.nonexistent.field")
    assert result == ""


def test_get_field_value_host_plugin_missing_field() -> None:
    """_get_field_value should return empty for nonexistent field within plugin."""
    agent = make_test_agent_info(host_plugin={"aws": {"iam_user": "admin"}})
    result = _get_field_value(agent, "host.plugin.aws.nonexistent")
    assert result == ""


def test_get_field_value_host_plugin_whole_dict() -> None:
    """_get_field_value should format a dict value when accessing a plugin namespace."""
    agent = make_test_agent_info(host_plugin={"aws": {"iam_user": "admin"}})
    result = _get_field_value(agent, "host.plugin.aws")
    assert result == "{'iam_user': 'admin'}"


# =============================================================================
# Tests for _get_sortable_value with host plugin dict access
# =============================================================================


def test_get_sortable_value_host_plugin_field() -> None:
    """_get_sortable_value should return raw value for host plugin field."""
    agent = make_test_agent_info(host_plugin={"aws": {"iam_user": "admin"}})
    result = _get_sortable_value(agent, "host.plugin.aws.iam_user")
    assert result == "admin"


def test_get_sortable_value_host_plugin_missing() -> None:
    """_get_sortable_value should return None for nonexistent host plugin field."""
    agent = make_test_agent_info(host_plugin={})
    result = _get_sortable_value(agent, "host.plugin.nonexistent.field")
    assert result is None


# =============================================================================
# Tests for _get_sortable_value
# =============================================================================


def test_get_sortable_value_simple_field() -> None:
    """_get_sortable_value should return raw value for simple field."""
    agent = make_test_agent_info()
    result = _get_sortable_value(agent, "name")
    assert result == AgentName("test-agent")


def test_get_sortable_value_nested_field() -> None:
    """_get_sortable_value should return raw value for nested field."""
    agent = make_test_agent_info()
    result = _get_sortable_value(agent, "host.name")
    assert result == "test-host"


def test_get_sortable_value_alias() -> None:
    """_get_sortable_value should resolve field aliases."""
    agent = make_test_agent_info()
    result = _get_sortable_value(agent, "provider")
    assert result == "local"


def test_get_sortable_value_invalid_field() -> None:
    """_get_sortable_value should return None for invalid field."""
    agent = make_test_agent_info()
    result = _get_sortable_value(agent, "nonexistent")
    assert result is None


# =============================================================================
# Tests for _sort_agents
# =============================================================================


def test_sort_agents_by_name_ascending() -> None:
    """_sort_agents should sort by name in ascending order."""
    agents = [
        make_test_agent_info(name="charlie"),
        make_test_agent_info(name="alpha"),
        make_test_agent_info(name="bravo"),
    ]
    result = _sort_agents(agents, "name", reverse=False)
    assert [str(a.name) for a in result] == ["alpha", "bravo", "charlie"]


def test_sort_agents_by_name_descending() -> None:
    """_sort_agents should sort by name in descending order."""
    agents = [
        make_test_agent_info(name="alpha"),
        make_test_agent_info(name="charlie"),
        make_test_agent_info(name="bravo"),
    ]
    result = _sort_agents(agents, "name", reverse=True)
    assert [str(a.name) for a in result] == ["charlie", "bravo", "alpha"]


# =============================================================================
# Tests for _format_streaming_header_row and _format_streaming_agent_row
# =============================================================================


def test_format_streaming_header_row_uses_uppercase_fields() -> None:
    """_format_streaming_header_row should produce uppercase, dot-replaced headers."""
    fields = ["name", "host", "state"]
    widths = _compute_column_widths(fields, 120)
    result = _format_streaming_header_row(fields, widths)
    assert "NAME" in result
    assert "HOST" in result
    assert "STATE" in result


def test_format_streaming_agent_row_extracts_field_values() -> None:
    """_format_streaming_agent_row should extract and format agent field values."""
    agent = make_test_agent_info()
    fields = ["name", "provider"]
    widths = _compute_column_widths(fields, 120)
    result = _format_streaming_agent_row(agent, fields, widths)
    assert "test-agent" in result
    assert "local" in result


def test_compute_column_widths_respects_minimums() -> None:
    """_compute_column_widths should never go below minimum widths."""
    fields = ["name", "state"]
    widths = _compute_column_widths(fields, 120)
    assert widths["name"] >= 20
    assert widths["state"] >= 10


def test_compute_column_widths_expands_expandable_columns() -> None:
    """_compute_column_widths should give extra space to expandable columns."""
    fields = ["name", "state"]
    widths = _compute_column_widths(fields, 120)
    # name is expandable, state is not -- name should get all the extra space
    assert widths["name"] > 20
    assert widths["state"] == 10


# =============================================================================
# Tests for _StreamingHumanRenderer
# =============================================================================


def _create_streaming_renderer(
    fields: list[str],
    is_tty: bool,
) -> _StreamingHumanRenderer:
    """Create and initialize a streaming renderer for tests."""
    return _StreamingHumanRenderer(fields=fields, is_tty=is_tty)


def test_streaming_renderer_non_tty_no_ansi_codes(monkeypatch) -> None:
    """Non-TTY streaming output should contain no ANSI escape codes."""
    captured = StringIO()
    monkeypatch.setattr("sys.stdout", captured)

    renderer = _create_streaming_renderer(fields=["name", "state"], is_tty=False)
    renderer.start()
    renderer(make_test_agent_info())
    renderer.finish()

    output = captured.getvalue()
    assert "\x1b" not in output
    assert "test-agent" in output
    assert "NAME" in output


def test_streaming_renderer_tty_includes_status_line(monkeypatch) -> None:
    """TTY streaming output should include status line with ANSI codes."""
    captured = StringIO()
    monkeypatch.setattr("sys.stdout", captured)

    renderer = _create_streaming_renderer(fields=["name"], is_tty=True)
    renderer.start()

    output = captured.getvalue()
    assert "Searching..." in output


def test_streaming_renderer_tty_shows_count_after_agent(monkeypatch) -> None:
    """TTY streaming should update status line with count after agent is received."""
    captured = StringIO()
    monkeypatch.setattr("sys.stdout", captured)

    renderer = _create_streaming_renderer(fields=["name"], is_tty=True)
    renderer.start()
    renderer(make_test_agent_info())

    output = captured.getvalue()
    assert "(1 found)" in output


def test_streaming_renderer_finish_no_agents_shows_no_agents_found(monkeypatch) -> None:
    """Streaming renderer should indicate no agents when finishing with zero results."""
    captured = StringIO()
    monkeypatch.setattr("sys.stdout", captured)

    # Capture loguru output to the same StringIO by adding a temporary sink
    sink_id = logger.add(captured, format="{message}", level="INFO")
    try:
        renderer = _create_streaming_renderer(fields=["name"], is_tty=False)
        renderer.start()
        renderer.finish()
    finally:
        logger.remove(sink_id)

    output = captured.getvalue()
    assert "No agents found" in output


def test_streaming_renderer_thread_safety(monkeypatch) -> None:
    """Streaming renderer should handle concurrent calls without data corruption."""
    captured = StringIO()
    monkeypatch.setattr("sys.stdout", captured)

    renderer = _create_streaming_renderer(fields=["name"], is_tty=False)
    renderer.start()

    # Send agents from multiple threads concurrently
    agent_count = 20
    threads: list[threading.Thread] = []
    for idx in range(agent_count):
        agent = make_test_agent_info(name=f"agent-{idx}")
        thread = threading.Thread(target=renderer, args=(agent,))
        threads.append(thread)

    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    renderer.finish()

    output = captured.getvalue()
    # All agents should appear exactly once (header + 20 agent lines)
    lines = [line for line in output.strip().split("\n") if line.strip()]
    # 1 header + 20 agent rows
    assert len(lines) == agent_count + 1


def test_streaming_renderer_custom_fields(monkeypatch) -> None:
    """Streaming renderer should respect custom field selection."""
    captured = StringIO()
    monkeypatch.setattr("sys.stdout", captured)

    renderer = _create_streaming_renderer(fields=["name", "type"], is_tty=False)
    renderer.start()
    renderer(make_test_agent_info())
    renderer.finish()

    output = captured.getvalue()
    assert "NAME" in output
    assert "TYPE" in output
    assert "generic" in output


def test_streaming_renderer_tty_erases_status_on_finish(monkeypatch) -> None:
    """TTY streaming should erase the status line on finish."""
    captured = StringIO()
    monkeypatch.setattr("sys.stdout", captured)

    renderer = _create_streaming_renderer(fields=["name"], is_tty=True)
    renderer.start()
    renderer(make_test_agent_info())
    renderer.finish()

    output = captured.getvalue()
    # The final write should end with an erase-line sequence (no trailing status)
    assert output.endswith("\r\x1b[K")


# =============================================================================
# Tests for _should_use_streaming_mode
# =============================================================================


def test_should_use_streaming_mode_default_human() -> None:
    """Default HUMAN format without watch/sort/limit should use streaming mode."""
    assert (
        _should_use_streaming_mode(
            output_format=OutputFormat.HUMAN,
            is_watch=False,
            is_sort_explicit=False,
            limit=None,
        )
        is True
    )


def test_should_use_streaming_mode_with_limit_uses_batch() -> None:
    """--limit should force batch mode for deterministic results."""
    assert (
        _should_use_streaming_mode(
            output_format=OutputFormat.HUMAN,
            is_watch=False,
            is_sort_explicit=False,
            limit=5,
        )
        is False
    )


def test_should_use_streaming_mode_with_explicit_sort_uses_batch() -> None:
    """--sort should force batch mode for sorted output."""
    assert (
        _should_use_streaming_mode(
            output_format=OutputFormat.HUMAN,
            is_watch=False,
            is_sort_explicit=True,
            limit=None,
        )
        is False
    )


def test_should_use_streaming_mode_with_watch_uses_batch() -> None:
    """--watch should force batch mode."""
    assert (
        _should_use_streaming_mode(
            output_format=OutputFormat.HUMAN,
            is_watch=True,
            is_sort_explicit=False,
            limit=None,
        )
        is False
    )


def test_should_use_streaming_mode_json_format_uses_batch() -> None:
    """JSON format should use batch mode."""
    assert (
        _should_use_streaming_mode(
            output_format=OutputFormat.JSON,
            is_watch=False,
            is_sort_explicit=False,
            limit=None,
        )
        is False
    )
