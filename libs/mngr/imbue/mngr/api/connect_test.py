"""Unit tests for the connect API module."""

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock
from unittest.mock import patch

import pytest
from pyinfra.api import Host as PyinfraHost

from imbue.mngr.api.connect import _build_ssh_activity_wrapper_script
from imbue.mngr.api.connect import connect_to_agent
from imbue.mngr.api.data_types import ConnectionOptions
from imbue.mngr.errors import MngrError
from imbue.mngr.interfaces.data_types import PyinfraConnector


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


# Helper function to create a mock pyinfra host with configurable data
def _create_mock_pyinfra_host(
    name: str,
    ssh_user: str | None = None,
    ssh_port: int | None = None,
    ssh_key: str | None = None,
    ssh_known_hosts_file: str | None = None,
) -> PyinfraHost:
    """Create a mock PyinfraHost for testing SSH argument construction."""
    # Don't use spec - pyinfra Host has dynamic data attribute
    mock_host = MagicMock()
    mock_host.name = name

    # Set up the data.get() method to return the right values
    data_values: dict[str, Any] = {}
    if ssh_user is not None:
        data_values["ssh_user"] = ssh_user
    if ssh_port is not None:
        data_values["ssh_port"] = ssh_port
    if ssh_key is not None:
        data_values["ssh_key"] = ssh_key
    if ssh_known_hosts_file is not None:
        data_values["ssh_known_hosts_file"] = ssh_known_hosts_file

    mock_host.data = MagicMock()
    mock_host.data.get = lambda key, default=None: data_values.get(key, default)

    return mock_host


def _create_mock_host(
    pyinfra_host: PyinfraHost,
    is_local: bool = False,
    host_dir: Path = Path("/home/user/.mngr"),
) -> MagicMock:
    """Create a mock HostInterface with the given pyinfra host."""
    mock_host = MagicMock()
    mock_host.is_local = is_local
    mock_host.host_dir = host_dir

    # Create a mock connector with the pyinfra host
    mock_connector = MagicMock(spec=PyinfraConnector)
    mock_connector.host = pyinfra_host
    mock_host.connector = mock_connector

    return mock_host


def _create_mock_agent(name: str = "test-agent") -> MagicMock:
    """Create a mock AgentInterface."""
    mock_agent = MagicMock()
    mock_agent.name = name
    return mock_agent


def _create_mock_mngr_ctx(prefix: str = "mngr-") -> MagicMock:
    """Create a mock MngrContext."""
    mock_ctx = MagicMock()
    mock_ctx.config.prefix = prefix
    return mock_ctx


class TestConnectToAgentSshArgumentConstruction:
    """Tests for SSH argument construction in connect_to_agent."""

    def test_ssh_key_added_to_args_when_provided(self) -> None:
        """Test that SSH key is added with -i flag when provided."""
        pyinfra_host = _create_mock_pyinfra_host(
            name="example.com",
            ssh_key="/path/to/key",
            ssh_known_hosts_file="/path/to/known_hosts",
        )
        mock_host = _create_mock_host(pyinfra_host, is_local=False)
        mock_agent = _create_mock_agent()
        mock_ctx = _create_mock_mngr_ctx()
        connection_opts = ConnectionOptions()

        with patch("imbue.mngr.api.connect.os.execvp") as mock_execvp:
            connect_to_agent(mock_agent, mock_host, mock_ctx, connection_opts)

            # Verify execvp was called with ssh args containing the key
            call_args = mock_execvp.call_args
            # Second positional arg is the args list
            ssh_args = call_args[0][1]

            assert "-i" in ssh_args
            key_idx = ssh_args.index("-i")
            assert ssh_args[key_idx + 1] == "/path/to/key"

    def test_ssh_port_added_to_args_when_provided(self) -> None:
        """Test that SSH port is added with -p flag when provided."""
        pyinfra_host = _create_mock_pyinfra_host(
            name="example.com",
            ssh_port=2222,
            ssh_known_hosts_file="/path/to/known_hosts",
        )
        mock_host = _create_mock_host(pyinfra_host, is_local=False)
        mock_agent = _create_mock_agent()
        mock_ctx = _create_mock_mngr_ctx()
        connection_opts = ConnectionOptions()

        with patch("imbue.mngr.api.connect.os.execvp") as mock_execvp:
            connect_to_agent(mock_agent, mock_host, mock_ctx, connection_opts)

            call_args = mock_execvp.call_args
            ssh_args = call_args[0][1]

            assert "-p" in ssh_args
            port_idx = ssh_args.index("-p")
            assert ssh_args[port_idx + 1] == "2222"

    def test_known_hosts_file_added_when_provided(self) -> None:
        """Test that known_hosts file is added with UserKnownHostsFile option."""
        pyinfra_host = _create_mock_pyinfra_host(
            name="example.com",
            ssh_known_hosts_file="/custom/known_hosts",
        )
        mock_host = _create_mock_host(pyinfra_host, is_local=False)
        mock_agent = _create_mock_agent()
        mock_ctx = _create_mock_mngr_ctx()
        connection_opts = ConnectionOptions()

        with patch("imbue.mngr.api.connect.os.execvp") as mock_execvp:
            connect_to_agent(mock_agent, mock_host, mock_ctx, connection_opts)

            call_args = mock_execvp.call_args
            ssh_args = call_args[0][1]

            # Should contain UserKnownHostsFile option
            assert "-o" in ssh_args
            assert any("UserKnownHostsFile=/custom/known_hosts" in arg for arg in ssh_args)
            # Should also enable strict host checking
            assert any("StrictHostKeyChecking=yes" in arg for arg in ssh_args)

    def test_all_ssh_options_combined(self) -> None:
        """Test that all SSH options are combined correctly."""
        pyinfra_host = _create_mock_pyinfra_host(
            name="remote.host.com",
            ssh_user="deploy",
            ssh_port=2222,
            ssh_key="/home/user/.ssh/deploy_key",
            ssh_known_hosts_file="/home/user/.mngr/known_hosts",
        )
        mock_host = _create_mock_host(pyinfra_host, is_local=False)
        mock_agent = _create_mock_agent("my-agent")
        mock_ctx = _create_mock_mngr_ctx()
        connection_opts = ConnectionOptions()

        with patch("imbue.mngr.api.connect.os.execvp") as mock_execvp:
            connect_to_agent(mock_agent, mock_host, mock_ctx, connection_opts)

            call_args = mock_execvp.call_args
            ssh_args = call_args[0][1]

            # Check key
            assert "-i" in ssh_args
            key_idx = ssh_args.index("-i")
            assert ssh_args[key_idx + 1] == "/home/user/.ssh/deploy_key"

            # Check port
            assert "-p" in ssh_args
            port_idx = ssh_args.index("-p")
            assert ssh_args[port_idx + 1] == "2222"

            # Check known_hosts
            assert any("UserKnownHostsFile=/home/user/.mngr/known_hosts" in arg for arg in ssh_args)

            # Check user@host format
            assert "deploy@remote.host.com" in ssh_args


class TestConnectToAgentSecurityValidation:
    """Tests for security validation in connect_to_agent."""

    def test_raises_error_without_known_hosts_or_allow_unknown_flag(self) -> None:
        """Test that connection requires either known_hosts or allow-unknown-host flag."""
        pyinfra_host = _create_mock_pyinfra_host(
            name="example.com",
            # No ssh_known_hosts_file provided
        )
        mock_host = _create_mock_host(pyinfra_host, is_local=False)
        mock_agent = _create_mock_agent()
        mock_ctx = _create_mock_mngr_ctx()
        # is_unknown_host_allowed defaults to False
        connection_opts = ConnectionOptions()

        with pytest.raises(MngrError) as exc_info:
            connect_to_agent(mock_agent, mock_host, mock_ctx, connection_opts)

        assert "known_hosts" in str(exc_info.value.message).lower()

    def test_allows_connection_with_known_hosts_file(self) -> None:
        """Test that connection is allowed when known_hosts file is provided."""
        pyinfra_host = _create_mock_pyinfra_host(
            name="example.com",
            ssh_known_hosts_file="/path/to/known_hosts",
        )
        mock_host = _create_mock_host(pyinfra_host, is_local=False)
        mock_agent = _create_mock_agent()
        mock_ctx = _create_mock_mngr_ctx()
        connection_opts = ConnectionOptions()

        with patch("imbue.mngr.api.connect.os.execvp") as mock_execvp:
            # Should not raise
            connect_to_agent(mock_agent, mock_host, mock_ctx, connection_opts)
            mock_execvp.assert_called_once()

    def test_allows_connection_with_allow_unknown_host_flag(self) -> None:
        """Test that connection is allowed when allow-unknown-host flag is set."""
        pyinfra_host = _create_mock_pyinfra_host(
            name="example.com",
            # No ssh_known_hosts_file
        )
        mock_host = _create_mock_host(pyinfra_host, is_local=False)
        mock_agent = _create_mock_agent()
        mock_ctx = _create_mock_mngr_ctx()
        connection_opts = ConnectionOptions(is_unknown_host_allowed=True)

        with patch("imbue.mngr.api.connect.os.execvp") as mock_execvp:
            # Should not raise
            connect_to_agent(mock_agent, mock_host, mock_ctx, connection_opts)

            call_args = mock_execvp.call_args
            ssh_args = call_args[0][1]

            # Should disable strict host checking
            assert any("StrictHostKeyChecking=no" in arg for arg in ssh_args)
            assert any("UserKnownHostsFile=/dev/null" in arg for arg in ssh_args)

    def test_dev_null_known_hosts_treated_as_no_known_hosts(self) -> None:
        """Test that /dev/null known_hosts file is treated as no known_hosts."""
        pyinfra_host = _create_mock_pyinfra_host(
            name="example.com",
            ssh_known_hosts_file="/dev/null",
        )
        mock_host = _create_mock_host(pyinfra_host, is_local=False)
        mock_agent = _create_mock_agent()
        mock_ctx = _create_mock_mngr_ctx()
        # is_unknown_host_allowed defaults to False
        connection_opts = ConnectionOptions()

        # Should raise because /dev/null is not a valid known_hosts file
        with pytest.raises(MngrError):
            connect_to_agent(mock_agent, mock_host, mock_ctx, connection_opts)


class TestConnectToAgentUserHandling:
    """Tests for SSH user handling in connect_to_agent."""

    def test_user_at_host_format_when_user_provided(self) -> None:
        """Test that user@host format is used when SSH user is provided."""
        pyinfra_host = _create_mock_pyinfra_host(
            name="example.com",
            ssh_user="admin",
            ssh_known_hosts_file="/path/to/known_hosts",
        )
        mock_host = _create_mock_host(pyinfra_host, is_local=False)
        mock_agent = _create_mock_agent()
        mock_ctx = _create_mock_mngr_ctx()
        connection_opts = ConnectionOptions()

        with patch("imbue.mngr.api.connect.os.execvp") as mock_execvp:
            connect_to_agent(mock_agent, mock_host, mock_ctx, connection_opts)

            call_args = mock_execvp.call_args
            ssh_args = call_args[0][1]

            # Should contain user@host
            assert "admin@example.com" in ssh_args

    def test_host_only_when_no_user_provided(self) -> None:
        """Test that only host is used when no SSH user is provided."""
        pyinfra_host = _create_mock_pyinfra_host(
            name="example.com",
            # No ssh_user
            ssh_known_hosts_file="/path/to/known_hosts",
        )
        mock_host = _create_mock_host(pyinfra_host, is_local=False)
        mock_agent = _create_mock_agent()
        mock_ctx = _create_mock_mngr_ctx()
        connection_opts = ConnectionOptions()

        with patch("imbue.mngr.api.connect.os.execvp") as mock_execvp:
            connect_to_agent(mock_agent, mock_host, mock_ctx, connection_opts)

            call_args = mock_execvp.call_args
            ssh_args = call_args[0][1]

            # Should contain just host, not user@host
            assert "example.com" in ssh_args
            # Make sure it's not in user@host format
            assert not any("@example.com" in arg for arg in ssh_args)


class TestConnectToAgentLocalHost:
    """Tests for local host connection in connect_to_agent."""

    def test_local_host_uses_tmux_attach(self) -> None:
        """Test that local hosts use tmux attach directly."""
        mock_host = _create_mock_host(
            _create_mock_pyinfra_host(name="localhost"),
            is_local=True,
        )
        mock_agent = _create_mock_agent("test-agent")
        mock_ctx = _create_mock_mngr_ctx(prefix="mngr-")
        connection_opts = ConnectionOptions()

        with patch("imbue.mngr.api.connect.os.execvp") as mock_execvp:
            connect_to_agent(mock_agent, mock_host, mock_ctx, connection_opts)

            # Should call tmux, not ssh
            mock_execvp.assert_called_once()
            call_args = mock_execvp.call_args
            assert call_args[0][0] == "tmux"
            tmux_args = call_args[0][1]
            assert "attach" in tmux_args
            assert "-t" in tmux_args
            assert "mngr-test-agent" in tmux_args
