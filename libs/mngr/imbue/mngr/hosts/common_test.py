from datetime import datetime
from datetime import timedelta
from datetime import timezone

from imbue.mngr.hosts.common import compute_idle_seconds
from imbue.mngr.hosts.common import determine_lifecycle_state
from imbue.mngr.hosts.common import get_descendant_process_names
from imbue.mngr.hosts.common import resolve_expected_process_name
from imbue.mngr.hosts.common import timestamp_to_datetime
from imbue.mngr.primitives import AgentLifecycleState
from imbue.mngr.primitives import CommandString

# =========================================================================
# timestamp_to_datetime tests
# =========================================================================


def test_timestamp_to_datetime_returns_none_for_none() -> None:
    assert timestamp_to_datetime(None) is None


def test_timestamp_to_datetime_converts_valid_timestamp() -> None:
    result = timestamp_to_datetime(1700000000)
    assert result is not None
    assert result.tzinfo == timezone.utc
    assert result.year == 2023


def test_timestamp_to_datetime_returns_none_for_invalid() -> None:
    result = timestamp_to_datetime(-99999999999999)
    assert result is None


# =========================================================================
# compute_idle_seconds tests
# =========================================================================


def test_compute_idle_seconds_returns_none_when_all_none() -> None:
    assert compute_idle_seconds(None, None, None) is None


def test_compute_idle_seconds_uses_most_recent() -> None:
    now = datetime.now(timezone.utc)
    old = now - timedelta(hours=1)
    recent = now - timedelta(seconds=10)
    result = compute_idle_seconds(old, recent, None)
    assert result is not None
    assert 9 < result < 15


def test_compute_idle_seconds_with_single_activity() -> None:
    recent = datetime.now(timezone.utc) - timedelta(seconds=5)
    result = compute_idle_seconds(None, recent, None)
    assert result is not None
    assert 4 < result < 10


# =========================================================================
# determine_lifecycle_state tests
# =========================================================================


def test_lifecycle_stopped_when_no_tmux_info() -> None:
    assert determine_lifecycle_state(None, False, "claude", "") == AgentLifecycleState.STOPPED


def test_lifecycle_stopped_when_malformed_tmux_info() -> None:
    assert determine_lifecycle_state("bad", False, "claude", "") == AgentLifecycleState.STOPPED


def test_lifecycle_done_when_pane_dead() -> None:
    assert determine_lifecycle_state("1|bash|123", False, "claude", "") == AgentLifecycleState.DONE


def test_lifecycle_running_when_command_matches_and_active() -> None:
    assert determine_lifecycle_state("0|claude|123", True, "claude", "") == AgentLifecycleState.RUNNING


def test_lifecycle_waiting_when_command_matches_and_not_active() -> None:
    assert determine_lifecycle_state("0|claude|123", False, "claude", "") == AgentLifecycleState.WAITING


def test_lifecycle_running_when_descendant_matches() -> None:
    ps_output = "100 1 init\n200 123 bash\n300 200 claude\n"
    assert determine_lifecycle_state("0|bash|123", True, "claude", ps_output) == AgentLifecycleState.RUNNING


def test_lifecycle_replaced_when_non_shell_descendant() -> None:
    ps_output = "200 123 python3\n"
    assert determine_lifecycle_state("0|bash|123", True, "claude", ps_output) == AgentLifecycleState.REPLACED


def test_lifecycle_done_when_shell_only() -> None:
    assert determine_lifecycle_state("0|bash|123", True, "claude", "") == AgentLifecycleState.DONE


def test_lifecycle_replaced_when_unknown_command() -> None:
    assert determine_lifecycle_state("0|python3|123", True, "claude", "") == AgentLifecycleState.REPLACED


# =========================================================================
# get_descendant_process_names tests
# =========================================================================


def test_descendant_names_returns_empty_for_no_children() -> None:
    ps_output = "100 1 init\n200 1 sshd\n"
    result = get_descendant_process_names("999", ps_output)
    assert result == []


def test_descendant_names_finds_direct_children() -> None:
    ps_output = "100 1 init\n200 100 bash\n300 100 sshd\n"
    result = get_descendant_process_names("100", ps_output)
    assert set(result) == {"bash", "sshd"}


def test_descendant_names_finds_nested_children() -> None:
    ps_output = "100 1 init\n200 100 bash\n300 200 claude\n400 300 node\n"
    result = get_descendant_process_names("100", ps_output)
    assert result == ["bash", "claude", "node"]


# =========================================================================
# resolve_expected_process_name tests
# =========================================================================


def test_resolve_expected_process_name_for_claude() -> None:
    from imbue.mngr.config.data_types import MngrConfig

    config = MngrConfig.model_construct(agent_types={})
    result = resolve_expected_process_name("claude", CommandString("complex wrapper command"), config)
    assert result == "claude"


def test_resolve_expected_process_name_for_simple_command() -> None:
    from imbue.mngr.config.data_types import MngrConfig

    config = MngrConfig.model_construct(agent_types={})
    result = resolve_expected_process_name("custom", CommandString("/usr/bin/my-agent --flag"), config)
    assert result == "my-agent"


def test_resolve_expected_process_name_for_custom_type_with_claude_parent() -> None:
    from imbue.mngr.config.data_types import AgentTypeConfig
    from imbue.mngr.config.data_types import MngrConfig
    from imbue.mngr.primitives import AgentTypeName

    custom_config = AgentTypeConfig.model_construct(parent_type=AgentTypeName("claude"))
    config = MngrConfig.model_construct(agent_types={AgentTypeName("my-claude"): custom_config})
    result = resolve_expected_process_name("my-claude", CommandString("complex wrapper"), config)
    assert result == "claude"


def test_resolve_expected_process_name_for_bare_command() -> None:
    from imbue.mngr.config.data_types import MngrConfig

    config = MngrConfig.model_construct(agent_types={})
    result = resolve_expected_process_name("unknown", CommandString("sleep"), config)
    assert result == "sleep"
