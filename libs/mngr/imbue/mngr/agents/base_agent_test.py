"""Tests for BaseAgent."""

import json
from pathlib import Path

from imbue.mngr.conftest import create_test_base_agent
from imbue.mngr.interfaces.host import DEFAULT_AGENT_READY_TIMEOUT_SECONDS
from imbue.mngr.primitives import AgentLifecycleState
from imbue.mngr.providers.local.instance import LocalProviderInstance
from imbue.mngr.utils.polling import wait_for
from imbue.mngr.utils.testing import cleanup_tmux_session


def test_lifecycle_state_stopped_when_no_tmux_session(
    local_provider: LocalProviderInstance,
    temp_host_dir: Path,
    temp_work_dir: Path,
) -> None:
    """Test that agent is STOPPED when there is no tmux session."""
    test_agent = create_test_base_agent(local_provider, temp_host_dir, temp_work_dir)
    state = test_agent.get_lifecycle_state()
    assert state == AgentLifecycleState.STOPPED


def test_lifecycle_state_running_when_expected_process_exists(
    local_provider: LocalProviderInstance,
    temp_host_dir: Path,
    temp_work_dir: Path,
) -> None:
    """Test that agent is RUNNING when tmux session exists with expected process and active file."""
    test_agent = create_test_base_agent(local_provider, temp_host_dir, temp_work_dir)
    session_name = f"{test_agent.mngr_ctx.config.prefix}{test_agent.name}"

    # Create a tmux session and run the expected command
    test_agent.host.execute_command(
        f"tmux new-session -d -s '{session_name}' 'sleep 1000'",
        timeout_seconds=5.0,
    )

    # Create the active file in the agent's state directory (signals RUNNING)
    agent_dir = temp_host_dir / "agents" / str(test_agent.id)
    active_file = agent_dir / "active"
    active_file.write_text("")

    try:
        # Poll for up to 5 seconds for the state to become RUNNING
        # There's a race condition where the process might not be fully started yet
        wait_for(
            lambda: test_agent.get_lifecycle_state() == AgentLifecycleState.RUNNING,
            error_message="Expected agent lifecycle state to be RUNNING",
        )
    finally:
        # Clean up tmux session and all its processes
        cleanup_tmux_session(session_name)


def test_lifecycle_state_replaced_when_different_process_exists(
    local_provider: LocalProviderInstance,
    temp_host_dir: Path,
    temp_work_dir: Path,
) -> None:
    """Test that agent is REPLACED when tmux session exists with different process."""
    test_agent = create_test_base_agent(local_provider, temp_host_dir, temp_work_dir)
    session_name = f"{test_agent.mngr_ctx.config.prefix}{test_agent.name}"

    # Create a tmux session with a different command (cat waits for input indefinitely)
    test_agent.host.execute_command(
        f"tmux new-session -d -s '{session_name}' 'cat'",
        timeout_seconds=5.0,
    )

    try:
        # Poll for up to 5 seconds for the state to become REPLACED
        # There's a race condition where tmux spawns a shell first, then execs the command.
        # During that brief window, pane_current_command shows the shell, giving DONE.
        wait_for(
            lambda: test_agent.get_lifecycle_state() == AgentLifecycleState.REPLACED,
            error_message="Expected agent lifecycle state to be REPLACED",
        )
    finally:
        # Clean up tmux session and all its processes
        cleanup_tmux_session(session_name)


def test_lifecycle_state_done_when_no_process_in_pane(
    local_provider: LocalProviderInstance,
    temp_host_dir: Path,
    temp_work_dir: Path,
) -> None:
    """Test that agent is DONE when tmux session exists but no process is running."""
    test_agent = create_test_base_agent(local_provider, temp_host_dir, temp_work_dir)
    session_name = f"{test_agent.mngr_ctx.config.prefix}{test_agent.name}"

    # Create a tmux session, then manually stop the process inside it
    # First create it with a long-running command
    test_agent.host.execute_command(
        f"tmux new-session -d -s '{session_name}'",
        timeout_seconds=5.0,
    )

    # The tmux session now has a shell with no child processes (DONE state)
    try:
        # Poll for up to 5 seconds for the state to become DONE
        # There's a race condition where tmux may have brief child processes during init
        wait_for(
            lambda: test_agent.get_lifecycle_state() == AgentLifecycleState.DONE,
            error_message="Expected agent lifecycle state to be DONE",
        )
    finally:
        # Clean up tmux session and all its processes
        cleanup_tmux_session(session_name)


def test_get_reported_status_returns_none_when_no_status_files(
    local_provider: LocalProviderInstance,
    temp_host_dir: Path,
    temp_work_dir: Path,
) -> None:
    """Test that get_reported_status returns None when no status files exist."""
    test_agent = create_test_base_agent(local_provider, temp_host_dir, temp_work_dir)
    status = test_agent.get_reported_status()
    assert status is None


def test_get_reported_status_returns_status_with_markdown_only(
    local_provider: LocalProviderInstance,
    temp_host_dir: Path,
    temp_work_dir: Path,
) -> None:
    """Test that get_reported_status returns AgentStatus with markdown content."""
    test_agent = create_test_base_agent(local_provider, temp_host_dir, temp_work_dir)
    agent_dir = temp_host_dir / "agents" / str(test_agent.id)
    status_dir = agent_dir / "status"
    status_dir.mkdir(parents=True, exist_ok=True)

    markdown_content = "Agent is running\nProcessing task 123"
    (status_dir / "status.md").write_text(markdown_content)

    status = test_agent.get_reported_status()
    assert status is not None
    assert status.line == "Agent is running"
    assert status.full == markdown_content
    assert status.html is None


def test_get_reported_status_returns_status_with_html_and_markdown(
    local_provider: LocalProviderInstance,
    temp_host_dir: Path,
    temp_work_dir: Path,
) -> None:
    """Test that get_reported_status returns AgentStatus with both markdown and html."""
    test_agent = create_test_base_agent(local_provider, temp_host_dir, temp_work_dir)
    agent_dir = temp_host_dir / "agents" / str(test_agent.id)
    status_dir = agent_dir / "status"
    status_dir.mkdir(parents=True, exist_ok=True)

    markdown_content = "Agent is running\nProcessing task 123"
    html_content = "<html><body><h1>Agent is running</h1><p>Processing task 123</p></body></html>"
    (status_dir / "status.md").write_text(markdown_content)
    (status_dir / "status.html").write_text(html_content)

    status = test_agent.get_reported_status()
    assert status is not None
    assert status.line == "Agent is running"
    assert status.full == markdown_content
    assert status.html == html_content


def test_lifecycle_state_waiting_when_no_active_file(
    local_provider: LocalProviderInstance,
    temp_host_dir: Path,
    temp_work_dir: Path,
) -> None:
    """Test that agent is WAITING when tmux session exists with expected process but no active file."""
    test_agent = create_test_base_agent(local_provider, temp_host_dir, temp_work_dir)
    session_name = f"{test_agent.mngr_ctx.config.prefix}{test_agent.name}"

    # Create a tmux session and run the expected command
    test_agent.host.execute_command(
        f"tmux new-session -d -s '{session_name}' 'sleep 1000'",
        timeout_seconds=5.0,
    )

    # No active file is created, so agent should be WAITING

    try:
        # Poll for up to 5 seconds for the state to become WAITING
        wait_for(
            lambda: test_agent.get_lifecycle_state() == AgentLifecycleState.WAITING,
            error_message="Expected agent lifecycle state to be WAITING",
        )
    finally:
        # Clean up tmux session and all its processes
        cleanup_tmux_session(session_name)


def test_lifecycle_state_running_when_active_file_created(
    local_provider: LocalProviderInstance,
    temp_host_dir: Path,
    temp_work_dir: Path,
) -> None:
    """Test that agent transitions from WAITING to RUNNING when active file is created."""
    test_agent = create_test_base_agent(local_provider, temp_host_dir, temp_work_dir)
    session_name = f"{test_agent.mngr_ctx.config.prefix}{test_agent.name}"

    # Create a tmux session and run the expected command
    test_agent.host.execute_command(
        f"tmux new-session -d -s '{session_name}' 'sleep 1000'",
        timeout_seconds=5.0,
    )

    agent_dir = temp_host_dir / "agents" / str(test_agent.id)

    try:
        # First verify it's in WAITING state (no active file)
        wait_for(
            lambda: test_agent.get_lifecycle_state() == AgentLifecycleState.WAITING,
            error_message="Expected agent lifecycle state to be WAITING",
        )

        # Create the active file
        active_file = agent_dir / "active"
        active_file.write_text("")

        # Now verify it's in RUNNING state
        wait_for(
            lambda: test_agent.get_lifecycle_state() == AgentLifecycleState.RUNNING,
            error_message="Expected agent lifecycle state to be RUNNING after creating active file",
        )
    finally:
        # Clean up tmux session and all its processes
        cleanup_tmux_session(session_name)


def test_get_initial_message_returns_none_when_not_set(
    local_provider: LocalProviderInstance,
    temp_host_dir: Path,
    temp_work_dir: Path,
) -> None:
    """Test that get_initial_message returns None when not set in data.json."""
    test_agent = create_test_base_agent(local_provider, temp_host_dir, temp_work_dir)
    assert test_agent.get_initial_message() is None


def test_get_initial_message_returns_message_when_set(
    local_provider: LocalProviderInstance,
    temp_host_dir: Path,
    temp_work_dir: Path,
) -> None:
    """Test that get_initial_message returns the message when set in data.json."""
    test_agent = create_test_base_agent(local_provider, temp_host_dir, temp_work_dir)
    agent_dir = temp_host_dir / "agents" / str(test_agent.id)
    data_path = agent_dir / "data.json"

    # Update data.json with initial_message
    data = json.loads(data_path.read_text())
    data["initial_message"] = "Hello from test"
    data_path.write_text(json.dumps(data, indent=2))

    assert test_agent.get_initial_message() == "Hello from test"


def test_get_resume_message_returns_none_when_not_set(
    local_provider: LocalProviderInstance,
    temp_host_dir: Path,
    temp_work_dir: Path,
) -> None:
    """Test that get_resume_message returns None when not set in data.json."""
    test_agent = create_test_base_agent(local_provider, temp_host_dir, temp_work_dir)
    assert test_agent.get_resume_message() is None


def test_get_resume_message_returns_message_when_set(
    local_provider: LocalProviderInstance,
    temp_host_dir: Path,
    temp_work_dir: Path,
) -> None:
    """Test that get_resume_message returns the message when set in data.json."""
    test_agent = create_test_base_agent(local_provider, temp_host_dir, temp_work_dir)
    agent_dir = temp_host_dir / "agents" / str(test_agent.id)
    data_path = agent_dir / "data.json"

    # Update data.json with resume_message
    data = json.loads(data_path.read_text())
    data["resume_message"] = "Welcome back!"
    data_path.write_text(json.dumps(data, indent=2))

    assert test_agent.get_resume_message() == "Welcome back!"


def test_get_ready_timeout_seconds_returns_default_when_not_set(
    local_provider: LocalProviderInstance,
    temp_host_dir: Path,
    temp_work_dir: Path,
) -> None:
    """Test that get_ready_timeout_seconds returns default when not set in data.json."""
    test_agent = create_test_base_agent(local_provider, temp_host_dir, temp_work_dir)
    assert test_agent.get_ready_timeout_seconds() == DEFAULT_AGENT_READY_TIMEOUT_SECONDS


def test_get_ready_timeout_seconds_returns_value_when_set(
    local_provider: LocalProviderInstance,
    temp_host_dir: Path,
    temp_work_dir: Path,
) -> None:
    """Test that get_ready_timeout_seconds returns the value when set in data.json."""
    test_agent = create_test_base_agent(local_provider, temp_host_dir, temp_work_dir)
    agent_dir = temp_host_dir / "agents" / str(test_agent.id)
    data_path = agent_dir / "data.json"

    # Update data.json with ready_timeout_seconds
    data = json.loads(data_path.read_text())
    data["ready_timeout_seconds"] = 2.5
    data_path.write_text(json.dumps(data, indent=2))

    assert test_agent.get_ready_timeout_seconds() == 2.5


def test_get_expected_process_name_uses_command_basename(
    local_provider: LocalProviderInstance,
    temp_host_dir: Path,
    temp_work_dir: Path,
) -> None:
    """Test that get_expected_process_name returns the command basename."""
    test_agent = create_test_base_agent(local_provider, temp_host_dir, temp_work_dir)
    # Default command is "sleep 1000" based on create_test_base_agent
    assert test_agent.get_expected_process_name() == "sleep"


def test_uses_marker_based_send_message_returns_false_by_default(
    local_provider: LocalProviderInstance,
    temp_host_dir: Path,
    temp_work_dir: Path,
) -> None:
    """Test that uses_marker_based_send_message returns False by default."""
    test_agent = create_test_base_agent(local_provider, temp_host_dir, temp_work_dir)
    assert test_agent.uses_marker_based_send_message() is False


def test_get_tui_ready_indicator_returns_none_by_default(
    local_provider: LocalProviderInstance,
    temp_host_dir: Path,
    temp_work_dir: Path,
) -> None:
    """Test that get_tui_ready_indicator returns None by default."""
    test_agent = create_test_base_agent(local_provider, temp_host_dir, temp_work_dir)
    assert test_agent.get_tui_ready_indicator() is None


def test_send_backspace_with_noop_sends_keys_to_tmux(
    local_provider: LocalProviderInstance,
    temp_host_dir: Path,
    temp_work_dir: Path,
) -> None:
    """Test that _send_backspace_with_noop sends backspaces and noop keys to tmux session."""
    test_agent = create_test_base_agent(local_provider, temp_host_dir, temp_work_dir)
    session_name = f"{test_agent.mngr_ctx.config.prefix}{test_agent.name}"

    # Create a tmux session with some text
    test_agent.host.execute_command(
        f"tmux new-session -d -s '{session_name}' 'cat'",
        timeout_seconds=5.0,
    )

    try:
        # Wait for cat to start
        wait_for(
            lambda: test_agent.host.execute_command(
                f"tmux list-panes -t '{session_name}' -F '#{{pane_current_command}}'"
            ).stdout.strip()
            == "cat",
            timeout=5.0,
            error_message="cat process not ready",
        )

        # Send some text
        test_agent.host.execute_command(f"tmux send-keys -t '{session_name}' -l 'hello'")

        # Wait for text to appear
        wait_for(
            lambda: "hello" in (test_agent._capture_pane_content(session_name) or ""),
            timeout=5.0,
            error_message="text not visible in pane",
        )

        # Now send backspaces with noop - should remove some characters
        test_agent._send_backspace_with_noop(session_name, count=2)

        # Verify backspaces were processed (last 2 chars should be removed)
        content = test_agent._capture_pane_content(session_name)
        assert content is not None
        # After backspaces, "hello" should become "hel"
        assert "hel" in content
    finally:
        test_agent.host.execute_command(
            f"tmux kill-session -t '{session_name}' 2>/dev/null",
            timeout_seconds=5.0,
        )


def test_send_enter_and_wait_for_signal_returns_true_when_signal_received(
    local_provider: LocalProviderInstance,
    temp_host_dir: Path,
    temp_work_dir: Path,
) -> None:
    """Test that _send_enter_and_wait_for_signal returns True when tmux wait-for signal is received."""
    test_agent = create_test_base_agent(local_provider, temp_host_dir, temp_work_dir)
    session_name = f"{test_agent.mngr_ctx.config.prefix}{test_agent.name}"
    wait_channel = f"mngr-submit-{session_name}"

    # Create a tmux session
    test_agent.host.execute_command(
        f"tmux new-session -d -s '{session_name}' 'bash'",
        timeout_seconds=5.0,
    )

    try:
        # Signal the channel from a background process after a short delay
        # This simulates what the UserPromptSubmit hook does
        test_agent.host.execute_command(
            f"( sleep 0.1 && tmux wait-for -S '{wait_channel}' ) &",
            timeout_seconds=1.0,
        )

        # Call the method - it should receive the signal and return True
        result = test_agent._send_enter_and_wait_for_signal(session_name, wait_channel)
        assert result is True
    finally:
        test_agent.host.execute_command(
            f"tmux kill-session -t '{session_name}' 2>/dev/null",
            timeout_seconds=5.0,
        )


def test_send_enter_and_wait_for_signal_returns_false_on_timeout(
    local_provider: LocalProviderInstance,
    temp_host_dir: Path,
    temp_work_dir: Path,
) -> None:
    """Test that _send_enter_and_wait_for_signal returns False when signal times out."""
    test_agent = create_test_base_agent(local_provider, temp_host_dir, temp_work_dir)
    session_name = f"{test_agent.mngr_ctx.config.prefix}{test_agent.name}"
    # Use a unique channel that won't be signaled
    wait_channel = f"mngr-submit-never-signaled-{session_name}"

    # Create a tmux session
    test_agent.host.execute_command(
        f"tmux new-session -d -s '{session_name}' 'bash'",
        timeout_seconds=5.0,
    )

    try:
        # Call the method without signaling - should timeout and return False
        result = test_agent._send_enter_and_wait_for_signal(session_name, wait_channel)
        assert result is False
    finally:
        test_agent.host.execute_command(
            f"tmux kill-session -t '{session_name}' 2>/dev/null",
            timeout_seconds=5.0,
        )


# =============================================================================
# get_reported_urls tests
# =============================================================================


def test_get_reported_urls_returns_empty_dict_when_no_urls(
    local_provider: LocalProviderInstance,
    temp_host_dir: Path,
    temp_work_dir: Path,
) -> None:
    test_agent = create_test_base_agent(local_provider, temp_host_dir, temp_work_dir)
    assert test_agent.get_reported_urls() == {}


def test_get_reported_urls_returns_default_url(
    local_provider: LocalProviderInstance,
    temp_host_dir: Path,
    temp_work_dir: Path,
) -> None:
    test_agent = create_test_base_agent(
        local_provider, temp_host_dir, temp_work_dir, reported_urls={"default": "https://example.com/agent"}
    )
    urls = test_agent.get_reported_urls()
    assert urls == {"default": "https://example.com/agent"}


def test_get_reported_urls_returns_multiple_typed_urls(
    local_provider: LocalProviderInstance,
    temp_host_dir: Path,
    temp_work_dir: Path,
) -> None:
    test_agent = create_test_base_agent(
        local_provider,
        temp_host_dir,
        temp_work_dir,
        reported_urls={"terminal": "https://example.com/ttyd", "chat": "https://example.com/chat"},
    )
    urls = test_agent.get_reported_urls()
    assert urls == {"terminal": "https://example.com/ttyd", "chat": "https://example.com/chat"}


def test_get_reported_urls_returns_default_and_typed_urls(
    local_provider: LocalProviderInstance,
    temp_host_dir: Path,
    temp_work_dir: Path,
) -> None:
    test_agent = create_test_base_agent(
        local_provider,
        temp_host_dir,
        temp_work_dir,
        reported_urls={"default": "https://example.com/default", "terminal": "https://example.com/ttyd"},
    )
    urls = test_agent.get_reported_urls()
    assert urls == {
        "default": "https://example.com/default",
        "terminal": "https://example.com/ttyd",
    }


def test_get_reported_url_returns_default_type(
    local_provider: LocalProviderInstance,
    temp_host_dir: Path,
    temp_work_dir: Path,
) -> None:
    test_agent = create_test_base_agent(
        local_provider,
        temp_host_dir,
        temp_work_dir,
        reported_urls={"default": "https://example.com/default", "terminal": "https://example.com/ttyd"},
    )
    assert test_agent.get_reported_url() == "https://example.com/default"


def test_get_reported_url_returns_none_when_no_default(
    local_provider: LocalProviderInstance,
    temp_host_dir: Path,
    temp_work_dir: Path,
) -> None:
    test_agent = create_test_base_agent(
        local_provider,
        temp_host_dir,
        temp_work_dir,
        reported_urls={"terminal": "https://example.com/ttyd"},
    )
    assert test_agent.get_reported_url() is None
