import json
import shlex
import time
from datetime import datetime
from datetime import timezone
from pathlib import Path
from typing import Any
from typing import Final
from typing import Mapping
from typing import Sequence
from uuid import uuid4

from loguru import logger
from pydantic import Field

from imbue.mngr.config.data_types import MngrContext
from imbue.mngr.errors import HostConnectionError
from imbue.mngr.errors import SendMessageError
from imbue.mngr.interfaces.agent import AgentInterface
from imbue.mngr.interfaces.agent import AgentStatus
from imbue.mngr.interfaces.data_types import FileTransferSpec
from imbue.mngr.interfaces.host import CreateAgentOptions
from imbue.mngr.interfaces.host import DEFAULT_AGENT_READY_TIMEOUT_SECONDS
from imbue.mngr.interfaces.host import DEFAULT_ENTER_DELAY_SECONDS
from imbue.mngr.interfaces.host import OnlineHostInterface
from imbue.mngr.primitives import ActivitySource
from imbue.mngr.primitives import AgentLifecycleState
from imbue.mngr.primitives import CommandString
from imbue.mngr.primitives import Permission
from imbue.mngr.utils.env_utils import parse_env_file
from imbue.mngr.utils.polling import poll_until

# Constants for send_message marker-based synchronization
_SEND_MESSAGE_POLL_INTERVAL_SECONDS: Final[float] = 0.05
_SEND_MESSAGE_TIMEOUT_SECONDS: Final[float] = 10.0
_TUI_READY_TIMEOUT_SECONDS: Final[float] = 30.0

# Constants for Enter retry mechanism
_ENTER_SUBMISSION_WAIT_FOR_TIMEOUT_SECONDS: Final[float] = 0.5
_INITIAL_BACKSPACE_SETTLE_SECONDS: Final[float] = 0.5
_RETRY_BACKSPACE_SETTLE_SECONDS: Final[float] = 0.2
_PRE_ENTER_DELAY_SECONDS: Final[float] = 0.3


class BaseAgent(AgentInterface):
    """Concrete agent implementation that stores data on the host filesystem."""

    host: OnlineHostInterface = Field(description="The host this agent runs on (must be online)")

    def get_host(self) -> OnlineHostInterface:
        return self.host

    def assemble_command(
        self,
        host: OnlineHostInterface,
        agent_args: tuple[str, ...],
        command_override: CommandString | None,
    ) -> CommandString:
        """Default: command_override or config.command or agent_type, then append cli_args and agent_args.

        If no explicit command is defined, falls back to using the agent_type as a command.
        This allows using arbitrary commands as agent types (e.g., 'mngr create my-agent echo').
        """
        logger.trace("Assembling command for agent {} (type={}) on host {}", self.name, self.agent_type, host.id)
        if command_override is not None:
            base = str(command_override)
        elif self.agent_config.command is not None:
            base = str(self.agent_config.command)
        else:
            # Fall back to using the agent type as a command (documented "Direct command" behavior)
            base = str(self.agent_type)

        parts = [base]
        if self.agent_config.cli_args:
            parts.append(self.agent_config.cli_args)
        if agent_args:
            parts.extend(agent_args)

        command = CommandString(" ".join(parts))
        logger.trace("Assembled command: {}", command)
        return command

    def _get_agent_dir(self) -> Path:
        """Get the agent's state directory path."""
        return self.host.host_dir / "agents" / str(self.id)

    def _get_data_path(self) -> Path:
        """Get the path to the agent's data.json file."""
        return self._get_agent_dir() / "data.json"

    def _read_data(self) -> dict[str, Any]:
        """Read the agent's data.json file."""
        try:
            content = self.host.read_text_file(self._get_data_path())
            return json.loads(content)
        except FileNotFoundError:
            return {}

    def _write_data(self, data: dict[str, Any]) -> None:
        """Write the agent's data.json file and persist to external storage."""
        self.host.write_text_file(self._get_data_path(), json.dumps(data, indent=2))

        # Persist agent data to external storage (e.g., Modal volume)
        self.host.save_agent_data(self.id, data)

    # =========================================================================
    # Certified Field Getters/Setters
    # =========================================================================

    def get_command(self) -> CommandString:
        data = self._read_data()
        cmd = data.get("command")
        return CommandString(cmd) if cmd else CommandString("bash")

    def get_permissions(self) -> list[Permission]:
        data = self._read_data()
        perms = data.get("permissions", [])
        return [Permission(p) for p in perms]

    def set_permissions(self, value: Sequence[Permission]) -> None:
        data = self._read_data()
        data["permissions"] = [str(p) for p in value]
        self._write_data(data)

    def get_is_start_on_boot(self) -> bool:
        data = self._read_data()
        return data.get("start_on_boot", False)

    def set_is_start_on_boot(self, value: bool) -> None:
        data = self._read_data()
        data["start_on_boot"] = value
        self._write_data(data)

    # =========================================================================
    # Interaction
    # =========================================================================

    def is_running(self) -> bool:
        """Check if the agent is currently running."""
        logger.trace("Checking if agent {} is running", self.name)
        pid_path = self._get_agent_dir() / "agent.pid"
        try:
            content = self.host.read_text_file(pid_path)
            pid = int(content.strip())
            result = self.host.execute_command(f"ps -p {pid}", timeout_seconds=5.0)
            is_running = result.success
            logger.trace("Agent {} is_running={} (pid={})", self.name, is_running, pid)
            return is_running
        except (FileNotFoundError, ValueError):
            logger.trace("Agent {} is_running=False (no pid file or invalid)", self.name)
            return False

    def get_lifecycle_state(self) -> AgentLifecycleState:
        """Get the lifecycle state of this agent using tmux format variables.

        This method checks both the foreground process and descendant processes to handle
        complex command constructs (like shell wrappers or fallback commands using ||).
        """
        logger.trace("Getting lifecycle state for agent {}", self.name)
        session_name = f"{self.mngr_ctx.config.prefix}{self.name}"

        # Get pane state and pid in one command using tmux format variables
        # pane_dead: 0 if alive, 1 if dead
        # pane_current_command: basename of the foreground process
        # pane_pid: PID of the pane's shell process
        result = self.host.execute_command(
            f"tmux list-panes -t '{session_name}' "
            f"-F '#{{pane_dead}}|#{{pane_current_command}}|#{{pane_pid}}' 2>/dev/null | head -n 1",
            timeout_seconds=5.0,
        )

        if not result.success or not result.stdout.strip():
            logger.trace("Agent {} lifecycle state: STOPPED (no tmux session)", self.name)
            return AgentLifecycleState.STOPPED

        parts = result.stdout.strip().split("|")
        if len(parts) != 3:
            logger.trace("Agent {} lifecycle state: STOPPED (malformed tmux output)", self.name)
            return AgentLifecycleState.STOPPED

        pane_dead, current_command, pane_pid = parts

        # If pane's main process died, the agent is done
        if pane_dead == "1":
            logger.trace("Agent {} lifecycle state: DONE (pane process died)", self.name)
            return AgentLifecycleState.DONE

        # Check if current command matches expected command (by basename)
        expected_basename = self.get_expected_process_name()
        if current_command == expected_basename:
            return self._check_waiting_state()

        # Current command doesn't match expected - check descendant processes
        # This handles complex shell constructs like "cmd1 || cmd2"
        ps_result = self.host.execute_command(
            "ps -e -o pid=,ppid=,comm= 2>/dev/null",
            timeout_seconds=5.0,
        )

        if ps_result.success:
            descendant_names = self._get_descendant_process_names(pane_pid, ps_result.stdout)

            # Check if any descendant process matches the expected command
            if expected_basename in descendant_names:
                return self._check_waiting_state()

            # Check for non-shell descendant processes
            non_shell_processes = [p for p in descendant_names if not self._is_shell_command(p)]
            if non_shell_processes:
                logger.trace("Agent {} lifecycle state: REPLACED (non-shell descendant processes)", self.name)
                return AgentLifecycleState.REPLACED

        # No matching descendant found
        # If current command is a shell, the agent probably finished or never started (DONE)
        # If it's not a shell, the agent was replaced by something else (REPLACED)
        if self._is_shell_command(current_command):
            logger.trace("Agent {} lifecycle state: DONE (shell command, no agent process)", self.name)
            return AgentLifecycleState.DONE

        logger.trace("Agent {} lifecycle state: REPLACED (unknown process)", self.name)
        return AgentLifecycleState.REPLACED

    def _get_command_basename(self, command: CommandString) -> str:
        """Extract the basename from a command string."""
        # Handle both "sleep 1000" and "/usr/bin/sleep 1000"
        return command.split()[0].split("/")[-1] if command else ""

    def get_expected_process_name(self) -> str:
        """Get the expected process name for lifecycle state detection.

        Subclasses can override this to return a hardcoded process name
        when the command is complex (e.g., shell wrappers with exports).
        """
        return self._get_command_basename(self.get_command())

    def _get_descendant_process_names(self, root_pid: str, ps_output: str) -> list[str]:
        """Get names of all descendant processes from ps output."""
        # Build maps: children_by_ppid and comm_by_pid
        children_by_ppid: dict[str, list[str]] = {}
        comm_by_pid: dict[str, str] = {}

        for line in ps_output.strip().split("\n"):
            line_parts = line.split()
            if len(line_parts) >= 3:
                pid, ppid, comm = line_parts[0], line_parts[1], line_parts[2]
                comm_by_pid[pid] = comm
                if ppid not in children_by_ppid:
                    children_by_ppid[ppid] = []
                children_by_ppid[ppid].append(pid)

        # Find all descendant process names using BFS from root_pid
        descendant_names: list[str] = []
        queue = list(children_by_ppid.get(root_pid, []))
        while queue:
            pid = queue.pop(0)
            if pid in comm_by_pid:
                descendant_names.append(comm_by_pid[pid])
            queue.extend(children_by_ppid.get(pid, []))

        return descendant_names

    def _check_waiting_state(self) -> AgentLifecycleState:
        """Check if the agent is waiting and return WAITING or RUNNING state."""
        waiting_path = self._get_agent_dir() / "waiting"
        try:
            self.host.read_text_file(waiting_path)
            logger.trace("Agent {} lifecycle state: WAITING", self.name)
            return AgentLifecycleState.WAITING
        except FileNotFoundError:
            logger.trace("Agent {} lifecycle state: RUNNING (no waiting file)", self.name)
            return AgentLifecycleState.RUNNING

    def _command_basename_matches(self, current: str, expected: str) -> bool:
        """Check if current command basename matches expected command."""
        # Extract basename from expected command
        # Handle both "sleep 1000" and "/usr/bin/sleep 1000"
        expected_basename = expected.split()[0].split("/")[-1]
        return current == expected_basename

    def _is_shell_command(self, command: str) -> bool:
        """Check if a command string represents a shell."""
        # Common shells - just check the basename directly since
        # pane_current_command gives us the basename already
        shells = ["bash", "sh", "zsh", "fish", "dash", "ksh", "tcsh", "csh"]
        return command in shells

    def get_initial_message(self) -> str | None:
        data = self._read_data()
        return data.get("initial_message")

    def get_resume_message(self) -> str | None:
        data = self._read_data()
        return data.get("resume_message")

    def get_message_delay_seconds(self) -> float:
        data = self._read_data()
        return data.get("message_delay_seconds", DEFAULT_AGENT_READY_TIMEOUT_SECONDS)

    def get_enter_delay_seconds(self) -> float:
        """Get the delay between sending message text and Enter key.

        This can be configured per-agent via `enter_delay_seconds` in data.json.
        """
        data = self._read_data()
        return data.get("enter_delay_seconds", DEFAULT_ENTER_DELAY_SECONDS)

    def send_message(self, message: str) -> None:
        """Send a message to the running agent.

        For agents that echo input to the terminal (like Claude Code), uses a
        marker-based synchronization approach to ensure the message is fully
        received before sending Enter. This avoids race conditions where Enter
        could be interpreted as a literal newline instead of a submit action.

        Subclasses can enable this by overriding uses_marker_based_send_message().
        """
        logger.debug("Sending message to agent {} (length={})", self.name, len(message))
        session_name = f"{self.mngr_ctx.config.prefix}{self.name}"

        if self.uses_marker_based_send_message():
            self._send_message_with_marker(session_name, message)
        else:
            self._send_message_simple(session_name, message)

        logger.trace("Message sent to agent {}", self.name)

    def uses_marker_based_send_message(self) -> bool:
        """Return True to use marker-based synchronization for send_message.

        Marker-based send requires the application to echo input to the terminal.
        This is useful for interactive agents like Claude Code where sending Enter
        immediately after the message text can cause race conditions.

        Returns False by default. Subclasses can override to enable.
        """
        return False

    def get_tui_ready_indicator(self) -> str | None:
        """Return a string that indicates the TUI is ready to accept input.

        This string will be looked for in the terminal pane content before sending
        messages. This is useful for TUIs that take time to initialize after the
        process starts.

        Returns None by default (no TUI readiness check). Subclasses can override.
        """
        return None

    def _send_message_simple(self, session_name: str, message: str) -> None:
        """Send a message without marker-based synchronization."""
        send_msg_cmd = f"tmux send-keys -t '{session_name}' -l {shlex.quote(message)}"
        result = self.host.execute_command(send_msg_cmd)
        if not result.success:
            raise SendMessageError(str(self.name), f"tmux send-keys failed: {result.stderr or result.stdout}")

        # Delay to let the input handler process the text before sending Enter.
        # Without this, Enter can be interpreted as a literal newline instead of submit.
        time.sleep(self.get_enter_delay_seconds())

        send_enter_cmd = f"tmux send-keys -t '{session_name}' Enter"
        result = self.host.execute_command(send_enter_cmd)
        if not result.success:
            raise SendMessageError(str(self.name), f"tmux send-keys Enter failed: {result.stderr or result.stdout}")

    def _send_message_with_marker(self, session_name: str, message: str) -> None:
        """Send a message using marker-based synchronization.

        This approach appends a unique marker to the message, waits for it to appear
        in the terminal, removes it with backspaces, and then sends Enter. This ensures
        the input handler has fully processed the message text before submitting.
        """
        # Wait for TUI to be ready if an indicator is configured
        tui_indicator = self.get_tui_ready_indicator()
        if tui_indicator is not None:
            self._wait_for_tui_ready(session_name, tui_indicator)

        # Generate a unique marker to detect when the message has been fully received
        # Using just the UUID without newlines - newlines are harder to reliably delete
        # with backspace in some input areas
        marker = uuid4().hex
        message_with_marker = message + marker

        # Send the message with marker
        send_msg_cmd = f"tmux send-keys -t '{session_name}' -l {shlex.quote(message_with_marker)}"
        result = self.host.execute_command(send_msg_cmd)
        if not result.success:
            raise SendMessageError(str(self.name), f"tmux send-keys failed: {result.stderr or result.stdout}")

        # Wait for the marker to appear in the pane (confirms message was fully received)
        self._wait_for_marker_visible(session_name, marker)

        # Remove the marker by sending backspaces (32 hex chars for UUID)
        # Send backspaces and noop keys to clean up the marker
        self._send_backspace_with_noop(session_name, count=len(marker), settle_delay=_INITIAL_BACKSPACE_SETTLE_SECONDS)

        # Verify the marker is gone and the message ends correctly
        # Use the last 20 chars of the message as the expected ending (or full message if shorter)
        expected_ending = message[-20:] if len(message) > 20 else message
        self._wait_for_message_ending(session_name, marker, expected_ending)

        # Add a small delay after the display looks correct, before sending Enter.
        # The terminal display can update before Claude Code's input handler has fully
        # processed the backspaces. We use a short delay here since the retry mechanism
        # will handle any failures.
        logger.debug("Waiting {}s before sending Enter", _PRE_ENTER_DELAY_SECONDS)
        time.sleep(_PRE_ENTER_DELAY_SECONDS)

        # Send Enter with retry logic. Sometimes Enter is interpreted as a literal newline
        # instead of a submit action. We detect this by checking if the message is still
        # in the input area after sending Enter, and retry if so.
        self._send_enter_with_retry(session_name, expected_ending)

    def _send_backspace_with_noop(self, session_name: str, count: int = 1, settle_delay: float | None = None) -> None:
        """Send backspace(s) followed by noop keys to reset input handler state.

        This helper:
        1. Sends the specified number of backspaces
        2. Waits for the input handler to settle
        3. Sends a no-op key sequence (Right then Left) to reset state

        The noop keys are necessary because Claude Code's input handler can get into
        a state after backspaces where Enter is interpreted as a literal newline.
        Sending any key (even a no-op) before Enter fixes this.

        Args:
            session_name: The tmux session name
            count: Number of backspaces to send
            settle_delay: How long to wait after backspaces. If None, uses get_enter_delay_seconds()
        """
        if count > 0:
            backspace_keys = " ".join(["BSpace"] * count)
            backspace_cmd = f"tmux send-keys -t '{session_name}' {backspace_keys}"
            result = self.host.execute_command(backspace_cmd)
            if not result.success:
                raise SendMessageError(
                    str(self.name), f"tmux send-keys BSpace failed: {result.stderr or result.stdout}"
                )

        # Give Claude Code's input handler time to process the backspaces
        delay = settle_delay if settle_delay is not None else self.get_enter_delay_seconds()
        logger.debug("Waiting {}s for backspaces to settle", delay)
        time.sleep(delay)

        # Send a no-op key sequence (Right then Left) to reset input handler state
        noop_cmd = f"tmux send-keys -t '{session_name}' Right Left"
        result = self.host.execute_command(noop_cmd)
        if not result.success:
            logger.warning("Failed to send noop keys: {}", result.stderr or result.stdout)

    def _capture_pane_content(self, session_name: str) -> str | None:
        """Capture the current pane content, returning None on failure."""
        result = self.host.execute_command(
            f"tmux capture-pane -t '{session_name}' -p",
            timeout_seconds=5.0,
        )
        if result.success:
            return result.stdout.rstrip()
        return None

    def _wait_for_tui_ready(self, session_name: str, indicator: str) -> None:
        """Wait until the TUI is ready by looking for the indicator string in the pane.

        This ensures the application's UI is fully rendered before we send input.
        Without this check, input sent too early may be lost or appear as raw text
        instead of being processed by the application's input handler.
        """
        logger.debug("Waiting for TUI to be ready (looking for: {})", indicator)
        if not poll_until(
            lambda: self._check_pane_contains(session_name, indicator),
            timeout=_TUI_READY_TIMEOUT_SECONDS,
            poll_interval=_SEND_MESSAGE_POLL_INTERVAL_SECONDS,
        ):
            raise SendMessageError(
                str(self.name),
                f"Timeout waiting for TUI to be ready (waited {_TUI_READY_TIMEOUT_SECONDS:.1f}s)",
            )
        logger.debug("TUI ready indicator found: {}", indicator)

    def _wait_for_marker_visible(self, session_name: str, marker: str) -> None:
        """Wait until the marker is visible in the tmux pane.

        Note: We check if marker is IN the pane, not at the end, because
        Claude Code has a status line at the bottom that appears after the input area.
        """
        logger.trace("Waiting for marker: {}", marker)
        if not poll_until(
            lambda: self._check_pane_contains(session_name, marker),
            timeout=_SEND_MESSAGE_TIMEOUT_SECONDS,
            poll_interval=_SEND_MESSAGE_POLL_INTERVAL_SECONDS,
        ):
            raise SendMessageError(
                str(self.name),
                f"Timeout waiting for message marker to appear (waited {_SEND_MESSAGE_TIMEOUT_SECONDS:.1f}s)",
            )
        logger.debug("Marker {} found in pane", marker)

    def _check_pane_contains(self, session_name: str, text: str) -> bool:
        """Check if the pane content contains the given text."""
        content = self._capture_pane_content(session_name)
        found = content is not None and text in content
        return found

    def _wait_for_message_ending(self, session_name: str, marker: str, expected_ending: str) -> None:
        """Wait until the marker is removed and the expected message ending is visible.

        Note: We check if expected_ending is IN the pane, not at the end, because
        Claude Code has a status line at the bottom that appears after the input area.
        """
        if not poll_until(
            lambda: self._check_marker_removed_and_contains(session_name, marker, expected_ending),
            timeout=_SEND_MESSAGE_TIMEOUT_SECONDS,
            poll_interval=_SEND_MESSAGE_POLL_INTERVAL_SECONDS,
        ):
            raise SendMessageError(
                str(self.name),
                f"Timeout waiting for message to be ready for submission (waited {_SEND_MESSAGE_TIMEOUT_SECONDS:.1f}s)",
            )
        logger.trace("Marker removed and expected content visible in pane")

    def _check_marker_removed_and_contains(self, session_name: str, marker: str, expected_ending: str) -> bool:
        """Check if the marker is gone and pane contains expected content."""
        content = self._capture_pane_content(session_name)
        if content is None:
            return False
        marker_gone = marker not in content
        contains_expected = expected_ending in content
        return marker_gone and contains_expected

    def _send_enter_with_retry(self, session_name: str, expected_ending: str, max_retries: int = 10) -> None:
        """Send Enter to submit the message, with retry logic for reliability.

        Uses tmux wait-for to detect when the UserPromptSubmit hook fires, indicating
        Claude started processing the message. If Enter was interpreted as a literal
        newline instead of submit, we clean up with backspace + noop keys and retry.
        """
        wait_channel = f"mngr-submit-{session_name}"

        for attempt in range(max_retries):
            # Send Enter and wait for signal (starts waiting BEFORE sending to avoid race)
            if self._send_enter_and_wait_for_signal(session_name, wait_channel):
                logger.debug("Message submitted successfully on attempt {}", attempt + 1)
                return

            # Timed out waiting for signal - Enter was likely interpreted as newline
            logger.debug(
                "Enter may have been interpreted as newline (attempt {}), cleaning up and retrying...",
                attempt + 1,
            )

            # Clean up the accidental newline with backspace, then send noop keys to reset state
            self._send_backspace_with_noop(session_name, count=1, settle_delay=_RETRY_BACKSPACE_SETTLE_SECONDS)

        # All retries exhausted - raise an error
        raise SendMessageError(
            str(self.name),
            f"Failed to submit message after {max_retries} attempts - Enter keeps being interpreted as newline",
        )

    def _send_enter_and_wait_for_signal(self, session_name: str, wait_channel: str) -> bool:
        """Send Enter and wait for the tmux wait-for signal from the hook.

        This starts waiting BEFORE sending Enter to avoid a race condition where
        the hook might fire before we start listening for the signal.

        The sequence is:
        1. Start tmux wait-for in background
        2. Send Enter
        3. Wait for the background wait-for to complete (with timeout)

        Returns True if signal received, False if timeout.
        """
        timeout_iterations = int(_ENTER_SUBMISSION_WAIT_FOR_TIMEOUT_SECONDS * 100)
        cmd = (
            f"bash -c '"
            f'tmux wait-for "$0" & W=$!; '
            f'tmux send-keys -t "$1" Enter; '
            f"for i in $(seq 1 {timeout_iterations}); do "
            f"kill -0 $W 2>/dev/null || exit 0; "
            f"sleep 0.01; "
            f"done; "
            f"kill $W 2>/dev/null; exit 1"
            f"' {shlex.quote(wait_channel)} {shlex.quote(session_name)}"
        )
        result = self.host.execute_command(cmd, timeout_seconds=_ENTER_SUBMISSION_WAIT_FOR_TIMEOUT_SECONDS + 1)
        if result.success:
            logger.debug("Received submission signal on channel {}", wait_channel)
            return True
        logger.debug("Timeout waiting for submission signal on channel {}", wait_channel)
        return False

    # =========================================================================
    # Status (Reported)
    # =========================================================================

    def get_reported_url(self) -> str | None:
        status_path = self._get_agent_dir() / "status" / "url"
        try:
            return self.host.read_text_file(status_path).strip()
        except FileNotFoundError:
            return None

    def get_reported_start_time(self) -> datetime | None:
        status_path = self._get_agent_dir() / "status" / "start_time"
        try:
            content = self.host.read_text_file(status_path).strip()
            return datetime.fromisoformat(content)
        except FileNotFoundError:
            return None

    def get_reported_status_markdown(self) -> str | None:
        status_path = self._get_agent_dir() / "status" / "status.md"
        try:
            return self.host.read_text_file(status_path)
        except FileNotFoundError:
            return None

    def get_reported_status_html(self) -> str | None:
        status_path = self._get_agent_dir() / "status" / "status.html"
        try:
            return self.host.read_text_file(status_path)
        except FileNotFoundError:
            return None

    def get_reported_status(self) -> AgentStatus | None:
        """Get the agent's reported status."""
        status_markdown = self.get_reported_status_markdown()
        status_html = self.get_reported_status_html()
        status_line = status_markdown.split("\n")[0] if status_markdown else None

        if status_line or status_markdown or status_html:
            return AgentStatus(
                line=status_line or "",
                full=status_markdown or "",
                html=status_html,
            )

        return None

    # =========================================================================
    # Activity
    # =========================================================================

    def get_reported_activity_time(self, activity_type: ActivitySource) -> datetime | None:
        """Return the last activity time using file modification time.

        Activity time is determined by mtime, not by parsing the JSON content.
        This ensures consistency across all activity writers (Python, bash, lua)
        and allows simple scripts to just touch files without writing JSON.
        """
        activity_path = self._get_agent_dir() / "activity" / activity_type.value.lower()
        return self.host.get_file_mtime(activity_path)

    def record_activity(self, activity_type: ActivitySource) -> None:
        """Record activity by writing JSON with timestamp and metadata.

        The JSON contains:
        - time: milliseconds since Unix epoch (int)
        - agent_id: the agent's ID (for debugging)
        - agent_name: the agent's name (for debugging)

        Note: The authoritative activity time is the file's mtime, not the
        JSON content. The JSON is for debugging/auditing purposes.
        """
        logger.trace("Recording {} activity for agent {}", activity_type, self.name)
        activity_path = self._get_agent_dir() / "activity" / activity_type.value.lower()
        now = datetime.now(timezone.utc)
        data = {
            "time": int(now.timestamp() * 1000),
            "agent_id": str(self.id),
            "agent_name": str(self.name),
        }
        self.host.write_text_file(activity_path, json.dumps(data, indent=2))

    def get_reported_activity_record(self, activity_type: ActivitySource) -> str | None:
        activity_path = self._get_agent_dir() / "activity" / activity_type.value.lower()
        try:
            return self.host.read_text_file(activity_path)
        except FileNotFoundError:
            return None

    # =========================================================================
    # Plugin Data (Certified)
    # =========================================================================

    def get_plugin_data(self, plugin_name: str) -> dict[str, Any]:
        data = self._read_data()
        plugin_data = data.get("plugin", {})
        return plugin_data.get(plugin_name, {})

    def set_plugin_data(self, plugin_name: str, data: dict[str, Any]) -> None:
        agent_data = self._read_data()
        if "plugin" not in agent_data:
            agent_data["plugin"] = {}
        agent_data["plugin"][plugin_name] = data
        self._write_data(agent_data)

    # =========================================================================
    # Plugin Data (Reported)
    # =========================================================================

    def get_reported_plugin_file(self, plugin_name: str, filename: str) -> str:
        plugin_path = self._get_agent_dir() / "plugin" / plugin_name / filename
        return self.host.read_text_file(plugin_path)

    def set_reported_plugin_file(self, plugin_name: str, filename: str, data: str) -> None:
        plugin_path = self._get_agent_dir() / "plugin" / plugin_name / filename
        self.host.write_text_file(plugin_path, data)

    def list_reported_plugin_files(self, plugin_name: str) -> list[str]:
        plugin_dir = self._get_agent_dir() / "plugin" / plugin_name
        try:
            result = self.host.execute_command(f"ls -1 '{plugin_dir}'", timeout_seconds=5.0)
            if result.success:
                return [f.strip() for f in result.stdout.split("\n") if f.strip()]
            return []
        except (OSError, HostConnectionError):
            return []

    # =========================================================================
    # Environment
    # =========================================================================

    def get_env_vars(self) -> dict[str, str]:
        env_path = self._get_agent_dir() / "environment"
        try:
            content = self.host.read_text_file(env_path)
            return parse_env_file(content)
        except FileNotFoundError:
            return {}

    def set_env_vars(self, env: Mapping[str, str]) -> None:
        lines = [f"{key}={value}" for key, value in env.items()]
        content = "\n".join(lines) + "\n" if lines else ""
        env_path = self._get_agent_dir() / "environment"
        self.host.write_text_file(env_path, content)

    def get_env_var(self, key: str) -> str | None:
        env = self.get_env_vars()
        return env.get(key)

    def set_env_var(self, key: str, value: str) -> None:
        env = self.get_env_vars()
        env[key] = value
        self.set_env_vars(env)

    # =========================================================================
    # Computed Properties
    # =========================================================================

    @property
    def runtime_seconds(self) -> float | None:
        start_time = self.get_reported_start_time()
        if start_time is None:
            return None
        now = datetime.now(timezone.utc)
        return (now - start_time).total_seconds()

    # =========================================================================
    # Provisioning Lifecycle
    # =========================================================================

    def on_before_provisioning(
        self,
        host: OnlineHostInterface,
        options: CreateAgentOptions,
        mngr_ctx: MngrContext,
    ) -> None:
        """Default implementation: no-op.

        Subclasses can override to validate preconditions before provisioning.
        """

    def get_provision_file_transfers(
        self,
        host: OnlineHostInterface,
        options: CreateAgentOptions,
        mngr_ctx: MngrContext,
    ) -> Sequence[FileTransferSpec]:
        """Default implementation: no file transfers.

        Subclasses can override to declare files to transfer during provisioning.
        """
        return []

    def provision(
        self,
        host: OnlineHostInterface,
        options: CreateAgentOptions,
        mngr_ctx: MngrContext,
    ) -> None:
        """Default implementation: no-op.

        Subclasses can override to perform agent-type-specific provisioning.
        """

    def on_after_provisioning(
        self,
        host: OnlineHostInterface,
        options: CreateAgentOptions,
        mngr_ctx: MngrContext,
    ) -> None:
        """Default implementation: no-op.

        Subclasses can override to perform finalization after provisioning.
        """
