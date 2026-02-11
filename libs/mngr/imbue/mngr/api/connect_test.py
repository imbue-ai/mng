"""Unit tests for the connect API module."""

from pathlib import Path

import pytest
from pyinfra.api import Host as PyinfraHost
from pyinfra.api import State as PyinfraState
from pyinfra.api.inventory import Inventory

from imbue.mngr.api.connect import SIGNAL_EXIT_CODE_DESTROY
from imbue.mngr.api.connect import SIGNAL_EXIT_CODE_STOP
from imbue.mngr.api.connect import _build_ssh_activity_wrapper_script
from imbue.mngr.api.connect import _build_ssh_args
from imbue.mngr.api.connect import _determine_post_disconnect_action
from imbue.mngr.api.data_types import ConnectionOptions
from imbue.mngr.errors import MngrError
from imbue.mngr.hosts.host import Host
from imbue.mngr.interfaces.data_types import PyinfraConnector
from imbue.mngr.primitives import HostId


def test_build_ssh_activity_wrapper_script_creates_activity_directory() -> None:
    script = _build_ssh_activity_wrapper_script("mngr-test-session", Path("/home/user/.mngr"))

    assert "mkdir -p '/home/user/.mngr/activity'" in script


def test_build_ssh_activity_wrapper_script_writes_to_activity_file() -> None:
    script = _build_ssh_activity_wrapper_script("mngr-test-session", Path("/home/user/.mngr"))

    assert "'/home/user/.mngr/activity/ssh'" in script


def test_build_ssh_activity_wrapper_script_attaches_to_tmux_session() -> None:
    script = _build_ssh_activity_wrapper_script("mngr-my-agent", Path("/home/user/.mngr"))

    assert "tmux attach -t 'mngr-my-agent'" in script


def test_build_ssh_activity_wrapper_script_kills_activity_tracker_on_exit() -> None:
    script = _build_ssh_activity_wrapper_script("mngr-test", Path("/tmp/.mngr"))

    assert "kill $MNGR_ACTIVITY_PID" in script


def test_build_ssh_activity_wrapper_script_writes_json_with_time_and_pid() -> None:
    script = _build_ssh_activity_wrapper_script("mngr-test", Path("/tmp/.mngr"))

    # The script should write JSON with time and ssh_pid fields
    assert "time" in script
    assert "ssh_pid" in script
    assert "TIME_MS" in script


def test_build_ssh_activity_wrapper_script_handles_paths_with_spaces() -> None:
    script = _build_ssh_activity_wrapper_script("mngr-test", Path("/home/user/my dir/.mngr"))

    # Paths should be quoted to handle spaces
    assert "'/home/user/my dir/.mngr/activity'" in script
    assert "'/home/user/my dir/.mngr/activity/ssh'" in script


def test_build_ssh_activity_wrapper_script_checks_for_signal_file() -> None:
    script = _build_ssh_activity_wrapper_script("mngr-my-agent", Path("/home/user/.mngr"))

    assert "'/home/user/.mngr/signals/mngr-my-agent'" in script
    assert "SIGNAL_FILE=" in script


def test_build_ssh_activity_wrapper_script_exits_with_destroy_code_on_destroy_signal() -> None:
    script = _build_ssh_activity_wrapper_script("mngr-test", Path("/tmp/.mngr"))

    assert f"exit {SIGNAL_EXIT_CODE_DESTROY}" in script
    assert '"destroy"' in script


def test_build_ssh_activity_wrapper_script_exits_with_stop_code_on_stop_signal() -> None:
    script = _build_ssh_activity_wrapper_script("mngr-test", Path("/tmp/.mngr"))

    assert f"exit {SIGNAL_EXIT_CODE_STOP}" in script
    assert '"stop"' in script


def test_build_ssh_activity_wrapper_script_removes_signal_file_after_reading() -> None:
    script = _build_ssh_activity_wrapper_script("mngr-test", Path("/tmp/.mngr"))

    assert 'rm -f "$SIGNAL_FILE"' in script


def test_build_ssh_activity_wrapper_script_signal_file_uses_session_name() -> None:
    script = _build_ssh_activity_wrapper_script("mngr-unique-session", Path("/data/.mngr"))

    assert "'/data/.mngr/signals/mngr-unique-session'" in script


# =========================================================================
# Tests for _build_ssh_args
# =========================================================================


def _create_ssh_pyinfra_host(
    hostname: str,
    ssh_user: str | None,
    ssh_port: int | None,
    ssh_key: str | None,
    ssh_known_hosts_file: str | None,
) -> PyinfraHost:
    """Create a real pyinfra Host with SSH connection data."""
    host_data: dict[str, str | int] = {}
    if ssh_user is not None:
        host_data["ssh_user"] = ssh_user
    if ssh_port is not None:
        host_data["ssh_port"] = ssh_port
    if ssh_key is not None:
        host_data["ssh_key"] = ssh_key
    if ssh_known_hosts_file is not None:
        host_data["ssh_known_hosts_file"] = ssh_known_hosts_file

    names_data = ([(hostname, host_data)], {})
    inventory = Inventory(names_data)
    state = PyinfraState(inventory=inventory)
    pyinfra_host = inventory.get_host(hostname)
    pyinfra_host.init(state)
    return pyinfra_host


def _make_ssh_host(
    hostname: str = "example.com",
    ssh_user: str | None = "ubuntu",
    ssh_port: int | None = 22,
    ssh_key: str | None = "/home/user/.ssh/id_rsa",
    ssh_known_hosts_file: str | None = None,
) -> Host:
    """Create a Host with a real PyinfraConnector backed by a real pyinfra Host."""
    pyinfra_host = _create_ssh_pyinfra_host(
        hostname=hostname,
        ssh_user=ssh_user,
        ssh_port=ssh_port,
        ssh_key=ssh_key,
        ssh_known_hosts_file=ssh_known_hosts_file,
    )
    connector = PyinfraConnector(pyinfra_host)
    return Host.model_construct(
        id=HostId.generate(),
        connector=connector,
    )


def test_build_ssh_args_with_known_hosts_file() -> None:
    host = _make_ssh_host(ssh_known_hosts_file="/tmp/known_hosts")
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
    host = _make_ssh_host(ssh_known_hosts_file=None)
    opts = ConnectionOptions(is_unknown_host_allowed=True)

    args = _build_ssh_args(host, opts)

    assert "StrictHostKeyChecking=no" in " ".join(args)
    assert "UserKnownHostsFile=/dev/null" in " ".join(args)


def test_build_ssh_args_raises_without_known_hosts_or_allow_unknown() -> None:
    host = _make_ssh_host(ssh_known_hosts_file=None)
    opts = ConnectionOptions(is_unknown_host_allowed=False)

    with pytest.raises(MngrError, match="known_hosts"):
        _build_ssh_args(host, opts)


def test_build_ssh_args_without_user() -> None:
    host = _make_ssh_host(ssh_user=None, ssh_known_hosts_file="/tmp/known_hosts")
    opts = ConnectionOptions(is_unknown_host_allowed=False)

    args = _build_ssh_args(host, opts)

    # Should have bare hostname, not user@hostname
    assert "example.com" in args
    assert not any("@" in arg for arg in args)


def test_build_ssh_args_without_port() -> None:
    host = _make_ssh_host(ssh_port=None, ssh_known_hosts_file="/tmp/known_hosts")
    opts = ConnectionOptions(is_unknown_host_allowed=False)

    args = _build_ssh_args(host, opts)

    assert "-p" not in args


def test_build_ssh_args_without_key() -> None:
    host = _make_ssh_host(ssh_key=None, ssh_known_hosts_file="/tmp/known_hosts")
    opts = ConnectionOptions(is_unknown_host_allowed=False)

    args = _build_ssh_args(host, opts)

    assert "-i" not in args


def test_build_ssh_args_known_hosts_dev_null_treated_as_missing() -> None:
    host = _make_ssh_host(ssh_known_hosts_file="/dev/null")
    opts = ConnectionOptions(is_unknown_host_allowed=True)

    args = _build_ssh_args(host, opts)

    # Should fall through to the allow_unknown_host branch
    assert "StrictHostKeyChecking=no" in " ".join(args)


# =========================================================================
# Tests for _determine_post_disconnect_action
# =========================================================================


def test_determine_post_disconnect_action_destroy_signal() -> None:
    action = _determine_post_disconnect_action(SIGNAL_EXIT_CODE_DESTROY, "mngr-test-agent")

    assert action is not None
    executable, argv = action
    assert executable == "mngr"
    assert argv == ["mngr", "destroy", "--session", "mngr-test-agent", "-f"]


def test_determine_post_disconnect_action_stop_signal() -> None:
    action = _determine_post_disconnect_action(SIGNAL_EXIT_CODE_STOP, "mngr-test-agent")

    assert action is not None
    executable, argv = action
    assert executable == "mngr"
    assert argv == ["mngr", "stop", "--session", "mngr-test-agent"]


def test_determine_post_disconnect_action_normal_exit_returns_none() -> None:
    action = _determine_post_disconnect_action(0, "mngr-test-agent")

    assert action is None


def test_determine_post_disconnect_action_unknown_exit_code_returns_none() -> None:
    action = _determine_post_disconnect_action(255, "mngr-test-agent")

    assert action is None


def test_determine_post_disconnect_action_uses_session_name_in_args() -> None:
    action = _determine_post_disconnect_action(SIGNAL_EXIT_CODE_DESTROY, "custom-my-agent")

    assert action is not None
    _, argv = action
    assert argv == ["mngr", "destroy", "--session", "custom-my-agent", "-f"]
