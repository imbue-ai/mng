import shlex
from collections.abc import Callable
from collections.abc import Sequence
from typing import Final
from uuid import uuid4

from loguru import logger
from pydantic import ConfigDict
from pydantic import Field

from imbue.concurrency_group.concurrency_group import ConcurrencyGroup
from imbue.imbue_common.frozen_model import FrozenModel
from imbue.imbue_common.logging import log_span
from imbue.imbue_common.mutable_model import MutableModel
from imbue.mng.errors import BaseMngError
from imbue.mng.interfaces.host import OnlineHostInterface
from imbue.mng.utils.polling import poll_until

# Constants for send_message marker-based synchronization
SEND_MESSAGE_TIMEOUT_SECONDS: Final[float] = 10.0
CAPTURE_PANE_TIMEOUT_SECONDS: Final[float] = 5.0

# Constants for signal-based synchronization
# Note that this does need to be fairly long, since it can take a little while for the machine to respond if you're unlucky
ENTER_SUBMISSION_WAIT_FOR_TIMEOUT_SECONDS: Final[float] = 10.0


class TmuxCommandResult(FrozenModel):
    """Result of running a shell command for tmux operations."""

    is_success: bool = Field(description="Whether the command exited successfully")
    stdout: str = Field(description="Standard output")
    stderr: str = Field(description="Standard error")


# A callable that runs a shell command (as a list of args) with an optional timeout
# and returns the result. This abstraction allows the same tmux protocol to work
# over both local subprocesses (via ConcurrencyGroup) and remote hosts (via SSH).
TmuxCommandRunner = Callable[[Sequence[str], float | None], TmuxCommandResult]


class TmuxSendError(BaseMngError):
    """Failed to send a message to a tmux pane."""

    def __init__(self, target: str, reason: str) -> None:
        self.target = target
        self.reason = reason
        super().__init__(f"Failed to send message to tmux pane {target}: {reason}")


class CgCommandRunner(MutableModel):
    """TmuxCommandRunner that runs commands via a ConcurrencyGroup (local subprocess)."""

    model_config = ConfigDict(arbitrary_types_allowed=True)
    cg: ConcurrencyGroup = Field(frozen=True, description="ConcurrencyGroup for running processes")

    def __call__(self, args: Sequence[str], timeout: float | None) -> TmuxCommandResult:
        result = self.cg.run_process_to_completion(
            list(args),
            timeout=timeout,
            is_checked_after=False,
        )
        return TmuxCommandResult(
            is_success=result.returncode == 0,
            stdout=result.stdout,
            stderr=result.stderr,
        )


class HostCommandRunner(MutableModel):
    """TmuxCommandRunner that runs commands via a host (supports SSH)."""

    model_config = ConfigDict(arbitrary_types_allowed=True)
    host: OnlineHostInterface = Field(frozen=True, description="Host for executing commands")

    def __call__(self, args: Sequence[str], timeout: float | None) -> TmuxCommandResult:
        cmd_str = shlex.join(args)
        result = (
            self.host.execute_command(cmd_str, timeout_seconds=timeout)
            if timeout is not None
            else self.host.execute_command(cmd_str)
        )
        return TmuxCommandResult(
            is_success=result.success,
            stdout=result.stdout,
            stderr=result.stderr,
        )


def make_cg_command_runner(cg: ConcurrencyGroup) -> TmuxCommandRunner:
    """Create a TmuxCommandRunner that runs commands via a ConcurrencyGroup."""
    return CgCommandRunner(cg=cg)


def make_host_command_runner(host: OnlineHostInterface) -> TmuxCommandRunner:
    """Create a TmuxCommandRunner that runs commands via a host (supports SSH)."""
    return HostCommandRunner(host=host)


def send_message_to_tmux_pane(target: str, message: str, run_command: TmuxCommandRunner) -> None:
    """Send a message to a tmux pane using marker-based synchronization.

    This approach appends a unique marker to the message, waits for it to appear
    in the terminal, removes it with backspaces, and then sends Enter. This ensures
    the input handler has fully processed the message text before submitting.

    On failure (e.g. marker visibility or submission timeout), partial text
    including the marker may remain in the input field. We intentionally do not
    attempt cleanup because deleting text risks accidentally removing part of
    the user's message -- leaving stale marker text is safer than data loss.
    """
    # Generate a unique marker to detect when the message has been fully received
    marker = uuid4().hex
    message_with_marker = message + marker

    # Send the message with marker
    result = run_command(["tmux", "send-keys", "-t", target, "-l", message_with_marker], None)
    if not result.is_success:
        raise TmuxSendError(target, f"tmux send-keys failed: {result.stderr or result.stdout}")

    # Wait for the marker to appear in the pane (confirms message was fully received)
    _wait_for_marker_visible(target, marker, run_command)

    # Remove the marker by sending backspaces (32 hex chars for UUID)
    _send_backspace_with_noop(target, count=len(marker), run_command=run_command)

    # Verify the marker is gone and the message ends correctly
    # Use the tail of the last line of the message as the expected ending, since
    # only that portion is visible on the current input line in the tmux pane.
    last_line = message.rsplit("\n", 1)[-1]
    expected_ending = last_line[-32:] if len(last_line) > 32 else last_line
    _wait_for_message_ending(target, marker, expected_ending, run_command)

    # Send Enter and wait for submission signal
    _send_enter_and_wait(target, run_command)


def capture_tmux_pane(target: str, run_command: TmuxCommandRunner) -> str | None:
    """Capture the current pane content, returning None on failure."""
    result = run_command(["tmux", "capture-pane", "-t", target, "-p"], CAPTURE_PANE_TIMEOUT_SECONDS)
    if result.is_success:
        return result.stdout.rstrip()
    return None


def _send_backspace_with_noop(target: str, count: int, run_command: TmuxCommandRunner) -> None:
    """Send backspace(s) followed by noop keys to reset input handler state.

    The noop keys are necessary because Claude Code's input handler can get into
    a state after backspaces where Enter is interpreted as a literal newline.
    Sending any key (even a no-op) before Enter fixes this.
    """
    if count > 0:
        backspace_keys = ["BSpace"] * count
        result = run_command(["tmux", "send-keys", "-t", target, *backspace_keys], None)
        if not result.is_success:
            raise TmuxSendError(target, f"tmux send-keys BSpace failed: {result.stderr or result.stdout}")

    # Send a no-op key sequence (Left then Right) to reset input handler state
    result = run_command(["tmux", "send-keys", "-t", target, "Left", "Right"], None)
    if not result.is_success:
        logger.warning("Failed to send noop keys: {}", result.stderr or result.stdout)


def _check_pane_contains(target: str, text: str, run_command: TmuxCommandRunner) -> bool:
    """Check if the pane content contains the given text."""
    content = capture_tmux_pane(target, run_command)
    return content is not None and text in content


def _wait_for_marker_visible(target: str, marker: str, run_command: TmuxCommandRunner) -> None:
    """Wait until the marker is visible in the tmux pane.

    Note: We check if marker is IN the pane, not at the end, because
    Claude Code has a status line at the bottom that appears after the input area.
    """
    with log_span("Waiting for marker: {}", marker):
        if not poll_until(
            lambda: _check_pane_contains(target, marker, run_command),
            timeout=SEND_MESSAGE_TIMEOUT_SECONDS,
        ):
            raise TmuxSendError(
                target,
                f"Timeout waiting for message marker to appear (waited {SEND_MESSAGE_TIMEOUT_SECONDS:.1f}s)",
            )


def _wait_for_message_ending(target: str, marker: str, expected_ending: str, run_command: TmuxCommandRunner) -> None:
    """Wait until the marker is removed and the expected message ending is visible.

    Note: We check if expected_ending is IN the pane, not at the end, because
    Claude Code has a status line at the bottom that appears after the input area.
    """
    if not poll_until(
        lambda: _check_marker_removed_and_contains(target, marker, expected_ending, run_command),
        timeout=SEND_MESSAGE_TIMEOUT_SECONDS,
    ):
        raise TmuxSendError(
            target,
            f"Timeout waiting for message to be ready for submission (waited {SEND_MESSAGE_TIMEOUT_SECONDS:.1f}s)",
        )
    logger.trace("Verified marker removed and expected content visible in pane")


def _check_marker_removed_and_contains(
    target: str, marker: str, expected_ending: str, run_command: TmuxCommandRunner
) -> bool:
    """Check if the marker is gone and pane contains expected content."""
    content = capture_tmux_pane(target, run_command)
    if content is None:
        return False
    is_marker_gone = marker not in content
    is_contains_expected = expected_ending in content
    return is_marker_gone and is_contains_expected


def _send_enter_and_wait(target: str, run_command: TmuxCommandRunner) -> None:
    """Send Enter to submit the message and wait for the submission signal.

    Uses tmux wait-for to detect when the UserPromptSubmit hook fires.
    Raises TmuxSendError if the signal is not received within the timeout.
    """
    wait_channel = f"mng-submit-{target}"
    if _send_enter_and_wait_for_signal(target, wait_channel, run_command, ENTER_SUBMISSION_WAIT_FOR_TIMEOUT_SECONDS):
        logger.debug("Message submitted successfully")
        return

    pane_content = capture_tmux_pane(target, run_command)
    if pane_content is not None:
        logger.error(
            "TUI send enter and wait timeout -- pane content:\n{}",
            pane_content,
        )
    else:
        logger.error("TUI send enter and wait timeout -- failed to capture pane content")

    raise TmuxSendError(
        target,
        f"Timeout waiting for message submission signal (waited {ENTER_SUBMISSION_WAIT_FOR_TIMEOUT_SECONDS}s)",
    )


def _send_enter_and_wait_for_signal(
    target: str, wait_channel: str, run_command: TmuxCommandRunner, timeout_seconds: float
) -> bool:
    """Send Enter and wait for the tmux wait-for signal from the hook.

    This starts waiting BEFORE sending Enter to avoid a race condition where
    the hook might fire before we start listening for the signal.

    The sequence is:
    1. Start tmux wait-for (with timeout) in background
    2. Send Enter
    3. Wait for the background process to complete

    Returns True if signal received, False if timeout.
    """
    result = run_command(
        [
            "bash",
            "-c",
            'timeout $0 tmux wait-for "$1" & W=$!; tmux send-keys -t "$2" Enter; wait $W',
            str(timeout_seconds),
            wait_channel,
            target,
        ],
        timeout_seconds + 1,
    )
    if result.is_success:
        logger.trace("Received submission signal")
        return True
    logger.debug("Timeout waiting for submission signal on channel {}", wait_channel)
    return False
