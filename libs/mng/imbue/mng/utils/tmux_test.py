import pytest

from imbue.concurrency_group.concurrency_group import ConcurrencyGroup
from imbue.mng.utils.polling import wait_for
from imbue.mng.utils.testing import get_short_random_string
from imbue.mng.utils.testing import tmux_session_cleanup
from imbue.mng.utils.tmux import ENTER_SUBMISSION_WAIT_FOR_TIMEOUT_SECONDS
from imbue.mng.utils.tmux import TmuxSendError
from imbue.mng.utils.tmux import _send_backspace_with_noop
from imbue.mng.utils.tmux import _send_enter_and_wait_for_signal
from imbue.mng.utils.tmux import capture_tmux_pane
from imbue.mng.utils.tmux import send_message_to_tmux_pane


def test_capture_tmux_pane_returns_content(cg: ConcurrencyGroup) -> None:
    """Test that capture_tmux_pane returns pane content for an active session."""
    session_name = f"mng-test-capture-{get_short_random_string()}"
    cg.run_process_to_completion(
        ["tmux", "new-session", "-d", "-s", session_name, "cat"],
        is_checked_after=False,
    )
    with tmux_session_cleanup(session_name):
        # Wait for cat to start
        wait_for(
            lambda: capture_tmux_pane(session_name, cg) is not None,
            timeout=5.0,
            error_message="pane not available",
        )

        content = capture_tmux_pane(session_name, cg)
        assert content is not None


def test_capture_tmux_pane_returns_none_for_nonexistent_session(cg: ConcurrencyGroup) -> None:
    """Test that capture_tmux_pane returns None for a session that doesn't exist."""
    result = capture_tmux_pane(f"mng-nonexistent-{get_short_random_string()}", cg)
    assert result is None


def test_send_backspace_with_noop_removes_characters(cg: ConcurrencyGroup) -> None:
    """Test that _send_backspace_with_noop sends backspaces and noop keys to tmux session."""
    session_name = f"mng-test-bspace-{get_short_random_string()}"
    cg.run_process_to_completion(
        ["tmux", "new-session", "-d", "-s", session_name, "cat"],
        is_checked_after=False,
    )
    with tmux_session_cleanup(session_name):
        # Wait for cat to start
        wait_for(
            lambda: _pane_current_command(session_name, cg) == "cat",
            timeout=5.0,
            error_message="cat process not ready",
        )

        # Send some text
        cg.run_process_to_completion(
            ["tmux", "send-keys", "-t", session_name, "-l", "hello"],
            is_checked_after=False,
        )

        # Wait for text to appear
        wait_for(
            lambda: "hello" in (capture_tmux_pane(session_name, cg) or ""),
            timeout=5.0,
            error_message="text not visible in pane",
        )

        # Send backspaces with noop - should remove last 2 characters
        _send_backspace_with_noop(session_name, count=2, cg=cg)

        # Verify backspaces were processed ("hello" -> "hel")
        wait_for(
            lambda: "hel" in (capture_tmux_pane(session_name, cg) or ""),
            timeout=5.0,
            error_message="backspaces not processed",
        )
        content = capture_tmux_pane(session_name, cg)
        assert content is not None
        assert "hel" in content


def test_send_enter_and_wait_for_signal_returns_true_when_signaled(cg: ConcurrencyGroup) -> None:
    """Test that _send_enter_and_wait_for_signal returns True when tmux wait-for signal is received."""
    session_name = f"mng-test-signal-{get_short_random_string()}"
    wait_channel = f"mng-submit-{session_name}"

    cg.run_process_to_completion(
        ["tmux", "new-session", "-d", "-s", session_name, "bash"],
        is_checked_after=False,
    )
    with tmux_session_cleanup(session_name):
        # Signal the channel from a background process after a short delay
        # This simulates what the UserPromptSubmit hook does
        cg.run_process_to_completion(
            ["bash", "-c", f"( sleep 0.1 && tmux wait-for -S '{wait_channel}' ) &"],
            is_checked_after=False,
        )

        result = _send_enter_and_wait_for_signal(
            session_name, wait_channel, cg, ENTER_SUBMISSION_WAIT_FOR_TIMEOUT_SECONDS
        )
        assert result is True


def test_send_enter_and_wait_for_signal_returns_false_on_timeout(cg: ConcurrencyGroup) -> None:
    """Test that _send_enter_and_wait_for_signal returns False when signal times out."""
    session_name = f"mng-test-timeout-{get_short_random_string()}"
    # Use a unique channel that won't be signaled
    wait_channel = f"mng-submit-never-signaled-{session_name}"

    cg.run_process_to_completion(
        ["tmux", "new-session", "-d", "-s", session_name, "bash"],
        is_checked_after=False,
    )
    with tmux_session_cleanup(session_name):
        # Use a short timeout so this test doesn't take 10s
        result = _send_enter_and_wait_for_signal(session_name, wait_channel, cg, timeout_seconds=1.0)
        assert result is False


def test_send_message_to_tmux_pane_raises_on_bad_target(cg: ConcurrencyGroup) -> None:
    """Test that send_message_to_tmux_pane raises TmuxSendError for a nonexistent target."""
    bad_target = f"mng-nonexistent-{get_short_random_string()}"
    with pytest.raises(TmuxSendError) as exc_info:
        send_message_to_tmux_pane(bad_target, "hello", cg)
    assert exc_info.value.target == bad_target
    assert "tmux send-keys failed" in exc_info.value.reason


def test_tmux_send_error_formatting() -> None:
    """Test that TmuxSendError formats its message correctly."""
    error = TmuxSendError("my-session:0", "tmux send-keys failed: no such session")
    assert "my-session:0" in str(error)
    assert "tmux send-keys failed: no such session" in str(error)
    assert error.target == "my-session:0"
    assert error.reason == "tmux send-keys failed: no such session"


def _pane_current_command(session_name: str, cg: ConcurrencyGroup) -> str:
    """Get the current command running in a tmux pane."""
    result = cg.run_process_to_completion(
        ["tmux", "list-panes", "-t", session_name, "-F", "#{pane_current_command}"],
        is_checked_after=False,
    )
    return result.stdout.strip() if result.returncode == 0 else ""
