"""Unit tests for the connect API module."""

from datetime import datetime
from datetime import timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
from pyinfra.api import Host as PyinfraHost
from pyinfra.api import State as PyinfraState
from pyinfra.api.inventory import Inventory

from imbue.mngr.agents.base_agent import BaseAgent
from imbue.mngr.api.connect import SIGNAL_EXIT_CODE_DESTROY
from imbue.mngr.api.connect import SIGNAL_EXIT_CODE_STOP
from imbue.mngr.api.connect import _build_ssh_activity_wrapper_script
from imbue.mngr.api.connect import _build_ssh_args
from imbue.mngr.api.connect import connect_to_agent
from imbue.mngr.api.data_types import ConnectionOptions
from imbue.mngr.config.data_types import AgentTypeConfig
from imbue.mngr.config.data_types import MngrContext
from imbue.mngr.errors import MngrError
from imbue.mngr.hosts.host import Host
from imbue.mngr.interfaces.data_types import PyinfraConnector
from imbue.mngr.primitives import AgentId
from imbue.mngr.primitives import AgentName
from imbue.mngr.primitives import AgentTypeName
from imbue.mngr.primitives import HostId
from imbue.mngr.providers.local.instance import LocalProviderInstance


def test_build_ssh_activity_wrapper_script_creates_activity_directory() -> None:
    """Test that the wrapper script creates the activity directory."""
    script = _build_ssh_activity_wrapper_script("mngr-test-session", Path("/home/user/.mngr"))

    assert "mkdir -p '/home/user/.mngr/activity'" in script


def test_build_ssh_activity_wrapper_script_writes_to_activity_file() -> None:
    """Test that the wrapper script writes to the activity/ssh file."""
    script = _build_ssh_activity_wrapper_script("mngr-test-session", Path("/home/user/.mngr"))

    assert "'/home/user/.mngr/activity/ssh'" in script


def test_build_ssh_activity_wrapper_script_attaches_to_tmux_session() -> None:
    """Test that the wrapper script attaches to the correct tmux session."""
    script = _build_ssh_activity_wrapper_script("mngr-my-agent", Path("/home/user/.mngr"))

    assert "tmux attach -t 'mngr-my-agent'" in script


def test_build_ssh_activity_wrapper_script_kills_activity_tracker_on_exit() -> None:
    """Test that the wrapper script kills the activity tracker when tmux exits."""
    script = _build_ssh_activity_wrapper_script("mngr-test", Path("/tmp/.mngr"))

    assert "kill $MNGR_ACTIVITY_PID" in script


def test_build_ssh_activity_wrapper_script_writes_json_with_time_and_pid() -> None:
    """Test that the activity file contains JSON with time and ssh_pid."""
    script = _build_ssh_activity_wrapper_script("mngr-test", Path("/tmp/.mngr"))

    # The script should write JSON with time and ssh_pid fields
    assert "time" in script
    assert "ssh_pid" in script
    assert "TIME_MS" in script


def test_build_ssh_activity_wrapper_script_handles_paths_with_spaces() -> None:
    """Test that the wrapper script handles paths with spaces correctly."""
    script = _build_ssh_activity_wrapper_script("mngr-test", Path("/home/user/my dir/.mngr"))

    # Paths should be quoted to handle spaces
    assert "'/home/user/my dir/.mngr/activity'" in script
    assert "'/home/user/my dir/.mngr/activity/ssh'" in script


def test_build_ssh_activity_wrapper_script_checks_for_signal_file() -> None:
    """Test that the wrapper script checks for the session-specific signal file."""
    script = _build_ssh_activity_wrapper_script("mngr-my-agent", Path("/home/user/.mngr"))

    assert "'/home/user/.mngr/signals/mngr-my-agent'" in script
    assert "SIGNAL_FILE=" in script


def test_build_ssh_activity_wrapper_script_exits_with_destroy_code_on_destroy_signal() -> None:
    """Test that the wrapper script exits with SIGNAL_EXIT_CODE_DESTROY when signal is 'destroy'."""
    script = _build_ssh_activity_wrapper_script("mngr-test", Path("/tmp/.mngr"))

    assert f"exit {SIGNAL_EXIT_CODE_DESTROY}" in script
    assert '"destroy"' in script


def test_build_ssh_activity_wrapper_script_exits_with_stop_code_on_stop_signal() -> None:
    """Test that the wrapper script exits with SIGNAL_EXIT_CODE_STOP when signal is 'stop'."""
    script = _build_ssh_activity_wrapper_script("mngr-test", Path("/tmp/.mngr"))

    assert f"exit {SIGNAL_EXIT_CODE_STOP}" in script
    assert '"stop"' in script


def test_build_ssh_activity_wrapper_script_removes_signal_file_after_reading() -> None:
    """Test that the wrapper script removes the signal file after reading it."""
    script = _build_ssh_activity_wrapper_script("mngr-test", Path("/tmp/.mngr"))

    assert 'rm -f "$SIGNAL_FILE"' in script


def test_build_ssh_activity_wrapper_script_signal_file_uses_session_name() -> None:
    """Test that the signal file path includes the session name for per-session signals."""
    script = _build_ssh_activity_wrapper_script("mngr-unique-session", Path("/data/.mngr"))

    assert "'/data/.mngr/signals/mngr-unique-session'" in script


# =========================================================================
# Tests for _build_ssh_args
# =========================================================================


def _create_pyinfra_ssh_host(
    hostname: str,
    data: dict[str, Any],
) -> PyinfraHost:
    """Create a real pyinfra Host with the given SSH connection data."""
    names_data = ([(hostname, data)], {})
    inventory = Inventory(names_data)
    state = PyinfraState(inventory=inventory)
    pyinfra_host = inventory.get_host(hostname)
    pyinfra_host.init(state)
    return pyinfra_host


def _make_ssh_host(
    local_provider: LocalProviderInstance,
    temp_mngr_ctx: MngrContext,
    hostname: str = "example.com",
    ssh_user: str | None = "ubuntu",
    ssh_port: int | None = 22,
    ssh_key: str | None = "/home/user/.ssh/id_rsa",
    ssh_known_hosts_file: str | None = None,
) -> Host:
    """Create a real Host with an SSH pyinfra connector for testing."""
    host_data: dict[str, Any] = {}
    if ssh_user is not None:
        host_data["ssh_user"] = ssh_user
    if ssh_port is not None:
        host_data["ssh_port"] = ssh_port
    if ssh_key is not None:
        host_data["ssh_key"] = ssh_key
    if ssh_known_hosts_file is not None:
        host_data["ssh_known_hosts_file"] = ssh_known_hosts_file

    pyinfra_host = _create_pyinfra_ssh_host(hostname, host_data)
    connector = PyinfraConnector(pyinfra_host)

    return Host(
        id=HostId(f"host-{uuid4().hex}"),
        connector=connector,
        provider_instance=local_provider,
        mngr_ctx=temp_mngr_ctx,
    )


def _make_remote_agent(
    host: Host,
    temp_mngr_ctx: MngrContext,
    agent_name: str = "test-agent",
) -> BaseAgent:
    """Create a real BaseAgent on a remote host for testing connect_to_agent."""
    return BaseAgent(
        id=AgentId(f"agent-{uuid4().hex}"),
        name=AgentName(agent_name),
        agent_type=AgentTypeName("test"),
        work_dir=Path("/tmp/work"),
        create_time=datetime.now(timezone.utc),
        host_id=host.id,
        mngr_ctx=temp_mngr_ctx,
        agent_config=AgentTypeConfig(),
        host=host,
    )


def test_build_ssh_args_with_known_hosts_file(
    local_provider: LocalProviderInstance,
    temp_mngr_ctx: MngrContext,
) -> None:
    """Test that _build_ssh_args uses StrictHostKeyChecking=yes with a known_hosts file."""
    host = _make_ssh_host(local_provider, temp_mngr_ctx, ssh_known_hosts_file="/tmp/known_hosts")
    opts = ConnectionOptions(is_unknown_host_allowed=False)

    args = _build_ssh_args(host, opts)

    assert "-i" in args
    assert "/home/user/.ssh/id_rsa" in args
    assert "-p" in args
    assert "22" in args
    assert "UserKnownHostsFile=/tmp/known_hosts" in " ".join(args)
    assert "StrictHostKeyChecking=yes" in " ".join(args)
    assert "ubuntu@example.com" in args


def test_build_ssh_args_with_allow_unknown_host(
    local_provider: LocalProviderInstance,
    temp_mngr_ctx: MngrContext,
) -> None:
    """Test that _build_ssh_args disables host key checking when allowed."""
    host = _make_ssh_host(local_provider, temp_mngr_ctx, ssh_known_hosts_file=None)
    opts = ConnectionOptions(is_unknown_host_allowed=True)

    args = _build_ssh_args(host, opts)

    assert "StrictHostKeyChecking=no" in " ".join(args)
    assert "UserKnownHostsFile=/dev/null" in " ".join(args)


def test_build_ssh_args_raises_without_known_hosts_or_allow_unknown(
    local_provider: LocalProviderInstance,
    temp_mngr_ctx: MngrContext,
) -> None:
    """Test that _build_ssh_args raises MngrError when no known_hosts and not allowing unknown."""
    host = _make_ssh_host(local_provider, temp_mngr_ctx, ssh_known_hosts_file=None)
    opts = ConnectionOptions(is_unknown_host_allowed=False)

    with pytest.raises(MngrError, match="known_hosts"):
        _build_ssh_args(host, opts)


def test_build_ssh_args_without_user(
    local_provider: LocalProviderInstance,
    temp_mngr_ctx: MngrContext,
) -> None:
    """Test that _build_ssh_args omits user@ when ssh_user is None."""
    host = _make_ssh_host(local_provider, temp_mngr_ctx, ssh_user=None, ssh_known_hosts_file="/tmp/known_hosts")
    opts = ConnectionOptions(is_unknown_host_allowed=False)

    args = _build_ssh_args(host, opts)

    # Should have bare hostname, not user@hostname
    assert "example.com" in args
    assert not any("@" in arg for arg in args)


def test_build_ssh_args_without_port(
    local_provider: LocalProviderInstance,
    temp_mngr_ctx: MngrContext,
) -> None:
    """Test that _build_ssh_args omits -p when ssh_port is None."""
    host = _make_ssh_host(local_provider, temp_mngr_ctx, ssh_port=None, ssh_known_hosts_file="/tmp/known_hosts")
    opts = ConnectionOptions(is_unknown_host_allowed=False)

    args = _build_ssh_args(host, opts)

    assert "-p" not in args


def test_build_ssh_args_without_key(
    local_provider: LocalProviderInstance,
    temp_mngr_ctx: MngrContext,
) -> None:
    """Test that _build_ssh_args omits -i when ssh_key is None."""
    host = _make_ssh_host(local_provider, temp_mngr_ctx, ssh_key=None, ssh_known_hosts_file="/tmp/known_hosts")
    opts = ConnectionOptions(is_unknown_host_allowed=False)

    args = _build_ssh_args(host, opts)

    assert "-i" not in args


def test_build_ssh_args_known_hosts_dev_null_treated_as_missing(
    local_provider: LocalProviderInstance,
    temp_mngr_ctx: MngrContext,
) -> None:
    """Test that /dev/null known_hosts is treated as no known_hosts file."""
    host = _make_ssh_host(local_provider, temp_mngr_ctx, ssh_known_hosts_file="/dev/null")
    opts = ConnectionOptions(is_unknown_host_allowed=True)

    args = _build_ssh_args(host, opts)

    # Should fall through to the allow_unknown_host branch
    assert "StrictHostKeyChecking=no" in " ".join(args)


# =========================================================================
# Tests for connect_to_agent remote exit code handling
# =========================================================================


def test_connect_to_agent_remote_destroy_signal(
    local_provider: LocalProviderInstance,
    temp_mngr_ctx: MngrContext,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test that connect_to_agent exec's into mngr destroy when SSH exits with SIGNAL_EXIT_CODE_DESTROY."""
    host = _make_ssh_host(local_provider, temp_mngr_ctx, ssh_known_hosts_file="/tmp/known_hosts")
    agent = _make_remote_agent(host, temp_mngr_ctx)
    opts = ConnectionOptions(is_unknown_host_allowed=False)
    expected_session = f"{temp_mngr_ctx.config.prefix}{agent.name}"

    execvp_calls: list[tuple[str, list[str]]] = []
    monkeypatch.setattr("imbue.mngr.api.connect.subprocess.call", lambda args: SIGNAL_EXIT_CODE_DESTROY)
    monkeypatch.setattr("imbue.mngr.api.connect.os.execvp", lambda cmd, args: execvp_calls.append((cmd, list(args))))

    connect_to_agent(agent, host, temp_mngr_ctx, opts)

    assert len(execvp_calls) == 1
    assert execvp_calls[0] == ("mngr", ["mngr", "destroy", "--session", expected_session, "-f"])


def test_connect_to_agent_remote_stop_signal(
    local_provider: LocalProviderInstance,
    temp_mngr_ctx: MngrContext,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test that connect_to_agent exec's into mngr stop when SSH exits with SIGNAL_EXIT_CODE_STOP."""
    host = _make_ssh_host(local_provider, temp_mngr_ctx, ssh_known_hosts_file="/tmp/known_hosts")
    agent = _make_remote_agent(host, temp_mngr_ctx)
    opts = ConnectionOptions(is_unknown_host_allowed=False)
    expected_session = f"{temp_mngr_ctx.config.prefix}{agent.name}"

    execvp_calls: list[tuple[str, list[str]]] = []
    monkeypatch.setattr("imbue.mngr.api.connect.subprocess.call", lambda args: SIGNAL_EXIT_CODE_STOP)
    monkeypatch.setattr("imbue.mngr.api.connect.os.execvp", lambda cmd, args: execvp_calls.append((cmd, list(args))))

    connect_to_agent(agent, host, temp_mngr_ctx, opts)

    assert len(execvp_calls) == 1
    assert execvp_calls[0] == ("mngr", ["mngr", "stop", "--session", expected_session])


def test_connect_to_agent_remote_normal_exit_no_action(
    local_provider: LocalProviderInstance,
    temp_mngr_ctx: MngrContext,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test that connect_to_agent does not exec into anything on normal SSH exit (code 0)."""
    host = _make_ssh_host(local_provider, temp_mngr_ctx, ssh_known_hosts_file="/tmp/known_hosts")
    agent = _make_remote_agent(host, temp_mngr_ctx)
    opts = ConnectionOptions(is_unknown_host_allowed=False)

    execvp_calls: list[tuple[str, list[str]]] = []
    monkeypatch.setattr("imbue.mngr.api.connect.subprocess.call", lambda args: 0)
    monkeypatch.setattr("imbue.mngr.api.connect.os.execvp", lambda cmd, args: execvp_calls.append((cmd, list(args))))

    connect_to_agent(agent, host, temp_mngr_ctx, opts)

    assert len(execvp_calls) == 0


def test_connect_to_agent_remote_unknown_exit_code_no_action(
    local_provider: LocalProviderInstance,
    temp_mngr_ctx: MngrContext,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test that connect_to_agent does not exec into anything on unexpected SSH exit codes."""
    host = _make_ssh_host(local_provider, temp_mngr_ctx, ssh_known_hosts_file="/tmp/known_hosts")
    agent = _make_remote_agent(host, temp_mngr_ctx)
    opts = ConnectionOptions(is_unknown_host_allowed=False)

    execvp_calls: list[tuple[str, list[str]]] = []
    monkeypatch.setattr("imbue.mngr.api.connect.subprocess.call", lambda args: 255)
    monkeypatch.setattr("imbue.mngr.api.connect.os.execvp", lambda cmd, args: execvp_calls.append((cmd, list(args))))

    connect_to_agent(agent, host, temp_mngr_ctx, opts)

    assert len(execvp_calls) == 0


def test_connect_to_agent_remote_uses_correct_session_name(
    local_provider: LocalProviderInstance,
    temp_mngr_ctx: MngrContext,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test that connect_to_agent constructs the session name from prefix + agent name."""
    host = _make_ssh_host(local_provider, temp_mngr_ctx, ssh_known_hosts_file="/tmp/known_hosts")
    agent = _make_remote_agent(host, temp_mngr_ctx, agent_name="my-agent")
    opts = ConnectionOptions(is_unknown_host_allowed=False)
    expected_session = f"{temp_mngr_ctx.config.prefix}my-agent"

    execvp_calls: list[tuple[str, list[str]]] = []
    monkeypatch.setattr("imbue.mngr.api.connect.subprocess.call", lambda args: SIGNAL_EXIT_CODE_DESTROY)
    monkeypatch.setattr("imbue.mngr.api.connect.os.execvp", lambda cmd, args: execvp_calls.append((cmd, list(args))))

    connect_to_agent(agent, host, temp_mngr_ctx, opts)

    assert len(execvp_calls) == 1
    assert execvp_calls[0] == ("mngr", ["mngr", "destroy", "--session", expected_session, "-f"])
