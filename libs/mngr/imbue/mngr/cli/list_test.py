"""Tests for CLI list command helpers."""

from datetime import datetime
from datetime import timezone
from pathlib import Path

from imbue.mngr.api.list import AgentInfo
from imbue.mngr.cli.list import _format_value_as_string
from imbue.mngr.cli.list import _get_field_value
from imbue.mngr.cli.list import _get_sortable_value
from imbue.mngr.cli.list import _parse_slice_spec
from imbue.mngr.cli.list import _sort_agents
from imbue.mngr.interfaces.data_types import HostInfo
from imbue.mngr.interfaces.data_types import SnapshotInfo
from imbue.mngr.primitives import AgentId
from imbue.mngr.primitives import AgentLifecycleState
from imbue.mngr.primitives import AgentName
from imbue.mngr.primitives import CommandString
from imbue.mngr.primitives import HostId
from imbue.mngr.primitives import HostState
from imbue.mngr.primitives import ProviderInstanceName
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


def _create_test_agent(snapshots: list[SnapshotInfo] | None = None) -> AgentInfo:
    """Create a test AgentInfo for testing field extraction."""
    host_info = HostInfo(
        id=HostId.generate(),
        name="test-host",
        provider_name=ProviderInstanceName("local"),
        snapshots=snapshots or [],
        state=HostState.RUNNING,
    )
    return AgentInfo(
        id=AgentId.generate(),
        name=AgentName("test-agent"),
        type="claude",
        command=CommandString("claude"),
        work_dir=Path("/tmp/work"),
        create_time=datetime.now(timezone.utc),
        start_on_boot=False,
        state=AgentLifecycleState.RUNNING,
        host=host_info,
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
    assert result == "RUNNING"


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
    agent = _create_test_agent()
    result = _get_field_value(agent, "name")
    assert result == "test-agent"


def test_get_field_value_nested_field() -> None:
    """_get_field_value should extract nested field."""
    agent = _create_test_agent()
    result = _get_field_value(agent, "host.name")
    assert result == "test-host"


def test_get_field_value_with_alias() -> None:
    """_get_field_value should resolve field aliases."""
    agent = _create_test_agent()
    result = _get_field_value(agent, "provider")
    assert result == "local"


def test_get_field_value_list_index_first() -> None:
    """_get_field_value should extract first element with [0]."""
    snapshots = [
        _create_test_snapshot("snap-first", 0),
        _create_test_snapshot("snap-second", 1),
        _create_test_snapshot("snap-third", 2),
    ]
    agent = _create_test_agent(snapshots)
    result = _get_field_value(agent, "host.snapshots[0]")
    assert result == "snap-first"


def test_get_field_value_list_index_last() -> None:
    """_get_field_value should extract last element with [-1]."""
    snapshots = [
        _create_test_snapshot("snap-first", 0),
        _create_test_snapshot("snap-second", 1),
        _create_test_snapshot("snap-third", 2),
    ]
    agent = _create_test_agent(snapshots)
    result = _get_field_value(agent, "host.snapshots[-1]")
    assert result == "snap-third"


def test_get_field_value_list_index_middle() -> None:
    """_get_field_value should extract middle element with index."""
    snapshots = [
        _create_test_snapshot("snap-first", 0),
        _create_test_snapshot("snap-second", 1),
        _create_test_snapshot("snap-third", 2),
    ]
    agent = _create_test_agent(snapshots)
    result = _get_field_value(agent, "host.snapshots[1]")
    assert result == "snap-second"


def test_get_field_value_list_slice_first_n() -> None:
    """_get_field_value should extract first N elements with [:N]."""
    snapshots = [
        _create_test_snapshot("snap-first", 0),
        _create_test_snapshot("snap-second", 1),
        _create_test_snapshot("snap-third", 2),
    ]
    agent = _create_test_agent(snapshots)
    result = _get_field_value(agent, "host.snapshots[:2]")
    assert result == "snap-first, snap-second"


def test_get_field_value_list_slice_last_n() -> None:
    """_get_field_value should extract last N elements with [-N:]."""
    snapshots = [
        _create_test_snapshot("snap-first", 0),
        _create_test_snapshot("snap-second", 1),
        _create_test_snapshot("snap-third", 2),
    ]
    agent = _create_test_agent(snapshots)
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
    agent = _create_test_agent(snapshots)
    result = _get_field_value(agent, "host.snapshots[1:3]")
    assert result == "snap-1, snap-2"


def test_get_field_value_list_index_out_of_bounds() -> None:
    """_get_field_value should return empty string for out of bounds index."""
    snapshots = [_create_test_snapshot("snap-only", 0)]
    agent = _create_test_agent(snapshots)
    result = _get_field_value(agent, "host.snapshots[5]")
    assert result == ""


def test_get_field_value_list_empty() -> None:
    """_get_field_value should return empty string for empty list with index."""
    agent = _create_test_agent([])
    result = _get_field_value(agent, "host.snapshots[0]")
    assert result == ""


def test_get_field_value_list_empty_slice() -> None:
    """_get_field_value should return empty string for empty list with slice."""
    agent = _create_test_agent([])
    result = _get_field_value(agent, "host.snapshots[:3]")
    assert result == ""


def test_get_field_value_bracket_on_non_list() -> None:
    """_get_field_value should return empty string for bracket on non-list field."""
    agent = _create_test_agent()
    result = _get_field_value(agent, "host.name[0]")
    # host.name is a string, but we explicitly exclude strings from bracket indexing
    # for clearer behavior (strings would return single characters which is confusing)
    assert result == ""


def test_get_field_value_invalid_field() -> None:
    """_get_field_value should return empty string for invalid field."""
    agent = _create_test_agent()
    result = _get_field_value(agent, "nonexistent")
    assert result == ""


def test_get_field_value_invalid_nested_field() -> None:
    """_get_field_value should return empty string for invalid nested field."""
    agent = _create_test_agent()
    result = _get_field_value(agent, "host.nonexistent")
    assert result == ""


def test_get_field_value_invalid_slice_syntax() -> None:
    """_get_field_value should return empty string for invalid slice syntax."""
    snapshots = [_create_test_snapshot("snap-only", 0)]
    agent = _create_test_agent(snapshots)
    result = _get_field_value(agent, "host.snapshots[abc]")
    assert result == ""


def test_get_field_value_too_many_colons_in_slice() -> None:
    """_get_field_value should return empty string for too many colons in slice."""
    snapshots = [_create_test_snapshot("snap-only", 0)]
    agent = _create_test_agent(snapshots)
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
    agent = _create_test_agent(snapshots)
    # [::0] is invalid in Python - slice step cannot be zero
    result = _get_field_value(agent, "host.snapshots[::0]")
    assert result == ""


def test_get_field_value_empty_brackets_returns_empty() -> None:
    """_get_field_value should return empty string for empty brackets []."""
    snapshots = [_create_test_snapshot("snap-0", 0)]
    agent = _create_test_agent(snapshots)
    result = _get_field_value(agent, "host.snapshots[]")
    assert result == ""


def test_get_field_value_multiple_brackets_returns_empty() -> None:
    """_get_field_value should return empty string for multiple brackets [0][1]."""
    snapshots = [_create_test_snapshot("snap-0", 0)]
    agent = _create_test_agent(snapshots)
    result = _get_field_value(agent, "host.snapshots[0][0]")
    assert result == ""


def test_get_field_value_reverse_slice() -> None:
    """_get_field_value should support reverse slice [::-1]."""
    snapshots = [
        _create_test_snapshot("snap-0", 0),
        _create_test_snapshot("snap-1", 1),
        _create_test_snapshot("snap-2", 2),
    ]
    agent = _create_test_agent(snapshots)
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
    agent = _create_test_agent(snapshots)
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
    agent = _create_test_agent(snapshots)
    result = _get_field_value(agent, "host.snapshots[::2]")
    assert result == "snap-0, snap-2"


def test_get_field_value_whitespace_in_brackets() -> None:
    """_get_field_value should handle whitespace inside brackets."""
    snapshots = [
        _create_test_snapshot("snap-0", 0),
        _create_test_snapshot("snap-1", 1),
    ]
    agent = _create_test_agent(snapshots)
    result = _get_field_value(agent, "host.snapshots[ 0 ]")
    assert result == "snap-0"


def test_get_field_value_float_index_returns_empty() -> None:
    """_get_field_value should return empty string for float index [1.5]."""
    snapshots = [_create_test_snapshot("snap-0", 0)]
    agent = _create_test_agent(snapshots)
    result = _get_field_value(agent, "host.snapshots[1.5]")
    assert result == ""


def test_get_field_value_slice_beyond_list_length() -> None:
    """_get_field_value should return available elements for slice beyond list."""
    snapshots = [
        _create_test_snapshot("snap-0", 0),
        _create_test_snapshot("snap-1", 1),
    ]
    agent = _create_test_agent(snapshots)
    # Slice [0:100] on a 2-element list should return both elements
    result = _get_field_value(agent, "host.snapshots[0:100]")
    assert result == "snap-0, snap-1"


def test_get_field_value_slice_no_match_returns_empty() -> None:
    """_get_field_value should return empty string for slice with no matching elements."""
    snapshots = [
        _create_test_snapshot("snap-0", 0),
        _create_test_snapshot("snap-1", 1),
    ]
    agent = _create_test_agent(snapshots)
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
# Tests for _get_sortable_value
# =============================================================================


def test_get_sortable_value_simple_field() -> None:
    """_get_sortable_value should return raw value for simple field."""
    agent = _create_test_agent()
    result = _get_sortable_value(agent, "name")
    assert result == AgentName("test-agent")


def test_get_sortable_value_nested_field() -> None:
    """_get_sortable_value should return raw value for nested field."""
    agent = _create_test_agent()
    result = _get_sortable_value(agent, "host.name")
    assert result == "test-host"


def test_get_sortable_value_alias() -> None:
    """_get_sortable_value should resolve field aliases."""
    agent = _create_test_agent()
    result = _get_sortable_value(agent, "provider")
    assert result == "local"


def test_get_sortable_value_invalid_field() -> None:
    """_get_sortable_value should return None for invalid field."""
    agent = _create_test_agent()
    result = _get_sortable_value(agent, "nonexistent")
    assert result is None


# =============================================================================
# Tests for _sort_agents
# =============================================================================


def test_sort_agents_by_name_ascending() -> None:
    """_sort_agents should sort by name in ascending order."""
    agents = [
        _create_test_agent_with_name("charlie"),
        _create_test_agent_with_name("alpha"),
        _create_test_agent_with_name("bravo"),
    ]
    result = _sort_agents(agents, "name", reverse=False)
    assert [str(a.name) for a in result] == ["alpha", "bravo", "charlie"]


def test_sort_agents_by_name_descending() -> None:
    """_sort_agents should sort by name in descending order."""
    agents = [
        _create_test_agent_with_name("alpha"),
        _create_test_agent_with_name("charlie"),
        _create_test_agent_with_name("bravo"),
    ]
    result = _sort_agents(agents, "name", reverse=True)
    assert [str(a.name) for a in result] == ["charlie", "bravo", "alpha"]


def _create_test_agent_with_name(name: str) -> AgentInfo:
    """Create a test AgentInfo with the specified name."""
    host_info = HostInfo(
        id=HostId.generate(),
        name="test-host",
        provider_name=ProviderInstanceName("local"),
        snapshots=[],
        state=HostState.RUNNING,
    )
    return AgentInfo(
        id=AgentId.generate(),
        name=AgentName(name),
        type="claude",
        command=CommandString("claude"),
        work_dir=Path("/tmp/work"),
        create_time=datetime.now(timezone.utc),
        start_on_boot=False,
        state=AgentLifecycleState.RUNNING,
        host=host_info,
    )
