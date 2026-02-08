"""Unit tests for the connect API module."""

from pathlib import Path

from imbue.mngr.api.connect import SIGNAL_EXIT_CODE_DESTROY
from imbue.mngr.api.connect import SIGNAL_EXIT_CODE_STOP
from imbue.mngr.api.connect import _build_ssh_activity_wrapper_script


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
