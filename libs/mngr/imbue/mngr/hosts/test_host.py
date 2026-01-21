"""Integration tests for Host implementation.

Note: Unit tests for env file parsing are in utils/env_utils_test.py
"""

import fcntl
import json
import stat
import subprocess
import threading
from pathlib import Path

import pluggy
import pytest
from pyinfra.api.command import StringCommand

from imbue.mngr import hookimpl
from imbue.mngr.config.data_types import EnvVar
from imbue.mngr.config.data_types import MngrConfig
from imbue.mngr.config.data_types import MngrContext
from imbue.mngr.errors import LockNotHeldError
from imbue.mngr.errors import MngrError
from imbue.mngr.hosts.host import Host
from imbue.mngr.interfaces.agent import AgentInterface
from imbue.mngr.interfaces.data_types import ActivityConfig
from imbue.mngr.interfaces.host import AgentEnvironmentOptions
from imbue.mngr.interfaces.host import AgentProvisioningOptions
from imbue.mngr.interfaces.host import CreateAgentOptions
from imbue.mngr.interfaces.host import FileModificationSpec
from imbue.mngr.interfaces.host import NamedCommand
from imbue.mngr.interfaces.host import UploadFileSpec
from imbue.mngr.primitives import ActivitySource
from imbue.mngr.primitives import AgentName
from imbue.mngr.primitives import AgentTypeName
from imbue.mngr.primitives import CommandString
from imbue.mngr.primitives import HostName
from imbue.mngr.primitives import HostState
from imbue.mngr.primitives import IdleMode
from imbue.mngr.primitives import ProviderInstanceName
from imbue.mngr.providers.local.instance import LocalProviderInstance
from imbue.mngr.utils.testing import wait_for


@pytest.fixture
def host_with_temp_dir(local_provider: LocalProviderInstance, temp_host_dir: Path) -> tuple[Host, Path]:
    """Create a Host using the local provider and its temp directory."""
    host = local_provider.create_host(HostName("test"))
    assert isinstance(host, Host)
    return host, temp_host_dir


# =============================================================================
# Run Shell Command Tests
# =============================================================================


def test_run_simple_command(host_with_temp_dir: tuple[Host, Path]) -> None:
    """Test executing a simple command."""
    host, _ = host_with_temp_dir
    success, output = host._run_shell_command(StringCommand("echo hello"))
    assert success is True
    assert output.stdout == "hello"
    assert output.stderr == ""


def test_run_command_with_failure(host_with_temp_dir: tuple[Host, Path]) -> None:
    """Test command with non-zero exit code returns success=False."""
    host, _ = host_with_temp_dir
    success, output = host._run_shell_command(StringCommand("exit 42"))
    assert success is False


def test_run_command_with_stderr(host_with_temp_dir: tuple[Host, Path]) -> None:
    """Test command that writes to stderr."""
    host, _ = host_with_temp_dir
    success, output = host._run_shell_command(StringCommand("echo error >&2"))
    assert success is True
    assert output.stderr == "error"


def test_run_command_with_chdir(host_with_temp_dir: tuple[Host, Path]) -> None:
    """Test command with working directory using _chdir."""
    host, temp_dir = host_with_temp_dir
    success, output = host._run_shell_command(StringCommand("pwd"), _chdir=str(temp_dir))
    assert success is True
    assert output.stdout == str(temp_dir)


def test_run_command_with_env(host_with_temp_dir: tuple[Host, Path]) -> None:
    """Test command with environment variables using _env."""
    host, _ = host_with_temp_dir
    success, output = host._run_shell_command(
        StringCommand("echo $MY_TEST_VAR"),
        _env={"MY_TEST_VAR": "test_value"},
    )
    assert success is True
    assert output.stdout == "test_value"


def test_run_command_captures_multiline_output(host_with_temp_dir: tuple[Host, Path]) -> None:
    """Test that multiline output is captured correctly."""
    host, _ = host_with_temp_dir
    success, output = host._run_shell_command(StringCommand("printf 'line1\\nline2\\nline3'"))
    assert success is True
    assert "line1" in output.stdout
    assert "line2" in output.stdout
    assert "line3" in output.stdout


# =============================================================================
# Read File Tests (Bytes)
# =============================================================================


def test_read_file_returns_bytes(host_with_temp_dir: tuple[Host, Path]) -> None:
    """Test that read_file returns bytes."""
    host, temp_dir = host_with_temp_dir
    test_file = temp_dir / "test.bin"
    test_file.write_bytes(b"binary content")
    content = host.read_file(test_file)
    assert content == b"binary content"
    assert isinstance(content, bytes)


def test_read_nonexistent_file_raises(host_with_temp_dir: tuple[Host, Path]) -> None:
    """Test that reading a nonexistent file raises FileNotFoundError."""
    host, _ = host_with_temp_dir
    with pytest.raises(FileNotFoundError):
        host.read_file(Path("/nonexistent/file/path/12345.txt"))


# =============================================================================
# Write File Tests (Bytes)
# =============================================================================


def test_write_file_accepts_bytes(host_with_temp_dir: tuple[Host, Path]) -> None:
    """Test that write_file accepts bytes."""
    host, temp_dir = host_with_temp_dir
    file_path = temp_dir / "new_test.bin"
    host.write_file(file_path, b"binary content")
    assert file_path.read_bytes() == b"binary content"


def test_write_file_creates_directories(host_with_temp_dir: tuple[Host, Path]) -> None:
    """Test that write_file creates parent directories."""
    host, temp_dir = host_with_temp_dir
    file_path = temp_dir / "subdir" / "nested" / "test.bin"
    host.write_file(file_path, b"content")
    assert file_path.read_bytes() == b"content"


def test_write_file_with_mode(host_with_temp_dir: tuple[Host, Path]) -> None:
    """Test writing a file with specific permissions."""
    host, temp_dir = host_with_temp_dir
    file_path = temp_dir / "test.sh"
    host.write_file(file_path, b"#!/bin/bash\necho hello", mode="755")
    file_stat = file_path.stat()
    assert file_stat.st_mode & stat.S_IXUSR


# =============================================================================
# Read Text File Tests
# =============================================================================


def test_read_text_file_returns_string(host_with_temp_dir: tuple[Host, Path]) -> None:
    """Test that read_text_file returns a string."""
    host, temp_dir = host_with_temp_dir
    test_file = temp_dir / "test.txt"
    test_file.write_text("test content")
    content = host.read_text_file(test_file)
    assert content == "test content"
    assert isinstance(content, str)


def test_read_text_file_with_unicode(host_with_temp_dir: tuple[Host, Path]) -> None:
    """Test reading a file with unicode content."""
    host, temp_dir = host_with_temp_dir
    test_file = temp_dir / "unicode.txt"
    test_file.write_text("Hello World! Special chars: plus plus")
    content = host.read_text_file(test_file)
    assert "Hello World" in content


# =============================================================================
# Write Text File Tests
# =============================================================================


def test_write_text_file_accepts_string(host_with_temp_dir: tuple[Host, Path]) -> None:
    """Test that write_text_file accepts a string."""
    host, temp_dir = host_with_temp_dir
    file_path = temp_dir / "new_test.txt"
    host.write_text_file(file_path, "test content")
    assert file_path.read_text() == "test content"


def test_write_text_file_overwrites_existing(host_with_temp_dir: tuple[Host, Path]) -> None:
    """Test that write_text_file overwrites existing content."""
    host, temp_dir = host_with_temp_dir
    file_path = temp_dir / "existing.txt"
    file_path.write_text("old content")
    host.write_text_file(file_path, "new content")
    assert file_path.read_text() == "new content"


def test_write_text_file_with_mode(host_with_temp_dir: tuple[Host, Path]) -> None:
    """Test writing a text file with specific permissions."""
    host, temp_dir = host_with_temp_dir
    file_path = temp_dir / "text_test.sh"
    host.write_text_file(file_path, "#!/bin/bash\necho hello", mode="755")
    file_stat = file_path.stat()
    assert file_stat.st_mode & stat.S_IXUSR


# =============================================================================
# Activity Configuration Tests
# =============================================================================


def test_get_default_activity_config(host_with_temp_dir: tuple[Host, Path]) -> None:
    """Test getting default activity config when no file exists."""
    host, _ = host_with_temp_dir
    config = host.get_activity_config()
    assert config.idle_mode == IdleMode.AGENT
    assert config.idle_timeout_seconds == 3600
    assert len(config.activity_sources) > 0


def test_set_and_get_activity_config(host_with_temp_dir: tuple[Host, Path]) -> None:
    """Test setting and getting activity config."""
    host, _ = host_with_temp_dir
    config = ActivityConfig(
        idle_mode=IdleMode.USER,
        idle_timeout_seconds=7200,
        activity_sources=(ActivitySource.USER, ActivitySource.AGENT),
    )
    host.set_activity_config(config)

    retrieved = host.get_activity_config()
    assert retrieved.idle_mode == IdleMode.USER
    assert retrieved.idle_timeout_seconds == 7200


# =============================================================================
# Activity Time Tests
# =============================================================================


def test_record_boot_activity(host_with_temp_dir: tuple[Host, Path]) -> None:
    """Test recording boot activity."""
    host, _ = host_with_temp_dir
    host.record_activity(ActivitySource.BOOT)
    activity_time = host.get_reported_activity_time(ActivitySource.BOOT)
    assert activity_time is not None


def test_record_create_activity(host_with_temp_dir: tuple[Host, Path]) -> None:
    """Test recording create activity."""
    host, _ = host_with_temp_dir
    host.record_activity(ActivitySource.CREATE)
    activity_time = host.get_reported_activity_time(ActivitySource.CREATE)
    assert activity_time is not None


def test_invalid_activity_type_raises(host_with_temp_dir: tuple[Host, Path]) -> None:
    """Test that recording invalid activity type raises."""
    host, _ = host_with_temp_dir
    with pytest.raises(ValueError):
        host.record_activity(ActivitySource.USER)


def test_get_activity_content(host_with_temp_dir: tuple[Host, Path]) -> None:
    """Test getting activity file content."""
    host, _ = host_with_temp_dir
    host.record_activity(ActivitySource.BOOT)
    content = host.get_reported_activity_content(ActivitySource.BOOT)
    assert content is not None
    assert "T" in content


# =============================================================================
# Cooperative Locking Tests
# =============================================================================


def test_acquire_and_release_lock(host_with_temp_dir: tuple[Host, Path]) -> None:
    """Test acquiring and releasing a lock."""
    host, _ = host_with_temp_dir
    with host.lock_cooperatively(timeout_seconds=5.0):
        lock_time = host.get_reported_lock_time()
        assert lock_time is not None


def test_lock_timeout(host_with_temp_dir: tuple[Host, Path]) -> None:
    """Test that lock times out when held by another process."""
    host, temp_dir = host_with_temp_dir
    lock_path = temp_dir / "host_lock"
    lock_held = threading.Event()
    release_lock = threading.Event()

    def hold_lock():
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        with open(lock_path, "w") as f:
            fcntl.flock(f.fileno(), fcntl.LOCK_EX)
            lock_held.set()
            release_lock.wait()
            fcntl.flock(f.fileno(), fcntl.LOCK_UN)

    thread = threading.Thread(target=hold_lock)
    thread.start()
    lock_held.wait()

    try:
        with pytest.raises(LockNotHeldError):
            with host.lock_cooperatively(timeout_seconds=0.5):
                pass
    finally:
        release_lock.set()
        thread.join()


# =============================================================================
# Certified Data Tests
# =============================================================================


def test_get_empty_certified_data(host_with_temp_dir: tuple[Host, Path]) -> None:
    """Test getting certified data when no file exists."""
    host, _ = host_with_temp_dir
    data = host.get_all_certified_data()
    assert data.idle_mode == IdleMode.AGENT
    assert data.idle_timeout_seconds == 3600
    assert data.plugin == {}


def test_set_and_get_plugin_data(host_with_temp_dir: tuple[Host, Path]) -> None:
    """Test setting and getting plugin data."""
    host, _ = host_with_temp_dir
    host.set_plugin_data("test_plugin", {"key": "value"})
    data = host.get_plugin_data("test_plugin")
    assert data == {"key": "value"}


def test_get_nonexistent_plugin_data(host_with_temp_dir: tuple[Host, Path]) -> None:
    """Test getting data for a plugin that doesn't exist."""
    host, _ = host_with_temp_dir
    data = host.get_plugin_data("nonexistent")
    assert data == {}


# =============================================================================
# Environment Variable Tests
# =============================================================================


def test_get_empty_env_vars(host_with_temp_dir: tuple[Host, Path]) -> None:
    """Test getting env vars when no file exists."""
    host, _ = host_with_temp_dir
    env = host.get_env_vars()
    assert env == {}


def test_set_and_get_env_vars(host_with_temp_dir: tuple[Host, Path]) -> None:
    """Test setting and getting environment variables."""
    host, _ = host_with_temp_dir
    host.set_env_vars({"FOO": "bar", "BAZ": "qux"})
    env = host.get_env_vars()
    assert env["FOO"] == "bar"
    assert env["BAZ"] == "qux"


def test_set_single_env_var(host_with_temp_dir: tuple[Host, Path]) -> None:
    """Test setting a single environment variable."""
    host, _ = host_with_temp_dir
    host.set_env_vars({"EXISTING": "value"})
    host.set_env_var("NEW", "new_value")
    env = host.get_env_vars()
    assert env["EXISTING"] == "value"
    assert env["NEW"] == "new_value"


def test_get_single_env_var(host_with_temp_dir: tuple[Host, Path]) -> None:
    """Test getting a single environment variable."""
    host, _ = host_with_temp_dir
    host.set_env_vars({"MY_VAR": "my_value"})
    value = host.get_env_var("MY_VAR")
    assert value == "my_value"


def test_get_nonexistent_env_var(host_with_temp_dir: tuple[Host, Path]) -> None:
    """Test getting a nonexistent environment variable."""
    host, _ = host_with_temp_dir
    value = host.get_env_var("NONEXISTENT")
    assert value is None


# =============================================================================
# Plugin State Files Tests
# =============================================================================


def test_set_and_get_plugin_state_file(host_with_temp_dir: tuple[Host, Path]) -> None:
    """Test setting and getting plugin state files."""
    host, _ = host_with_temp_dir
    host.set_reported_plugin_state_file_data("test_plugin", "state.txt", "plugin state")
    content = host.get_reported_plugin_state_file_data("test_plugin", "state.txt")
    assert content == "plugin state"


def test_list_plugin_state_files(host_with_temp_dir: tuple[Host, Path]) -> None:
    """Test listing plugin state files."""
    host, _ = host_with_temp_dir
    host.set_reported_plugin_state_file_data("test_plugin", "file1.txt", "content1")
    host.set_reported_plugin_state_file_data("test_plugin", "file2.txt", "content2")
    files = host.get_reported_plugin_state_files("test_plugin")
    assert "file1.txt" in files
    assert "file2.txt" in files


def test_list_nonexistent_plugin_files(host_with_temp_dir: tuple[Host, Path]) -> None:
    """Test listing files for a plugin that doesn't exist."""
    host, _ = host_with_temp_dir
    files = host.get_reported_plugin_state_files("nonexistent")
    assert files == []


# =============================================================================
# Host State Tests
# =============================================================================


def test_local_host_always_running(host_with_temp_dir: tuple[Host, Path]) -> None:
    """Test that local host is always in RUNNING state."""
    host, _ = host_with_temp_dir
    state = host.get_state()
    assert state == HostState.RUNNING


def test_get_uptime(host_with_temp_dir: tuple[Host, Path]) -> None:
    """Test getting host uptime."""
    host, _ = host_with_temp_dir
    uptime = host.get_uptime_seconds()
    assert uptime > 0


# =============================================================================
# Idle Detection Tests
# =============================================================================


def test_get_idle_seconds_no_activity(host_with_temp_dir: tuple[Host, Path]) -> None:
    """Test idle seconds when no activity recorded."""
    host, _ = host_with_temp_dir
    idle = host.get_idle_seconds()
    assert idle == float("inf")


def test_get_idle_seconds_with_activity(host_with_temp_dir: tuple[Host, Path]) -> None:
    """Test idle seconds after recording activity."""
    host, _ = host_with_temp_dir
    host.record_activity(ActivitySource.CREATE)
    idle = host.get_idle_seconds()
    assert 0 <= idle < 10


# =============================================================================
# Agent Creation and Start Tests
# =============================================================================


def test_unset_vars_applied_during_agent_start(
    temp_host_dir: Path, temp_work_dir: Path, plugin_manager: pluggy.PluginManager, mngr_test_prefix: str
) -> None:
    """Test that unset_vars config is applied when starting agents."""
    config_with_unset = MngrConfig(
        default_host_dir=temp_host_dir,
        prefix=mngr_test_prefix,
        unset_vars=["HISTFILE", "PROFILE"],
    )

    mngr_ctx_with_unset = MngrContext(config=config_with_unset, pm=plugin_manager)
    provider_with_unset = LocalProviderInstance(
        name=ProviderInstanceName("local"),
        host_dir=temp_host_dir,
        mngr_ctx=mngr_ctx_with_unset,
    )

    host = provider_with_unset.create_host(HostName("test-unset-vars"))
    assert isinstance(host, Host)

    agent = host.create_agent_state(
        work_dir_path=temp_work_dir,
        options=CreateAgentOptions(
            name=AgentName("test-agent"),
            agent_type=AgentTypeName("generic"),
            command=CommandString("sleep 736249"),
        ),
    )

    host.start_agents([agent.id])

    session_name = f"{mngr_test_prefix}{agent.name}"

    # Wait for the tmux session to be fully ready before sending keys
    def session_ready() -> bool:
        result = host.execute_command(f"tmux has-session -t '{session_name}'")
        return result.success

    wait_for(session_ready, error_message="tmux session not ready")

    host.execute_command(f"tmux send-keys -t '{session_name}' 'echo HISTFILE_VALUE=${{HISTFILE:-UNSET}}' Enter")
    host.execute_command(f"tmux send-keys -t '{session_name}' 'echo PROFILE_VALUE=${{PROFILE:-UNSET}}' Enter")

    def check_output() -> bool:
        capture_result = host.execute_command(f"tmux capture-pane -t '{session_name}' -p")
        if not capture_result.success:
            return False
        output = capture_result.stdout
        has_histfile = "HISTFILE_VALUE=UNSET" in output or "HISTFILE_VALUE=" in output
        has_profile = "PROFILE_VALUE=UNSET" in output or "PROFILE_VALUE=" in output
        return has_histfile and has_profile

    wait_for(check_output, error_message="Expected environment variables not found in tmux output")

    host.stop_agents([agent.id])


# =============================================================================
# Agent Start/Stop Process Group Tests
#
# Note: because of xdist, we must be very careful with our "grep"'s below--
#  by using different sleeps for each command invocation, we can make this safe even when these tests are run concurrently.
# =============================================================================


def test_stop_agent_kills_single_pane_processes(
    temp_host_dir: Path, temp_work_dir: Path, plugin_manager: pluggy.PluginManager, mngr_test_prefix: str
) -> None:
    """Test that stop_agents kills all processes in a single-pane session."""
    config = MngrConfig(default_host_dir=temp_host_dir, prefix=mngr_test_prefix)
    mngr_ctx = MngrContext(config=config, pm=plugin_manager)
    provider = LocalProviderInstance(
        name=ProviderInstanceName("local"),
        host_dir=temp_host_dir,
        mngr_ctx=mngr_ctx,
    )
    host = provider.create_host(HostName("test-stop-single"))
    assert isinstance(host, Host)

    agent = host.create_agent_state(
        work_dir_path=temp_work_dir,
        options=CreateAgentOptions(
            name=AgentName("stop-test-single"),
            agent_type=AgentTypeName("generic"),
            command=CommandString("sleep 1001 & sleep 1001 & sleep 1001 & wait"),
        ),
    )

    host.start_agents([agent.id])
    session_name = f"{mngr_test_prefix}{agent.name}"

    success, output = host._run_shell_command(StringCommand("tmux list-sessions -F '#{session_name}' 2>/dev/null"))
    assert success
    assert session_name in output.stdout

    host.stop_agents([agent.id], timeout_seconds=1.0)

    def check_cleanup() -> bool:
        success, output = host._run_shell_command(StringCommand("tmux list-sessions -F '#{session_name}' 2>/dev/null"))
        session_killed = session_name not in output.stdout
        success_ps, output_ps = host._run_shell_command(StringCommand("ps aux | grep 'sleep 1001' | grep -v grep"))
        processes_killed = "sleep 1001" not in output_ps.stdout or not success_ps
        return session_killed and processes_killed

    wait_for(check_cleanup, error_message="Agent session and processes not cleaned up after stop")


def test_stop_agent_kills_multi_pane_processes(
    temp_host_dir: Path, temp_work_dir: Path, plugin_manager: pluggy.PluginManager, mngr_test_prefix: str
) -> None:
    """Test that stop_agents kills all processes in a multi-pane session."""
    config = MngrConfig(default_host_dir=temp_host_dir, prefix=mngr_test_prefix)
    mngr_ctx = MngrContext(config=config, pm=plugin_manager)
    provider = LocalProviderInstance(
        name=ProviderInstanceName("local"),
        host_dir=temp_host_dir,
        mngr_ctx=mngr_ctx,
    )
    host = provider.create_host(HostName("test-stop-multi"))
    assert isinstance(host, Host)

    agent = host.create_agent_state(
        work_dir_path=temp_work_dir,
        options=CreateAgentOptions(
            name=AgentName("stop-test-multi"),
            agent_type=AgentTypeName("generic"),
            command=CommandString("sleep 1000"),
        ),
    )

    host.start_agents([agent.id])
    session_name = f"{mngr_test_prefix}{agent.name}"

    host._run_shell_command(StringCommand(f"tmux split-window -t '{session_name}' 'sleep 2000'"))
    host._run_shell_command(StringCommand(f"tmux split-window -t '{session_name}' 'sleep 3000'"))

    success, output = host._run_shell_command(
        StringCommand(f"tmux list-panes -t '{session_name}' 2>/dev/null | wc -l")
    )
    assert success
    pane_count = int(output.stdout.strip())
    assert pane_count == 3

    host.stop_agents([agent.id], timeout_seconds=1.0)

    def check_cleanup() -> bool:
        success, output = host._run_shell_command(StringCommand("tmux list-sessions -F '#{session_name}' 2>/dev/null"))
        session_killed = session_name not in output.stdout
        success_ps, output_ps = host._run_shell_command(
            StringCommand("ps aux | grep -E 'sleep (1000|2000|3000)' | grep -v grep")
        )
        processes_killed = "sleep" not in output_ps.stdout or not success_ps
        return session_killed and processes_killed

    wait_for(check_cleanup, error_message="Multi-pane agent session and processes not cleaned up after stop")


def test_start_agent_creates_process_group(
    temp_host_dir: Path, temp_work_dir: Path, plugin_manager: pluggy.PluginManager, mngr_test_prefix: str
) -> None:
    """Test that start_agents creates tmux sessions in their own process group."""
    config = MngrConfig(default_host_dir=temp_host_dir, prefix=mngr_test_prefix)
    mngr_ctx = MngrContext(config=config, pm=plugin_manager)
    provider = LocalProviderInstance(
        name=ProviderInstanceName("local"),
        host_dir=temp_host_dir,
        mngr_ctx=mngr_ctx,
    )
    host = provider.create_host(HostName("test-pgid"))
    assert isinstance(host, Host)

    agent = host.create_agent_state(
        work_dir_path=temp_work_dir,
        options=CreateAgentOptions(
            name=AgentName("pgid-test"),
            agent_type=AgentTypeName("generic"),
            command=CommandString("sleep 847263"),
        ),
    )

    host.start_agents([agent.id])
    session_name = f"{mngr_test_prefix}{agent.name}"

    success, output = host._run_shell_command(
        StringCommand(f"tmux list-panes -t '{session_name}' -F '#{{pane_pid}}' 2>/dev/null")
    )
    assert success
    pane_pid = output.stdout.strip()
    assert pane_pid

    success, output = host._run_shell_command(StringCommand(f"ps -o pgid= -p {pane_pid} 2>/dev/null"))
    assert success
    pgid = output.stdout.strip()
    assert pgid

    host.stop_agents([agent.id])


# =============================================================================
# Additional Commands Tests
# =============================================================================


def test_additional_commands_stored_in_agent_data(
    temp_host_dir: Path, temp_work_dir: Path, plugin_manager: pluggy.PluginManager, mngr_test_prefix: str
) -> None:
    """Test that additional_commands are stored in the agent's data.json."""
    config = MngrConfig(default_host_dir=temp_host_dir, prefix=mngr_test_prefix)
    mngr_ctx = MngrContext(config=config, pm=plugin_manager)
    provider = LocalProviderInstance(
        name=ProviderInstanceName("local"),
        host_dir=temp_host_dir,
        mngr_ctx=mngr_ctx,
    )
    host = provider.create_host(HostName("test-additional-cmds-stored"))
    assert isinstance(host, Host)

    agent = host.create_agent_state(
        work_dir_path=temp_work_dir,
        options=CreateAgentOptions(
            name=AgentName("additional-cmds-stored"),
            agent_type=AgentTypeName("generic"),
            command=CommandString("sleep 892741"),
            additional_commands=(
                NamedCommand(command=CommandString("echo additional-cmd-1"), window_name=None),
                NamedCommand(command=CommandString("echo additional-cmd-2"), window_name="custom-window"),
            ),
        ),
    )

    # Read the data.json file and verify additional_commands are stored
    data_path = temp_host_dir / "agents" / str(agent.id) / "data.json"
    data = json.loads(data_path.read_text())

    assert "additional_commands" in data
    assert data["additional_commands"] == [
        {"command": "echo additional-cmd-1", "window_name": None},
        {"command": "echo additional-cmd-2", "window_name": "custom-window"},
    ]


def test_start_agent_creates_additional_tmux_windows(
    temp_host_dir: Path, temp_work_dir: Path, plugin_manager: pluggy.PluginManager, mngr_test_prefix: str
) -> None:
    """Test that start_agents creates additional tmux windows for additional_commands."""
    config = MngrConfig(default_host_dir=temp_host_dir, prefix=mngr_test_prefix)
    mngr_ctx = MngrContext(config=config, pm=plugin_manager)
    provider = LocalProviderInstance(
        name=ProviderInstanceName("local"),
        host_dir=temp_host_dir,
        mngr_ctx=mngr_ctx,
    )
    host = provider.create_host(HostName("test-additional-windows"))
    assert isinstance(host, Host)

    agent = host.create_agent_state(
        work_dir_path=temp_work_dir,
        options=CreateAgentOptions(
            name=AgentName("additional-windows"),
            agent_type=AgentTypeName("generic"),
            command=CommandString("sleep 764821"),
            additional_commands=(
                NamedCommand(command=CommandString("sleep 764822"), window_name=None),
                NamedCommand(command=CommandString("sleep 764823"), window_name=None),
            ),
        ),
    )

    host.start_agents([agent.id])
    session_name = f"{mngr_test_prefix}{agent.name}"

    try:
        # Verify the session was created
        success, output = host._run_shell_command(StringCommand("tmux list-sessions -F '#{session_name}' 2>/dev/null"))
        assert success
        assert session_name in output.stdout

        # Verify we have 3 windows (main + 2 additional)
        success, output = host._run_shell_command(
            StringCommand(f"tmux list-windows -t '{session_name}' -F '#{{window_name}}' 2>/dev/null")
        )
        assert success
        windows = output.stdout.strip().split("\n")
        assert len(windows) == 3, f"Expected 3 windows, got {len(windows)}: {windows}"

        # Verify window names
        assert "cmd-1" in windows
        assert "cmd-2" in windows

    finally:
        host.stop_agents([agent.id])


def test_start_agent_additional_windows_run_commands(
    temp_host_dir: Path, temp_work_dir: Path, plugin_manager: pluggy.PluginManager, mngr_test_prefix: str
) -> None:
    """Test that additional tmux windows actually run the specified commands."""
    config = MngrConfig(default_host_dir=temp_host_dir, prefix=mngr_test_prefix)
    mngr_ctx = MngrContext(config=config, pm=plugin_manager)
    provider = LocalProviderInstance(
        name=ProviderInstanceName("local"),
        host_dir=temp_host_dir,
        mngr_ctx=mngr_ctx,
    )
    host = provider.create_host(HostName("test-additional-commands"))
    assert isinstance(host, Host)

    agent = host.create_agent_state(
        work_dir_path=temp_work_dir,
        options=CreateAgentOptions(
            name=AgentName("additional-commands-run"),
            agent_type=AgentTypeName("generic"),
            command=CommandString("sleep 938472"),
            additional_commands=(
                NamedCommand(command=CommandString("echo UNIQUE_MARKER_938473 && sleep 938474"), window_name=None),
            ),
        ),
    )

    host.start_agents([agent.id])
    session_name = f"{mngr_test_prefix}{agent.name}"

    try:
        # Wait for the additional command to produce output
        def check_output() -> bool:
            capture_result = host._run_shell_command(
                StringCommand(f"tmux capture-pane -t '{session_name}:cmd-1' -p 2>/dev/null")
            )
            if not capture_result[0]:
                return False
            return "UNIQUE_MARKER_938473" in capture_result[1].stdout

        wait_for(check_output, error_message="Expected output from additional command not found")

    finally:
        host.stop_agents([agent.id])


# =============================================================================
# Provision Agent Tests
# =============================================================================


def test_provision_agent_create_directories(host_with_temp_dir: tuple[Host, Path]) -> None:
    """Test that provision_agent creates directories."""
    host, temp_dir = host_with_temp_dir
    agent = _create_minimal_agent(host, temp_dir)

    dir1 = temp_dir / "provision_test" / "dir1"
    dir2 = temp_dir / "provision_test" / "nested" / "dir2"

    options = CreateAgentOptions(
        name=AgentName("prov-dirs"),
        agent_type=AgentTypeName("generic"),
        command=CommandString("sleep 1"),
        provisioning=AgentProvisioningOptions(
            create_directories=(dir1, dir2),
        ),
    )

    host.provision_agent(agent, options, host.mngr_ctx)

    assert dir1.exists()
    assert dir1.is_dir()
    assert dir2.exists()
    assert dir2.is_dir()


def test_provision_agent_upload_files(host_with_temp_dir: tuple[Host, Path], tmp_path: Path) -> None:
    """Test that provision_agent uploads files from local to remote."""
    host, temp_dir = host_with_temp_dir
    agent = _create_minimal_agent(host, temp_dir)

    # Create a local file to upload
    local_file = tmp_path / "source" / "config.txt"
    local_file.parent.mkdir(parents=True)
    local_file.write_text("uploaded content")

    remote_path = temp_dir / "provision_test" / "config.txt"

    options = CreateAgentOptions(
        name=AgentName("prov-upload"),
        agent_type=AgentTypeName("generic"),
        command=CommandString("sleep 1"),
        provisioning=AgentProvisioningOptions(
            upload_files=(UploadFileSpec(local_path=local_file, remote_path=remote_path),),
        ),
    )

    host.provision_agent(agent, options, host.mngr_ctx)

    assert remote_path.exists()
    assert remote_path.read_text() == "uploaded content"


def test_provision_agent_append_to_existing_file(host_with_temp_dir: tuple[Host, Path]) -> None:
    """Test that provision_agent appends text to existing files."""
    host, temp_dir = host_with_temp_dir
    agent = _create_minimal_agent(host, temp_dir)

    target_file = temp_dir / "provision_test" / "append.txt"
    target_file.parent.mkdir(parents=True)
    target_file.write_text("existing content\n")

    options = CreateAgentOptions(
        name=AgentName("prov-append"),
        agent_type=AgentTypeName("generic"),
        command=CommandString("sleep 1"),
        provisioning=AgentProvisioningOptions(
            append_to_files=(FileModificationSpec(remote_path=target_file, text="appended text"),),
        ),
    )

    host.provision_agent(agent, options, host.mngr_ctx)

    assert target_file.read_text() == "existing content\nappended text"


def test_provision_agent_append_to_new_file(host_with_temp_dir: tuple[Host, Path]) -> None:
    """Test that provision_agent creates file when appending to non-existent file."""
    host, temp_dir = host_with_temp_dir
    agent = _create_minimal_agent(host, temp_dir)

    target_file = temp_dir / "provision_test" / "new_append.txt"

    options = CreateAgentOptions(
        name=AgentName("prov-append-new"),
        agent_type=AgentTypeName("generic"),
        command=CommandString("sleep 1"),
        provisioning=AgentProvisioningOptions(
            create_directories=(target_file.parent,),
            append_to_files=(FileModificationSpec(remote_path=target_file, text="new content"),),
        ),
    )

    host.provision_agent(agent, options, host.mngr_ctx)

    assert target_file.exists()
    assert target_file.read_text() == "new content"


def test_provision_agent_prepend_to_existing_file(host_with_temp_dir: tuple[Host, Path]) -> None:
    """Test that provision_agent prepends text to existing files."""
    host, temp_dir = host_with_temp_dir
    agent = _create_minimal_agent(host, temp_dir)

    target_file = temp_dir / "provision_test" / "prepend.txt"
    target_file.parent.mkdir(parents=True)
    target_file.write_text("existing content")

    options = CreateAgentOptions(
        name=AgentName("prov-prepend"),
        agent_type=AgentTypeName("generic"),
        command=CommandString("sleep 1"),
        provisioning=AgentProvisioningOptions(
            prepend_to_files=(FileModificationSpec(remote_path=target_file, text="prepended: "),),
        ),
    )

    host.provision_agent(agent, options, host.mngr_ctx)

    assert target_file.read_text() == "prepended: existing content"


def test_provision_agent_prepend_to_new_file(host_with_temp_dir: tuple[Host, Path]) -> None:
    """Test that provision_agent creates file when prepending to non-existent file."""
    host, temp_dir = host_with_temp_dir
    agent = _create_minimal_agent(host, temp_dir)

    target_file = temp_dir / "provision_test" / "new_prepend.txt"

    options = CreateAgentOptions(
        name=AgentName("prov-prepend-new"),
        agent_type=AgentTypeName("generic"),
        command=CommandString("sleep 1"),
        provisioning=AgentProvisioningOptions(
            create_directories=(target_file.parent,),
            prepend_to_files=(FileModificationSpec(remote_path=target_file, text="new content"),),
        ),
    )

    host.provision_agent(agent, options, host.mngr_ctx)

    assert target_file.exists()
    assert target_file.read_text() == "new content"


def test_provision_agent_user_commands(host_with_temp_dir: tuple[Host, Path]) -> None:
    """Test that provision_agent runs user commands."""
    host, temp_dir = host_with_temp_dir
    agent = _create_minimal_agent(host, temp_dir)

    marker_file = temp_dir / "provision_test" / "marker.txt"

    options = CreateAgentOptions(
        name=AgentName("prov-user-cmd"),
        agent_type=AgentTypeName("generic"),
        command=CommandString("sleep 1"),
        provisioning=AgentProvisioningOptions(
            create_directories=(marker_file.parent,),
            user_commands=(f"echo 'user command executed' > {marker_file}",),
        ),
    )

    host.provision_agent(agent, options, host.mngr_ctx)

    assert marker_file.exists()
    assert "user command executed" in marker_file.read_text()


def test_provision_agent_user_commands_in_work_dir(host_with_temp_dir: tuple[Host, Path]) -> None:
    """Test that user commands run in the agent's work_dir."""
    host, temp_dir = host_with_temp_dir

    # Create agent with a specific work_dir
    work_dir = temp_dir / "agent_work_dir"
    work_dir.mkdir(parents=True)
    agent = _create_minimal_agent(host, temp_dir, work_dir=work_dir)

    marker_file = work_dir / "pwd_output.txt"

    options = CreateAgentOptions(
        name=AgentName("prov-cwd"),
        agent_type=AgentTypeName("generic"),
        command=CommandString("sleep 1"),
        provisioning=AgentProvisioningOptions(
            user_commands=(f"pwd > {marker_file}",),
        ),
    )

    host.provision_agent(agent, options, host.mngr_ctx)

    assert marker_file.exists()
    assert str(work_dir) in marker_file.read_text()


def test_provision_agent_multiple_user_commands(host_with_temp_dir: tuple[Host, Path]) -> None:
    """Test that provision_agent runs multiple user commands in order."""
    host, temp_dir = host_with_temp_dir
    agent = _create_minimal_agent(host, temp_dir)

    output_file = temp_dir / "provision_test" / "sequence.txt"

    options = CreateAgentOptions(
        name=AgentName("prov-multi-cmd"),
        agent_type=AgentTypeName("generic"),
        command=CommandString("sleep 1"),
        provisioning=AgentProvisioningOptions(
            create_directories=(output_file.parent,),
            user_commands=(
                f"echo 'first' > {output_file}",
                f"echo 'second' >> {output_file}",
                f"echo 'third' >> {output_file}",
            ),
        ),
    )

    host.provision_agent(agent, options, host.mngr_ctx)

    assert output_file.exists()
    content = output_file.read_text()
    lines = content.strip().split("\n")
    assert lines[0] == "first"
    assert lines[1] == "second"
    assert lines[2] == "third"


def test_provision_agent_user_command_failure_raises(host_with_temp_dir: tuple[Host, Path]) -> None:
    """Test that provision_agent raises on user command failure."""
    host, temp_dir = host_with_temp_dir
    agent = _create_minimal_agent(host, temp_dir)

    options = CreateAgentOptions(
        name=AgentName("prov-fail"),
        agent_type=AgentTypeName("generic"),
        command=CommandString("sleep 1"),
        provisioning=AgentProvisioningOptions(
            user_commands=("exit 1",),
        ),
    )

    with pytest.raises(MngrError) as exc_info:
        host.provision_agent(agent, options, host.mngr_ctx)

    assert "User command failed" in str(exc_info.value)


def test_provision_agent_combined_options(host_with_temp_dir: tuple[Host, Path], tmp_path: Path) -> None:
    """Test provision_agent with multiple option types combined."""
    host, temp_dir = host_with_temp_dir
    agent = _create_minimal_agent(host, temp_dir)

    # Create local file to upload
    local_file = tmp_path / "source" / "upload.txt"
    local_file.parent.mkdir(parents=True)
    local_file.write_text("uploaded")

    provision_dir = temp_dir / "provision_combined"
    remote_upload = provision_dir / "uploaded.txt"
    append_file = provision_dir / "appended.txt"
    marker_file = provision_dir / "marker.txt"

    options = CreateAgentOptions(
        name=AgentName("prov-combined"),
        agent_type=AgentTypeName("generic"),
        command=CommandString("sleep 1"),
        provisioning=AgentProvisioningOptions(
            create_directories=(provision_dir,),
            upload_files=(UploadFileSpec(local_path=local_file, remote_path=remote_upload),),
            append_to_files=(FileModificationSpec(remote_path=append_file, text="appended content"),),
            user_commands=(f"echo 'marker' > {marker_file}",),
        ),
    )

    host.provision_agent(agent, options, host.mngr_ctx)

    # Verify all operations completed
    assert provision_dir.exists()
    assert remote_upload.read_text() == "uploaded"
    assert append_file.read_text() == "appended content"
    assert marker_file.read_text().strip() == "marker"


def test_provision_agent_upload_binary_file(host_with_temp_dir: tuple[Host, Path], tmp_path: Path) -> None:
    """Test that provision_agent uploads binary files correctly."""
    host, temp_dir = host_with_temp_dir
    agent = _create_minimal_agent(host, temp_dir)

    # Create a binary file
    local_file = tmp_path / "source" / "binary.bin"
    local_file.parent.mkdir(parents=True)
    binary_content = bytes(range(256))
    local_file.write_bytes(binary_content)

    remote_path = temp_dir / "provision_test" / "binary.bin"

    options = CreateAgentOptions(
        name=AgentName("prov-binary"),
        agent_type=AgentTypeName("generic"),
        command=CommandString("sleep 1"),
        provisioning=AgentProvisioningOptions(
            create_directories=(remote_path.parent,),
            upload_files=(UploadFileSpec(local_path=local_file, remote_path=remote_path),),
        ),
    )

    host.provision_agent(agent, options, host.mngr_ctx)

    assert remote_path.exists()
    assert remote_path.read_bytes() == binary_content


def test_provision_agent_order_of_operations(host_with_temp_dir: tuple[Host, Path], tmp_path: Path) -> None:
    """Test that provisioning operations happen in the correct order.

    The order should be:
    1. Create directories
    2. Upload files
    3. Append to files
    4. Prepend to files
    5. Sudo commands (skipped in this test)
    6. User commands
    """
    host, temp_dir = host_with_temp_dir
    agent = _create_minimal_agent(host, temp_dir)

    provision_dir = temp_dir / "order_test"
    target_file = provision_dir / "target.txt"
    log_file = provision_dir / "log.txt"

    # Create local file to upload
    local_file = tmp_path / "upload.txt"
    local_file.write_text("uploaded\n")

    options = CreateAgentOptions(
        name=AgentName("prov-order"),
        agent_type=AgentTypeName("generic"),
        command=CommandString("sleep 1"),
        provisioning=AgentProvisioningOptions(
            # 1. Create directories - must happen first so upload works
            create_directories=(provision_dir,),
            # 2. Upload files - puts base content in place
            upload_files=(UploadFileSpec(local_path=local_file, remote_path=target_file),),
            # 3. Append - adds to end of uploaded content
            append_to_files=(FileModificationSpec(remote_path=target_file, text="appended\n"),),
            # 4. Prepend - adds to beginning
            prepend_to_files=(FileModificationSpec(remote_path=target_file, text="prepended\n"),),
            # 6. User commands - run last, can verify final state
            user_commands=(f"cat {target_file} > {log_file}",),
        ),
    )

    host.provision_agent(agent, options, host.mngr_ctx)

    # Verify the final order in the file
    content = target_file.read_text()
    assert content == "prepended\nuploaded\nappended\n"

    # Log file should have captured the same content
    assert log_file.read_text() == content


# =============================================================================
# Helper Functions for Provision Tests
# =============================================================================


def _create_minimal_agent(host: Host, temp_dir: Path, work_dir: Path | None = None) -> AgentInterface:
    """Create a minimal agent for provisioning tests."""
    if work_dir is None:
        work_dir = temp_dir / "work"
        work_dir.mkdir(parents=True, exist_ok=True)

    return host.create_agent_state(
        work_dir_path=work_dir,
        options=CreateAgentOptions(
            name=AgentName("test-agent"),
            agent_type=AgentTypeName("generic"),
            command=CommandString("sleep 1"),
        ),
    )


# =============================================================================
# Provision Agent Hook Tests
# =============================================================================


class _ProvisionHookTracker:
    """Test plugin that tracks when on_provision_agent is called."""

    def __init__(self, marker_path: Path) -> None:
        self.marker_path = marker_path
        self.call_count = 0
        self.agent_names: list[str] = []

    @hookimpl
    def provision_agent(
        self,
        agent: AgentInterface,
        host: "Host",
        options: CreateAgentOptions,
        mngr_ctx: MngrContext,
    ) -> None:
        """Hook implementation that records when it was called."""
        self.call_count += 1
        self.agent_names.append(str(agent.name))
        # Write a marker file to verify hook ran before CLI options
        self.marker_path.parent.mkdir(parents=True, exist_ok=True)
        self.marker_path.write_text(f"hook_called:{agent.name}")


def test_provision_agent_calls_hook(
    temp_host_dir: Path, temp_work_dir: Path, plugin_manager: pluggy.PluginManager, mngr_test_prefix: str
) -> None:
    """Test that provision_agent calls the provision_agent hook."""
    marker_path = temp_host_dir / "hook_marker.txt"
    hook_tracker = _ProvisionHookTracker(marker_path)
    plugin_manager.register(hook_tracker)

    try:
        config = MngrConfig(default_host_dir=temp_host_dir, prefix=mngr_test_prefix)
        mngr_ctx = MngrContext(config=config, pm=plugin_manager)
        provider = LocalProviderInstance(
            name=ProviderInstanceName("local"),
            host_dir=temp_host_dir,
            mngr_ctx=mngr_ctx,
        )
        host = provider.create_host(HostName("test-hook"))
        assert isinstance(host, Host)

        agent = host.create_agent_state(
            work_dir_path=temp_work_dir,
            options=CreateAgentOptions(
                name=AgentName("hook-test-agent"),
                agent_type=AgentTypeName("generic"),
                command=CommandString("sleep 1"),
            ),
        )

        host.provision_agent(
            agent,
            CreateAgentOptions(
                name=AgentName("hook-test-agent"),
                agent_type=AgentTypeName("generic"),
                command=CommandString("sleep 1"),
            ),
            mngr_ctx,
        )

        # Verify hook was called
        assert hook_tracker.call_count == 1
        assert "hook-test-agent" in hook_tracker.agent_names
        assert marker_path.exists()
        assert "hook_called:hook-test-agent" in marker_path.read_text()

    finally:
        plugin_manager.unregister(hook_tracker)


def test_provision_agent_hook_called_before_cli_options(
    temp_host_dir: Path, temp_work_dir: Path, plugin_manager: pluggy.PluginManager, mngr_test_prefix: str
) -> None:
    """Test that provision_agent hook is called before CLI options are applied."""
    # This marker file will be created by CLI user_commands
    cli_marker_path = temp_host_dir / "provision_test" / "cli_marker.txt"
    hook_marker_path = temp_host_dir / "hook_order_marker.txt"

    class _OrderTrackingHook:
        """Hook that records if CLI marker exists when hook runs."""

        def __init__(self) -> None:
            self.cli_marker_existed_when_hook_ran: bool | None = None

        @hookimpl
        def provision_agent(
            self,
            agent: AgentInterface,
            host: "Host",
            options: CreateAgentOptions,
            mngr_ctx: MngrContext,
        ) -> None:
            # Check if CLI marker file exists (it should NOT at this point)
            self.cli_marker_existed_when_hook_ran = cli_marker_path.exists()
            # Write our own marker
            hook_marker_path.parent.mkdir(parents=True, exist_ok=True)
            hook_marker_path.write_text("hook_ran_first")

    order_tracker = _OrderTrackingHook()
    plugin_manager.register(order_tracker)

    try:
        config = MngrConfig(default_host_dir=temp_host_dir, prefix=mngr_test_prefix)
        mngr_ctx = MngrContext(config=config, pm=plugin_manager)
        provider = LocalProviderInstance(
            name=ProviderInstanceName("local"),
            host_dir=temp_host_dir,
            mngr_ctx=mngr_ctx,
        )
        host = provider.create_host(HostName("test-hook-order"))
        assert isinstance(host, Host)

        agent = host.create_agent_state(
            work_dir_path=temp_work_dir,
            options=CreateAgentOptions(
                name=AgentName("hook-order-agent"),
                agent_type=AgentTypeName("generic"),
                command=CommandString("sleep 1"),
            ),
        )

        # Provision with a CLI user_command that creates a marker file
        host.provision_agent(
            agent,
            CreateAgentOptions(
                name=AgentName("hook-order-agent"),
                agent_type=AgentTypeName("generic"),
                command=CommandString("sleep 1"),
                provisioning=AgentProvisioningOptions(
                    create_directories=(cli_marker_path.parent,),
                    user_commands=(f"echo 'cli_ran' > {cli_marker_path}",),
                ),
            ),
            mngr_ctx,
        )

        # Verify ordering: hook ran first (CLI marker did NOT exist when hook ran)
        assert order_tracker.cli_marker_existed_when_hook_ran is False
        # But CLI marker should exist now (CLI commands ran after hook)
        assert cli_marker_path.exists()
        assert hook_marker_path.exists()

    finally:
        plugin_manager.unregister(order_tracker)


# =============================================================================
# Agent Environment Variable Tests
# =============================================================================


def test_provision_agent_writes_env_vars_to_file(host_with_temp_dir: tuple[Host, Path]) -> None:
    """Test that provision_agent writes env_vars to the agent's env file."""
    host, temp_dir = host_with_temp_dir
    agent = _create_minimal_agent(host, temp_dir)

    options = CreateAgentOptions(
        name=AgentName("env-test"),
        agent_type=AgentTypeName("generic"),
        command=CommandString("sleep 1"),
        environment=AgentEnvironmentOptions(
            env_vars=(
                EnvVar(key="MY_VAR", value="my_value"),
                EnvVar(key="ANOTHER_VAR", value="another_value"),
            ),
        ),
    )

    host.provision_agent(agent, options, host.mngr_ctx)

    # Check that env file was created
    env_path = temp_dir / "agents" / str(agent.id) / "env"
    assert env_path.exists()

    content = env_path.read_text()
    assert "MY_VAR=my_value" in content
    assert "ANOTHER_VAR=another_value" in content


def test_provision_agent_writes_env_files_to_agent_env(host_with_temp_dir: tuple[Host, Path], tmp_path: Path) -> None:
    """Test that provision_agent loads env vars from env_files."""
    host, temp_dir = host_with_temp_dir
    agent = _create_minimal_agent(host, temp_dir)

    # Create an env file to load
    env_file = tmp_path / "test.env"
    env_file.write_text("FROM_FILE=file_value\nSECOND_VAR=second_value\n")

    options = CreateAgentOptions(
        name=AgentName("env-file-test"),
        agent_type=AgentTypeName("generic"),
        command=CommandString("sleep 1"),
        environment=AgentEnvironmentOptions(
            env_files=(env_file,),
        ),
    )

    host.provision_agent(agent, options, host.mngr_ctx)

    # Check that env file was created with vars from the env file
    env_path = temp_dir / "agents" / str(agent.id) / "env"
    assert env_path.exists()

    content = env_path.read_text()
    assert "FROM_FILE=file_value" in content
    assert "SECOND_VAR=second_value" in content


def test_provision_agent_user_commands_have_access_to_env_vars(host_with_temp_dir: tuple[Host, Path]) -> None:
    """Test that user commands can access the environment variables."""
    host, temp_dir = host_with_temp_dir
    agent = _create_minimal_agent(host, temp_dir)

    output_file = temp_dir / "provision_test" / "env_output.txt"

    options = CreateAgentOptions(
        name=AgentName("env-cmd-test"),
        agent_type=AgentTypeName("generic"),
        command=CommandString("sleep 1"),
        environment=AgentEnvironmentOptions(
            env_vars=(EnvVar(key="PROVISION_TEST_VAR", value="test_value_12345"),),
        ),
        provisioning=AgentProvisioningOptions(
            create_directories=(output_file.parent,),
            user_commands=(f"echo $PROVISION_TEST_VAR > {output_file}",),
        ),
    )

    host.provision_agent(agent, options, host.mngr_ctx)

    assert output_file.exists()
    assert "test_value_12345" in output_file.read_text()


def test_provision_agent_env_vars_precedence(
    host_with_temp_dir: tuple[Host, Path], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test that env_vars override env_files, and pass_env_vars override both."""
    host, temp_dir = host_with_temp_dir
    agent = _create_minimal_agent(host, temp_dir)

    # Create an env file with a value
    env_file = tmp_path / "test.env"
    env_file.write_text("OVERRIDE_VAR=from_file\n")

    # Set env_var to override the file
    # (Note: pass_env_vars is processed after env_vars, so it would override both)

    options = CreateAgentOptions(
        name=AgentName("env-precedence-test"),
        agent_type=AgentTypeName("generic"),
        command=CommandString("sleep 1"),
        environment=AgentEnvironmentOptions(
            env_files=(env_file,),
            env_vars=(EnvVar(key="OVERRIDE_VAR", value="from_env_var"),),
        ),
    )

    host.provision_agent(agent, options, host.mngr_ctx)

    # Check that env_vars overrode env_files
    env_path = temp_dir / "agents" / str(agent.id) / "env"
    content = env_path.read_text()
    assert "OVERRIDE_VAR=from_env_var" in content
    assert "from_file" not in content


def test_start_agent_has_access_to_env_vars(
    temp_host_dir: Path, temp_work_dir: Path, plugin_manager: pluggy.PluginManager, mngr_test_prefix: str
) -> None:
    """Test that started agents have access to environment variables.

    This test verifies that when an agent command runs, it has access to the
    environment variables defined in the agent's env file. We use a command
    that prints an env var to a file to verify this.
    """
    config = MngrConfig(default_host_dir=temp_host_dir, prefix=mngr_test_prefix)
    mngr_ctx = MngrContext(config=config, pm=plugin_manager)
    provider = LocalProviderInstance(
        name=ProviderInstanceName("local"),
        host_dir=temp_host_dir,
        mngr_ctx=mngr_ctx,
    )
    host = provider.create_host(HostName("test-env-start"))
    assert isinstance(host, Host)

    # Create a marker file path where the agent will write the env var value
    marker_file = temp_work_dir / "env_marker.txt"

    # The command will print the env var to a file, then sleep
    options = CreateAgentOptions(
        name=AgentName("env-start-test"),
        agent_type=AgentTypeName("generic"),
        command=CommandString(f"echo AGENT_START_VAR=$AGENT_START_VAR > {marker_file} && sleep 847291"),
        environment=AgentEnvironmentOptions(
            env_vars=(EnvVar(key="AGENT_START_VAR", value="agent_env_value_847291"),),
        ),
    )

    agent = host.create_agent_state(
        work_dir_path=temp_work_dir,
        options=options,
    )

    # Provision the agent to write the env file
    host.provision_agent(agent, options, mngr_ctx)

    # Start the agent
    host.start_agents([agent.id])

    try:
        # Wait for the marker file to be written
        def check_marker_file() -> bool:
            if not marker_file.exists():
                return False
            content = marker_file.read_text()
            return "AGENT_START_VAR=agent_env_value_847291" in content

        wait_for(check_marker_file, error_message="Expected environment variable not found in agent output file")

    finally:
        host.stop_agents([agent.id])


@pytest.mark.timeout(15)
def test_new_tmux_window_inherits_env_vars(
    temp_host_dir: Path, temp_work_dir: Path, plugin_manager: pluggy.PluginManager, mngr_test_prefix: str
) -> None:
    """Test that new tmux windows created by the user also have env vars.

    This verifies that the default-command is set on the tmux session so that
    any new window/pane created by the user will automatically source the env files.
    """
    config = MngrConfig(default_host_dir=temp_host_dir, prefix=mngr_test_prefix)
    mngr_ctx = MngrContext(config=config, pm=plugin_manager)
    provider = LocalProviderInstance(
        name=ProviderInstanceName("local"),
        host_dir=temp_host_dir,
        mngr_ctx=mngr_ctx,
    )
    host = provider.create_host(HostName("test-new-window"))
    assert isinstance(host, Host)

    marker_file = temp_work_dir / "new_window_marker.txt"
    session_name = f"{config.prefix}new-window-test"

    options = CreateAgentOptions(
        name=AgentName("new-window-test"),
        agent_type=AgentTypeName("generic"),
        command=CommandString("sleep 999999"),
        environment=AgentEnvironmentOptions(
            env_vars=(EnvVar(key="NEW_WINDOW_VAR", value="new_window_value_123456"),),
        ),
    )

    agent = host.create_agent_state(
        work_dir_path=temp_work_dir,
        options=options,
    )

    host.provision_agent(agent, options, mngr_ctx)
    host.start_agents([agent.id])

    try:
        # Create a new window in the session (simulating what a user would do)
        # This window should inherit the default-command which sources env files
        subprocess.run(
            ["tmux", "new-window", "-t", session_name, "-n", "user-window"],
            check=True,
            capture_output=True,
        )

        # Wait for the window to exist and shell to be ready
        # The shell is ready when it shows a prompt (has content in the pane)
        def window_ready() -> bool:
            result = subprocess.run(
                ["tmux", "list-windows", "-t", session_name, "-F", "#{window_name}"],
                capture_output=True,
                text=True,
            )
            if "user-window" not in result.stdout:
                return False
            # Check if the shell has started by looking for prompt content
            # The pane should have some content once the shell is ready
            capture = subprocess.run(
                ["tmux", "capture-pane", "-t", f"{session_name}:user-window", "-p"],
                capture_output=True,
                text=True,
            )
            # Shell is ready when it has displayed something (the prompt)
            # An empty pane means the shell hasn't started yet
            return capture.returncode == 0 and len(capture.stdout.strip()) > 0

        wait_for(window_ready, timeout=10.0, error_message="Window user-window not ready in session")

        # Send a command to the new window that writes the env var to a file
        subprocess.run(
            [
                "tmux",
                "send-keys",
                "-t",
                f"{session_name}:user-window",
                f"echo NEW_WINDOW_VAR=$NEW_WINDOW_VAR > {marker_file}",
                "Enter",
            ],
            check=True,
            capture_output=True,
        )

        # Wait for the marker file to be written with the expected value
        def check_marker_file() -> bool:
            if not marker_file.exists():
                return False
            content = marker_file.read_text()
            return "NEW_WINDOW_VAR=new_window_value_123456" in content

        wait_for(check_marker_file, error_message="New tmux window did not inherit environment variables")

    finally:
        host.stop_agents([agent.id])


def test_provision_agent_host_env_sourced_before_agent_env(host_with_temp_dir: tuple[Host, Path]) -> None:
    """Test that host env is sourced before agent env (agent can override host)."""
    host, temp_dir = host_with_temp_dir
    agent = _create_minimal_agent(host, temp_dir)

    # Set a host-level env var
    host.set_env_var("HOST_VAR", "host_value")
    host.set_env_var("SHARED_VAR", "from_host")

    output_file = temp_dir / "provision_test" / "host_env_output.txt"

    options = CreateAgentOptions(
        name=AgentName("host-env-test"),
        agent_type=AgentTypeName("generic"),
        command=CommandString("sleep 1"),
        environment=AgentEnvironmentOptions(
            env_vars=(EnvVar(key="SHARED_VAR", value="from_agent"),),
        ),
        provisioning=AgentProvisioningOptions(
            create_directories=(output_file.parent,),
            user_commands=(f"echo HOST_VAR=$HOST_VAR SHARED_VAR=$SHARED_VAR > {output_file}",),
        ),
    )

    host.provision_agent(agent, options, host.mngr_ctx)

    assert output_file.exists()
    content = output_file.read_text()
    # Host var should be available
    assert "HOST_VAR=host_value" in content
    # Agent env should override host env for SHARED_VAR
    assert "SHARED_VAR=from_agent" in content
