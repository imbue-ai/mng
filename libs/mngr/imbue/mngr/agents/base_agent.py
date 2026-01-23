import json
import shlex
from datetime import datetime
from datetime import timezone
from pathlib import Path
from typing import Any
from typing import Mapping
from typing import Sequence

from loguru import logger
from pydantic import Field

from imbue.mngr.errors import HostConnectionError
from imbue.mngr.errors import NoCommandDefinedError
from imbue.mngr.errors import SendMessageError
from imbue.mngr.interfaces.agent import AgentInterface
from imbue.mngr.interfaces.agent import AgentStatus
from imbue.mngr.interfaces.host import HostInterface
from imbue.mngr.primitives import ActivitySource
from imbue.mngr.primitives import AgentLifecycleState
from imbue.mngr.primitives import CommandString
from imbue.mngr.primitives import Permission
from imbue.mngr.utils.env_utils import parse_env_file


class BaseAgent(AgentInterface):
    """Concrete agent implementation that stores data on the host filesystem."""

    host: HostInterface = Field(description="The host this agent runs on")

    def get_host(self) -> HostInterface:
        return self.host

    def assemble_command(
        self,
        agent_args: tuple[str, ...],
        command_override: CommandString | None,
    ) -> CommandString:
        """Default: command_override or config.command, then append cli_args and agent_args."""
        logger.trace("Assembling command for agent {} (type={})", self.name, self.agent_type)
        if command_override is not None:
            base = str(command_override)
        elif self.agent_config.command is not None:
            base = str(self.agent_config.command)
        else:
            raise NoCommandDefinedError(f"No command defined for agent type '{self.agent_type}'")

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
        """Write the agent's data.json file."""
        self.host.write_text_file(self._get_data_path(), json.dumps(data, indent=2))

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
        expected_command = self.get_command()
        expected_basename = self._get_command_basename(expected_command)
        if self._command_basename_matches(current_command, expected_command):
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
            logger.trace("Agent {} lifecycle state: RUNNING", self.name)
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
        data_path = self.host.host_dir / "agents" / str(self.id) / "data.json"
        try:
            content = self.host.read_text_file(data_path)
        except FileNotFoundError:
            return None

        data = json.loads(content)
        return data.get("initial_message")

    def send_message(self, message: str) -> None:
        """Send a message to the running agent."""
        logger.debug("Sending message to agent {} (length={})", self.name, len(message))
        session_name = f"{self.mngr_ctx.config.prefix}{self.name}"

        send_msg_cmd = f"tmux send-keys -t '{session_name}' -l {shlex.quote(message)}"
        result = self.host.execute_command(send_msg_cmd)
        if not result.success:
            raise SendMessageError(str(self.name), f"tmux send-keys failed: {result.stderr or result.stdout}")

        send_enter_cmd = f"tmux send-keys -t '{session_name}' Enter"
        result = self.host.execute_command(send_enter_cmd)
        if not result.success:
            raise SendMessageError(str(self.name), f"tmux send-keys Enter failed: {result.stderr or result.stdout}")

        logger.trace("Message sent to agent {}", self.name)

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
        activity_path = self._get_agent_dir() / "activity" / activity_type.value
        try:
            content = self.host.read_text_file(activity_path)
            data = json.loads(content)
            return datetime.fromisoformat(data["time"])
        except (FileNotFoundError, KeyError, ValueError):
            return None

    def record_activity(self, activity_type: ActivitySource) -> None:
        logger.trace("Recording {} activity for agent {}", activity_type, self.name)
        activity_path = self._get_agent_dir() / "activity" / activity_type.value
        data = {
            "time": datetime.now(timezone.utc).isoformat(),
        }
        self.host.write_text_file(activity_path, json.dumps(data, indent=2))

    def get_reported_activity_record(self, activity_type: ActivitySource) -> str | None:
        activity_path = self._get_agent_dir() / "activity" / activity_type.value
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
