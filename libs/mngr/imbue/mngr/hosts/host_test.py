"""Unit tests for Host implementation."""

import json
from datetime import datetime
from datetime import timezone
from pathlib import Path

import pytest

from imbue.mngr.agents.base_agent import BaseAgent
from imbue.mngr.config.data_types import AgentTypeConfig
from imbue.mngr.errors import AgentError
from imbue.mngr.hosts.host import Host
from imbue.mngr.hosts.host import _build_start_agent_shell_command
from imbue.mngr.hosts.host import _parse_boot_time_output
from imbue.mngr.hosts.host import _parse_uptime_output
from imbue.mngr.interfaces.host import NamedCommand
from imbue.mngr.interfaces.host import OnlineHostInterface
from imbue.mngr.primitives import AgentId
from imbue.mngr.primitives import AgentName
from imbue.mngr.primitives import AgentTypeName
from imbue.mngr.primitives import CommandString
from imbue.mngr.primitives import HostName
from imbue.mngr.providers.local.instance import LocalProviderInstance
from imbue.mngr.utils.testing import get_short_random_string


class _TestableAgent(BaseAgent):
    """Test agent with observable on_destroy behavior."""

    on_destroy_called: bool = False
    on_destroy_should_raise: bool = False

    def on_destroy(self, host: OnlineHostInterface) -> None:
        self.on_destroy_called = True
        if self.on_destroy_should_raise:
            raise AgentError("cleanup failed")


def _create_testable_agent(
    local_provider: LocalProviderInstance,
    temp_host_dir: Path,
    temp_work_dir: Path,
    *,
    on_destroy_should_raise: bool = False,
) -> tuple[_TestableAgent, Host]:
    """Create a _TestableAgent with proper filesystem setup."""
    host = local_provider.create_host(HostName("test"))
    assert isinstance(host, Host)

    agent_id = AgentId.generate()
    agent_name = AgentName(f"test-agent-{get_short_random_string()}")

    create_time = datetime.now(timezone.utc)

    # Create agent directory and data.json
    agent_dir = temp_host_dir / "agents" / str(agent_id)
    agent_dir.mkdir(parents=True, exist_ok=True)
    data = {
        "id": str(agent_id),
        "name": str(agent_name),
        "type": "test",
        "command": "sleep 1000",
        "work_dir": str(temp_work_dir),
        "create_time": create_time.isoformat(),
    }
    (agent_dir / "data.json").write_text(json.dumps(data))

    agent = _TestableAgent(
        id=agent_id,
        name=agent_name,
        agent_type=AgentTypeName("test"),
        work_dir=temp_work_dir,
        create_time=create_time,
        host_id=host.id,
        host=host,
        mngr_ctx=local_provider.mngr_ctx,
        agent_config=AgentTypeConfig(command=CommandString("sleep 1000")),
        on_destroy_should_raise=on_destroy_should_raise,
    )
    return agent, host


@pytest.fixture
def host_with_agents_dir(
    local_provider: LocalProviderInstance,
    temp_host_dir: Path,
) -> tuple[Host, Path]:
    """Create a Host with an agents directory for testing."""
    host = local_provider.create_host(HostName("test-agent-refs"))
    assert isinstance(host, Host)
    agents_dir = temp_host_dir / "agents"
    agents_dir.mkdir(parents=True, exist_ok=True)
    return host, agents_dir


def test_get_agent_references_returns_refs_with_certified_data(
    host_with_agents_dir: tuple[Host, Path],
) -> None:
    """Test that get_agent_references returns refs with certified_data populated."""
    host, agents_dir = host_with_agents_dir

    # Create agent data
    agent_id = AgentId.generate()
    agent_dir = agents_dir / str(agent_id)
    agent_dir.mkdir()
    agent_data = {
        "id": str(agent_id),
        "name": "test-agent",
        "type": "claude",
        "permissions": ["read", "write"],
        "work_dir": "/tmp/work",
    }
    (agent_dir / "data.json").write_text(json.dumps(agent_data))

    refs = host.get_agent_references()

    assert len(refs) == 1
    assert refs[0].agent_id == agent_id
    assert refs[0].agent_name == AgentName("test-agent")
    assert refs[0].host_id == host.id
    assert refs[0].certified_data == agent_data
    assert refs[0].agent_type == "claude"
    assert refs[0].permissions == ("read", "write")
    assert refs[0].work_dir == Path("/tmp/work")


def test_get_agent_references_returns_empty_when_no_agents_dir(
    local_provider: LocalProviderInstance,
) -> None:
    """Test that get_agent_references returns empty list when no agents directory exists."""
    host = local_provider.create_host(HostName("test-no-agents"))
    assert isinstance(host, Host)

    # Don't create agents directory
    refs = host.get_agent_references()

    assert refs == []


def test_get_agent_references_skips_missing_data_json(
    host_with_agents_dir: tuple[Host, Path],
) -> None:
    """Test that get_agent_references skips agent dirs without data.json."""
    host, agents_dir = host_with_agents_dir

    # Create agent directory without data.json
    agent_id = AgentId.generate()
    agent_dir = agents_dir / str(agent_id)
    agent_dir.mkdir()
    # Don't create data.json

    refs = host.get_agent_references()

    assert refs == []


def test_get_agent_references_skips_invalid_json(
    host_with_agents_dir: tuple[Host, Path],
) -> None:
    """Test that get_agent_references skips agent dirs with invalid JSON."""
    host, agents_dir = host_with_agents_dir

    # Create agent with invalid JSON
    agent_id = AgentId.generate()
    agent_dir = agents_dir / str(agent_id)
    agent_dir.mkdir()
    (agent_dir / "data.json").write_text("not valid json {{{")

    refs = host.get_agent_references()

    assert refs == []


def test_get_agent_references_skips_missing_id(
    host_with_agents_dir: tuple[Host, Path],
) -> None:
    """Test that get_agent_references skips records with missing id."""
    host, agents_dir = host_with_agents_dir

    # Create agent data without id
    agent_id = AgentId.generate()
    agent_dir = agents_dir / str(agent_id)
    agent_dir.mkdir()
    agent_data = {"name": "test-agent"}
    (agent_dir / "data.json").write_text(json.dumps(agent_data))

    refs = host.get_agent_references()

    assert refs == []


def test_get_agent_references_skips_missing_name(
    host_with_agents_dir: tuple[Host, Path],
) -> None:
    """Test that get_agent_references skips records with missing name."""
    host, agents_dir = host_with_agents_dir

    # Create agent data without name
    agent_id = AgentId.generate()
    agent_dir = agents_dir / str(agent_id)
    agent_dir.mkdir()
    agent_data = {"id": str(agent_id)}
    (agent_dir / "data.json").write_text(json.dumps(agent_data))

    refs = host.get_agent_references()

    assert refs == []


def test_get_agent_references_skips_invalid_id(
    host_with_agents_dir: tuple[Host, Path],
) -> None:
    """Test that get_agent_references skips records with invalid id format."""
    host, agents_dir = host_with_agents_dir

    # Create agent data with invalid id
    agent_id = AgentId.generate()
    agent_dir = agents_dir / str(agent_id)
    agent_dir.mkdir()
    agent_data = {"id": "", "name": "test-agent"}
    (agent_dir / "data.json").write_text(json.dumps(agent_data))

    refs = host.get_agent_references()

    assert refs == []


def test_get_agent_references_skips_invalid_name(
    host_with_agents_dir: tuple[Host, Path],
) -> None:
    """Test that get_agent_references skips records with invalid name format."""
    host, agents_dir = host_with_agents_dir

    # Create agent data with invalid name
    agent_id = AgentId.generate()
    agent_dir = agents_dir / str(agent_id)
    agent_dir.mkdir()
    agent_data = {"id": str(agent_id), "name": ""}
    (agent_dir / "data.json").write_text(json.dumps(agent_data))

    refs = host.get_agent_references()

    assert refs == []


def test_get_agent_references_loads_multiple_agents(
    host_with_agents_dir: tuple[Host, Path],
) -> None:
    """Test that get_agent_references loads all valid agents."""
    host, agents_dir = host_with_agents_dir

    # Create multiple agents
    agent_ids = [AgentId.generate() for _ in range(3)]
    for i, agent_id in enumerate(agent_ids):
        agent_dir = agents_dir / str(agent_id)
        agent_dir.mkdir()
        agent_data = {"id": str(agent_id), "name": f"agent-{i}"}
        (agent_dir / "data.json").write_text(json.dumps(agent_data))

    refs = host.get_agent_references()

    assert len(refs) == 3
    ref_ids = {ref.agent_id for ref in refs}
    assert ref_ids == set(agent_ids)


def test_get_agent_references_skips_bad_records_but_loads_good_ones(
    host_with_agents_dir: tuple[Host, Path],
) -> None:
    """Test that get_agent_references skips bad records but still loads good ones."""
    host, agents_dir = host_with_agents_dir

    # Create a good agent
    good_id = AgentId.generate()
    good_dir = agents_dir / str(good_id)
    good_dir.mkdir()
    (good_dir / "data.json").write_text(json.dumps({"id": str(good_id), "name": "good-agent"}))

    # Create a bad agent (missing name)
    bad_id = AgentId.generate()
    bad_dir = agents_dir / str(bad_id)
    bad_dir.mkdir()
    (bad_dir / "data.json").write_text(json.dumps({"id": str(bad_id)}))

    # Create another good agent
    good_id_2 = AgentId.generate()
    good_dir_2 = agents_dir / str(good_id_2)
    good_dir_2.mkdir()
    (good_dir_2 / "data.json").write_text(json.dumps({"id": str(good_id_2), "name": "good-agent-2"}))

    refs = host.get_agent_references()

    # Should have 2 good agents, bad one skipped
    assert len(refs) == 2
    ref_ids = {ref.agent_id for ref in refs}
    assert good_id in ref_ids
    assert good_id_2 in ref_ids
    assert bad_id not in ref_ids


def test_destroy_agent_calls_on_destroy(
    local_provider: LocalProviderInstance,
    temp_host_dir: Path,
    temp_work_dir: Path,
) -> None:
    """Test that destroy_agent calls agent.on_destroy() before cleanup."""
    agent, host = _create_testable_agent(local_provider, temp_host_dir, temp_work_dir)

    agent_dir = temp_host_dir / "agents" / str(agent.id)
    assert agent_dir.exists()

    host.destroy_agent(agent)

    assert agent.on_destroy_called
    assert not agent_dir.exists()


def test_destroy_agent_continues_cleanup_when_on_destroy_raises(
    local_provider: LocalProviderInstance,
    temp_host_dir: Path,
    temp_work_dir: Path,
) -> None:
    """Test that destroy_agent still cleans up if agent.on_destroy() raises."""
    agent, host = _create_testable_agent(local_provider, temp_host_dir, temp_work_dir, on_destroy_should_raise=True)

    agent_dir = temp_host_dir / "agents" / str(agent.id)
    assert agent_dir.exists()

    # Exception propagates, but cleanup still runs
    with pytest.raises(AgentError, match="cleanup failed"):
        host.destroy_agent(agent)

    # State directory should still be cleaned up
    assert not agent_dir.exists()


# =========================================================================
# Tests for _build_start_agent_shell_command
# =========================================================================


def _create_test_agent(
    local_provider: LocalProviderInstance,
    temp_host_dir: Path,
    temp_work_dir: Path,
) -> BaseAgent:
    """Create a minimal test agent for command building tests."""
    host = local_provider.create_host(HostName("test"))
    assert isinstance(host, Host)

    agent_id = AgentId.generate()
    agent_name = AgentName(f"test-agent-{get_short_random_string()}")

    # Create agent directory and data.json
    agent_dir = temp_host_dir / "agents" / str(agent_id)
    agent_dir.mkdir(parents=True, exist_ok=True)
    data = {
        "id": str(agent_id),
        "name": str(agent_name),
        "type": "test",
        "command": "sleep 1000",
        "work_dir": str(temp_work_dir),
    }
    (agent_dir / "data.json").write_text(json.dumps(data))

    return BaseAgent(
        id=agent_id,
        name=agent_name,
        agent_type=AgentTypeName("test"),
        work_dir=temp_work_dir,
        create_time=datetime.now(timezone.utc),
        host_id=host.id,
        host=host,
        mngr_ctx=local_provider.mngr_ctx,
        agent_config=AgentTypeConfig(command=CommandString("sleep 1000")),
    )


def _build_command_with_defaults(
    agent: BaseAgent,
    host_dir: Path,
    additional_commands: list[NamedCommand] | None = None,
    unset_vars: list[str] | None = None,
) -> str:
    """Call _build_start_agent_shell_command with standard test defaults."""
    return _build_start_agent_shell_command(
        agent=agent,
        session_name=f"mngr-{agent.name}",
        command="sleep 1000",
        additional_commands=additional_commands if additional_commands is not None else [],
        env_shell_cmd="bash -c 'exec bash'",
        tmux_config_path=Path("/tmp/tmux.conf"),
        unset_vars=unset_vars if unset_vars is not None else [],
        host_dir=host_dir,
    )


def test_build_start_agent_shell_command_produces_single_command(
    local_provider: LocalProviderInstance,
    temp_host_dir: Path,
    temp_work_dir: Path,
) -> None:
    """The function should produce a single &&-chained shell command."""
    agent = _create_test_agent(local_provider, temp_host_dir, temp_work_dir)
    result = _build_command_with_defaults(agent, temp_host_dir)

    assert isinstance(result, str)

    # Should contain the core tmux commands chained with &&
    assert "tmux" in result
    assert "new-session" in result
    assert "set-option" in result
    assert "send-keys" in result

    # Should contain activity recording
    assert "mkdir -p" in result
    assert "activity" in result

    # Should contain the process monitor
    assert "nohup" in result
    assert "pane_pid" in result


def test_build_start_agent_shell_command_includes_unset_vars(
    local_provider: LocalProviderInstance,
    temp_host_dir: Path,
    temp_work_dir: Path,
) -> None:
    """Unset vars should appear at the start of the command chain."""
    agent = _create_test_agent(local_provider, temp_host_dir, temp_work_dir)
    result = _build_command_with_defaults(agent, temp_host_dir, unset_vars=["FOO_VAR", "BAR_VAR"])

    assert "unset FOO_VAR" in result
    assert "unset BAR_VAR" in result

    # Unset commands should come before tmux new-session
    unset_pos = result.index("unset")
    new_session_pos = result.index("new-session")
    assert unset_pos < new_session_pos


def test_build_start_agent_shell_command_includes_additional_windows(
    local_provider: LocalProviderInstance,
    temp_host_dir: Path,
    temp_work_dir: Path,
) -> None:
    """Additional commands should create new tmux windows."""
    agent = _create_test_agent(local_provider, temp_host_dir, temp_work_dir)
    additional_commands = [
        NamedCommand(command=CommandString("tail -f /var/log/syslog"), window_name="logs"),
        NamedCommand(command=CommandString("htop"), window_name=None),
    ]
    result = _build_command_with_defaults(agent, temp_host_dir, additional_commands=additional_commands)

    # Should create new windows
    assert "new-window" in result
    assert "logs" in result
    assert "cmd-2" in result

    # Should select window 0 at the end (since we have additional commands)
    assert "select-window" in result

    # Should send keys for the additional commands
    assert "tail -f /var/log/syslog" in result
    assert "htop" in result


def test_build_start_agent_shell_command_no_select_window_without_additional_commands(
    local_provider: LocalProviderInstance,
    temp_host_dir: Path,
    temp_work_dir: Path,
) -> None:
    """select-window should not appear when there are no additional commands."""
    agent = _create_test_agent(local_provider, temp_host_dir, temp_work_dir)
    result = _build_command_with_defaults(agent, temp_host_dir)

    assert "select-window" not in result


def test_build_start_agent_shell_command_uses_and_chaining(
    local_provider: LocalProviderInstance,
    temp_host_dir: Path,
    temp_work_dir: Path,
) -> None:
    """All steps should be chained with && for fail-fast behavior."""
    agent = _create_test_agent(local_provider, temp_host_dir, temp_work_dir)
    result = _build_command_with_defaults(agent, temp_host_dir)

    # The guard is joined with ";", the rest with "&&"
    # Split past the guard to check the && chain
    assert "; " in result
    after_guard = result.split("; ", 1)[1]
    parts = after_guard.split(" && ")
    assert len(parts) >= 6


def test_build_start_agent_shell_command_bails_if_session_exists(
    local_provider: LocalProviderInstance,
    temp_host_dir: Path,
    temp_work_dir: Path,
) -> None:
    """The command should start with a guard that exits early if the tmux session already exists."""
    agent = _create_test_agent(local_provider, temp_host_dir, temp_work_dir)
    result = _build_command_with_defaults(agent, temp_host_dir)
    session_name = f"mngr-{agent.name}"

    # Guard should be the first part (before the ";")
    guard, rest = result.split("; ", 1)
    assert "has-session" in guard
    assert session_name in guard
    assert "exit 0" in guard

    # The rest of the command (tmux new-session, etc.) comes after
    assert "new-session" in rest


def test_build_start_agent_shell_command_monitor_retries_pane_pid(
    local_provider: LocalProviderInstance,
    temp_host_dir: Path,
    temp_work_dir: Path,
) -> None:
    """The process monitor should retry getting the pane PID instead of exiting immediately."""
    agent = _create_test_agent(local_provider, temp_host_dir, temp_work_dir)
    result = _build_command_with_defaults(agent, temp_host_dir)

    # The monitor script should contain retry loop elements
    assert "TRIES=0" in result
    assert "TRIES=$((TRIES + 1))" in result
    assert "sleep 1" in result


# =========================================================================
# Tests for _parse_uptime_output
# =========================================================================


def test_parse_uptime_output_macos_format() -> None:
    """Test parsing macOS-style uptime output (boot timestamp + current timestamp)."""
    # macOS sysctl gives boot time, date gives current time
    stdout = "1700000000\n1700003600\n"
    result = _parse_uptime_output(stdout)
    assert result == 3600.0


def test_parse_uptime_output_linux_format() -> None:
    """Test parsing Linux-style /proc/uptime output."""
    stdout = "12345.67 98765.43\n"
    result = _parse_uptime_output(stdout)
    assert result == 12345.67


def test_parse_uptime_output_empty() -> None:
    """Test parsing empty output returns 0."""
    assert _parse_uptime_output("") == 0.0
    assert _parse_uptime_output("  \n") == 0.0


def test_parse_uptime_output_unexpected_lines() -> None:
    """Test parsing output with unexpected number of lines returns 0."""
    stdout = "line1\nline2\nline3\n"
    assert _parse_uptime_output(stdout) == 0.0


# =========================================================================
# Tests for _parse_boot_time_output
# =========================================================================


def test_parse_boot_time_output_valid_timestamp() -> None:
    """Test parsing a valid Unix timestamp returns the correct datetime."""
    # Both macOS sysctl and Linux btime produce a single Unix timestamp
    result = _parse_boot_time_output("1700000000\n")
    assert result is not None
    assert result == datetime(2023, 11, 14, 22, 13, 20, tzinfo=timezone.utc)


def test_parse_boot_time_output_empty() -> None:
    """Test parsing empty output returns None."""
    assert _parse_boot_time_output("") is None
    assert _parse_boot_time_output("  \n") is None


def test_parse_boot_time_output_non_numeric() -> None:
    """Test parsing non-numeric output returns None."""
    assert _parse_boot_time_output("not_a_number\n") is None
