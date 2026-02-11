# FIXME0: Replace usages of MagicMock, Mock, patch, etc with better testing patterns like we did in create_test.py
"""Unit tests for the connect API module."""

import shlex
from pathlib import Path
from unittest.mock import MagicMock
from unittest.mock import patch

import pytest

from imbue.mngr.api.connect import SIGNAL_EXIT_CODE_DESTROY
from imbue.mngr.api.connect import SIGNAL_EXIT_CODE_STOP
from imbue.mngr.api.connect import _build_ssh_activity_wrapper_script
from imbue.mngr.api.connect import _build_ssh_args
from imbue.mngr.api.connect import connect_to_agent
from imbue.mngr.api.data_types import ConnectionOptions
from imbue.mngr.errors import MngrError


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


def _make_mock_host(
    hostname: str = "example.com",
    ssh_user: str | None = "ubuntu",
    ssh_port: int | None = 22,
    ssh_key: str | None = "/home/user/.ssh/id_rsa",
    ssh_known_hosts_file: str | None = None,
) -> MagicMock:
    """Create a mock OnlineHostInterface with pyinfra connector data for SSH tests."""
    mock_host = MagicMock()
    mock_pyinfra_host = MagicMock()
    mock_pyinfra_host.name = hostname
    mock_pyinfra_host.data.get = lambda key, default=None: {
        "ssh_user": ssh_user,
        "ssh_port": ssh_port,
        "ssh_key": ssh_key,
        "ssh_known_hosts_file": ssh_known_hosts_file,
    }.get(key, default)
    mock_host.connector.host = mock_pyinfra_host
    return mock_host


def test_build_ssh_args_with_known_hosts_file() -> None:
    """Test that _build_ssh_args uses StrictHostKeyChecking=yes with a known_hosts file."""
    host = _make_mock_host(ssh_known_hosts_file="/tmp/known_hosts")
    opts = ConnectionOptions(is_unknown_host_allowed=False)

    args = _build_ssh_args(host, opts)

    assert "-i" in args
    assert "/home/user/.ssh/id_rsa" in args
    assert "-p" in args
    assert "22" in args
    assert "UserKnownHostsFile=/tmp/known_hosts" in " ".join(args)
    assert "StrictHostKeyChecking=yes" in " ".join(args)
    assert "ubuntu@example.com" in args


def test_build_ssh_args_with_allow_unknown_host() -> None:
    """Test that _build_ssh_args disables host key checking when allowed."""
    host = _make_mock_host(ssh_known_hosts_file=None)
    opts = ConnectionOptions(is_unknown_host_allowed=True)

    args = _build_ssh_args(host, opts)

    assert "StrictHostKeyChecking=no" in " ".join(args)
    assert "UserKnownHostsFile=/dev/null" in " ".join(args)


def test_build_ssh_args_raises_without_known_hosts_or_allow_unknown() -> None:
    """Test that _build_ssh_args raises MngrError when no known_hosts and not allowing unknown."""
    host = _make_mock_host(ssh_known_hosts_file=None)
    opts = ConnectionOptions(is_unknown_host_allowed=False)

    with pytest.raises(MngrError, match="known_hosts"):
        _build_ssh_args(host, opts)


def test_build_ssh_args_without_user() -> None:
    """Test that _build_ssh_args omits user@ when ssh_user is None."""
    host = _make_mock_host(ssh_user=None, ssh_known_hosts_file="/tmp/known_hosts")
    opts = ConnectionOptions(is_unknown_host_allowed=False)

    args = _build_ssh_args(host, opts)

    # Should have bare hostname, not user@hostname
    assert "example.com" in args
    assert not any("@" in arg for arg in args)


def test_build_ssh_args_without_port() -> None:
    """Test that _build_ssh_args omits -p when ssh_port is None."""
    host = _make_mock_host(ssh_port=None, ssh_known_hosts_file="/tmp/known_hosts")
    opts = ConnectionOptions(is_unknown_host_allowed=False)

    args = _build_ssh_args(host, opts)

    assert "-p" not in args


def test_build_ssh_args_without_key() -> None:
    """Test that _build_ssh_args omits -i when ssh_key is None."""
    host = _make_mock_host(ssh_key=None, ssh_known_hosts_file="/tmp/known_hosts")
    opts = ConnectionOptions(is_unknown_host_allowed=False)

    args = _build_ssh_args(host, opts)

    assert "-i" not in args


def test_build_ssh_args_known_hosts_dev_null_treated_as_missing() -> None:
    """Test that /dev/null known_hosts is treated as no known_hosts file."""
    host = _make_mock_host(ssh_known_hosts_file="/dev/null")
    opts = ConnectionOptions(is_unknown_host_allowed=True)

    args = _build_ssh_args(host, opts)

    # Should fall through to the allow_unknown_host branch
    assert "StrictHostKeyChecking=no" in " ".join(args)


# =========================================================================
# Tests for connect_to_agent remote exit code handling
# =========================================================================


def _make_mock_remote_host_and_agent(
    prefix: str = "mngr-",
    agent_name: str = "test-agent",
) -> tuple[MagicMock, MagicMock, MagicMock]:
    """Create mock agent, host, and mngr_ctx for testing connect_to_agent.

    Returns (agent, host, mngr_ctx).
    """
    agent = MagicMock()
    agent.name = agent_name

    host = _make_mock_host(ssh_known_hosts_file="/tmp/known_hosts")
    host.is_local = False
    host.host_dir = Path("/remote/.mngr")

    mngr_ctx = MagicMock()
    mngr_ctx.config.prefix = prefix

    return agent, host, mngr_ctx


@patch("imbue.mngr.api.connect.os.execvp")
@patch("imbue.mngr.api.connect.subprocess.call")
def test_connect_to_agent_remote_destroy_signal(mock_call: MagicMock, mock_execvp: MagicMock) -> None:
    """Test that connect_to_agent exec's into mngr destroy when SSH exits with SIGNAL_EXIT_CODE_DESTROY."""
    agent, host, mngr_ctx = _make_mock_remote_host_and_agent()
    opts = ConnectionOptions(is_unknown_host_allowed=False)
    mock_call.return_value = SIGNAL_EXIT_CODE_DESTROY

    connect_to_agent(agent, host, mngr_ctx, opts)

    mock_call.assert_called_once()
    mock_execvp.assert_called_once_with("mngr", ["mngr", "destroy", "--session", "mngr-test-agent", "-f"])


@patch("imbue.mngr.api.connect.os.execvp")
@patch("imbue.mngr.api.connect.subprocess.call")
def test_connect_to_agent_remote_stop_signal(mock_call: MagicMock, mock_execvp: MagicMock) -> None:
    """Test that connect_to_agent exec's into mngr stop when SSH exits with SIGNAL_EXIT_CODE_STOP."""
    agent, host, mngr_ctx = _make_mock_remote_host_and_agent()
    opts = ConnectionOptions(is_unknown_host_allowed=False)
    mock_call.return_value = SIGNAL_EXIT_CODE_STOP

    connect_to_agent(agent, host, mngr_ctx, opts)

    mock_call.assert_called_once()
    mock_execvp.assert_called_once_with("mngr", ["mngr", "stop", "--session", "mngr-test-agent"])


@patch("imbue.mngr.api.connect.os.execvp")
@patch("imbue.mngr.api.connect.subprocess.call")
def test_connect_to_agent_remote_normal_exit_no_action(mock_call: MagicMock, mock_execvp: MagicMock) -> None:
    """Test that connect_to_agent does not exec into anything on normal SSH exit (code 0)."""
    agent, host, mngr_ctx = _make_mock_remote_host_and_agent()
    opts = ConnectionOptions(is_unknown_host_allowed=False)
    mock_call.return_value = 0

    connect_to_agent(agent, host, mngr_ctx, opts)

    mock_call.assert_called_once()
    mock_execvp.assert_not_called()


@patch("imbue.mngr.api.connect.os.execvp")
@patch("imbue.mngr.api.connect.subprocess.call")
def test_connect_to_agent_remote_unknown_exit_code_no_action(mock_call: MagicMock, mock_execvp: MagicMock) -> None:
    """Test that connect_to_agent does not exec into anything on unexpected SSH exit codes."""
    agent, host, mngr_ctx = _make_mock_remote_host_and_agent()
    opts = ConnectionOptions(is_unknown_host_allowed=False)
    mock_call.return_value = 255

    connect_to_agent(agent, host, mngr_ctx, opts)

    mock_call.assert_called_once()
    mock_execvp.assert_not_called()


@patch("imbue.mngr.api.connect.os.execvp")
@patch("imbue.mngr.api.connect.subprocess.call")
def test_connect_to_agent_remote_uses_correct_session_name(mock_call: MagicMock, mock_execvp: MagicMock) -> None:
    """Test that connect_to_agent constructs the session name from prefix + agent name."""
    agent, host, mngr_ctx = _make_mock_remote_host_and_agent(prefix="custom-", agent_name="my-agent")
    opts = ConnectionOptions(is_unknown_host_allowed=False)
    mock_call.return_value = SIGNAL_EXIT_CODE_DESTROY

    connect_to_agent(agent, host, mngr_ctx, opts)

    mock_execvp.assert_called_once_with("mngr", ["mngr", "destroy", "--session", "custom-my-agent", "-f"])


def test_ssh_wrapper_script_is_correctly_quoted_for_bash_c() -> None:
    """Verify the wrapper script survives shell parsing as a single bash -c argument.

    SSH concatenates remote command arguments with spaces, so the wrapper must
    be shell-quoted into a single 'bash -c <quoted_script>' string. Otherwise
    bash -c only receives the first word (e.g. 'mkdir'), causing errors like
    'mkdir: missing operand'.
    """
    wrapper_script = _build_ssh_activity_wrapper_script("mngr-test", Path("/mngr"))
    remote_command = "bash -c " + shlex.quote(wrapper_script)

    # When the remote shell parses this command, bash should receive
    # the full wrapper script as a single -c argument
    parsed = shlex.split(remote_command)
    assert parsed == ["bash", "-c", wrapper_script]
