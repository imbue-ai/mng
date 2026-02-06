from __future__ import annotations

import fcntl
import json
import os
import shlex
import time
from collections.abc import Sequence
from pathlib import Path
from typing import Any
from typing import Callable
from typing import Final

import click
from loguru import logger
from pydantic import Field

from imbue.imbue_common.pure import pure
from imbue.mngr import hookimpl
from imbue.mngr.agents.base_agent import BaseAgent
from imbue.mngr.agents.default_plugins.claude_config import check_source_directory_trusted
from imbue.mngr.agents.default_plugins.claude_config import extend_claude_trust_to_worktree
from imbue.mngr.agents.default_plugins.claude_config import remove_claude_trust_for_path
from imbue.mngr.config.data_types import AgentTypeConfig
from imbue.mngr.config.data_types import MngrContext
from imbue.mngr.errors import AgentStartError
from imbue.mngr.errors import NoCommandDefinedError
from imbue.mngr.errors import PluginMngrError
from imbue.mngr.interfaces.agent import AgentInterface
from imbue.mngr.interfaces.data_types import FileTransferSpec
from imbue.mngr.interfaces.data_types import RelativePath
from imbue.mngr.interfaces.host import CreateAgentOptions
from imbue.mngr.interfaces.host import OnlineHostInterface
from imbue.mngr.primitives import CommandString
from imbue.mngr.primitives import WorkDirCopyMode
from imbue.mngr.utils.git_utils import find_git_common_dir
from imbue.mngr.utils.polling import poll_until_counted

_READY_SIGNAL_TIMEOUT_SECONDS: Final[float] = 10.0


class ClaudeAgentConfig(AgentTypeConfig):
    """Config for the claude agent type."""

    command: CommandString = Field(
        default=CommandString("claude"),
        description="Command to run claude agent",
    )
    sync_home_settings: bool = Field(
        default=True,
        description="Whether to sync Claude settings from ~/.claude/ to a remote host",
    )
    sync_claude_json: bool = Field(
        default=True,
        description="Whether to sync the local ~/.claude.json to a remote host (useful for API key settings and permissions)",
    )
    sync_repo_settings: bool = Field(
        default=True,
        description="Whether to sync unversioned .claude/ settings from the repo to the agent work_dir",
    )
    sync_claude_credentials: bool = Field(
        default=True,
        description="Whether to sync the local ~/.claude/.credentials.json to a remote host",
    )
    override_settings_folder: Path | None = Field(
        default=None,
        description="Extra folder to sync to the repo .claude/ folder in the agent work_dir."
        "(files are transferred after user settings, so they can override)",
    )
    check_installation: bool = Field(
        default=True,
        description="Check if claude is installed (if False, assumes it is already present)",
    )
    configure_readiness_hooks: bool = Field(
        default=True,
        description="Whether to configure Claude hooks for readiness signaling (waiting file)",
    )


def _check_claude_installed(host: OnlineHostInterface) -> bool:
    """Check if claude is installed on the host."""
    result = host.execute_command("command -v claude", timeout_seconds=10.0)
    return result.success


def _install_claude(host: OnlineHostInterface) -> None:
    """Install claude on the host using the official installer."""
    install_command = """curl --version && ( curl -fsSL https://claude.ai/install.sh | bash ) && echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc"""
    result = host.execute_command(install_command, timeout_seconds=300.0)
    if not result.success:
        raise PluginMngrError(f"Failed to install claude. stderr: {result.stderr}")


def _prompt_user_for_installation() -> bool:
    """Prompt the user to install claude locally."""
    logger.info(
        "\nClaude is not installed on this machine.\nYou can install it by running:\n  curl -fsSL https://claude.ai/install.sh | bash\n"
    )
    return click.confirm("Would you like to install it now?", default=True)


@pure
def _build_readiness_hooks_config() -> dict[str, Any]:
    """Build the hooks configuration for readiness signaling.

    These hooks use the MNGR_AGENT_STATE_DIR environment variable to create/remove
    files that signal agent state.

    - SessionStart: creates 'session_started' file (Claude Code has started)
    - UserPromptSubmit: removes 'waiting' file AND signals tmux wait-for channel
    - Stop: creates 'waiting' file (Claude finished processing, waiting for input)

    File semantics:
    - session_started: Claude Code session has started (for initial message timing)
    - waiting: Claude is waiting for user input (WAITING lifecycle state)

    The tmux wait-for signal on UserPromptSubmit allows instant detection of
    message submission without polling.
    """
    return {
        "hooks": {
            "SessionStart": [
                {
                    "hooks": [
                        {
                            "type": "command",
                            "command": 'touch "$MNGR_AGENT_STATE_DIR/session_started"',
                        },
                    ]
                }
            ],
            "UserPromptSubmit": [
                {
                    "hooks": [
                        {
                            "type": "command",
                            "command": 'rm -f "$MNGR_AGENT_STATE_DIR/waiting"',
                        },
                        {
                            "type": "command",
                            "command": "tmux wait-for -S \"mngr-submit-$(tmux display-message -p '#S')\" 2>/dev/null || true",
                        },
                    ]
                }
            ],
            "Stop": [
                {
                    "hooks": [
                        {
                            "type": "command",
                            "command": 'touch "$MNGR_AGENT_STATE_DIR/waiting"',
                        }
                    ]
                }
            ],
        }
    }


@pure
def _hook_already_exists(existing_hooks: list[dict[str, Any]], new_hook: dict[str, Any]) -> bool:
    """Check if a hook with the same command already exists in the list.

    Compares the inner hooks' commands to detect duplicates.
    """
    new_commands = {h.get("command") for h in new_hook.get("hooks", [])}
    for existing in existing_hooks:
        existing_commands = {h.get("command") for h in existing.get("hooks", [])}
        if new_commands == existing_commands:
            return True
    return False


def _merge_hooks_config(existing_settings: dict[str, Any], hooks_config: dict[str, Any]) -> bool:
    """Merge new hooks into existing settings, skipping duplicates.

    Returns True if any hooks were added, False if all already existed.
    """
    if "hooks" not in existing_settings:
        existing_settings["hooks"] = {}

    any_added = False
    for event_name, event_hooks in hooks_config["hooks"].items():
        if event_name not in existing_settings["hooks"]:
            existing_settings["hooks"][event_name] = []

        for new_hook in event_hooks:
            if not _hook_already_exists(existing_settings["hooks"][event_name], new_hook):
                existing_settings["hooks"][event_name].append(new_hook)
                any_added = True

    return any_added


class ClaudeAgent(BaseAgent):
    """Agent implementation for Claude with session resumption support."""

    def _get_claude_config(self) -> ClaudeAgentConfig:
        """Get the claude-specific config from this agent."""
        if isinstance(self.agent_config, ClaudeAgentConfig):
            return self.agent_config
        # Fall back to default config if not a ClaudeAgentConfig
        return ClaudeAgentConfig()

    def get_expected_process_name(self) -> str:
        """Return 'claude' as the expected process name.

        This overrides the base implementation because ClaudeAgent uses a complex
        shell command with exports and fallbacks, but the actual process is always 'claude'.
        """
        return "claude"

    def uses_marker_based_send_message(self) -> bool:
        """Enable marker-based send_message for Claude Code.

        Claude Code echoes input to the terminal and has a complex input handler
        that can misinterpret Enter as a literal newline if sent too quickly after
        the message text. The marker-based approach ensures the input handler has
        fully processed the message before submitting.
        """
        return True

    def get_tui_ready_indicator(self) -> str | None:
        """Return Claude Code's banner text as the TUI ready indicator.

        Claude Code displays "Claude Code" in its banner when the TUI is ready.
        Waiting for this ensures we don't send input before the UI is fully rendered,
        which would cause the input to be lost or appear as raw text.
        """
        return "Claude Code"

    def wait_for_ready_signal(self, start_action: Callable[[], None], timeout: float | None = None) -> None:
        """Wait for the agent to become ready, executing start_action then polling.

        Polls for the 'session_started' file that the SessionStart hook creates.
        This indicates Claude Code has started and is ready for input.

        Raises AgentStartError if the agent doesn't signal readiness within the timeout.
        """
        if timeout is None:
            timeout = _READY_SIGNAL_TIMEOUT_SECONDS

        session_started_path = self._get_agent_dir() / "session_started"

        logger.debug("Waiting for session_started file (timeout={}s)", timeout)

        # Remove any stale marker file
        rm_cmd = f"rm -f {shlex.quote(str(session_started_path))}"
        self.host.execute_command(rm_cmd, timeout_seconds=1.0)

        # Run the start action (e.g., start the agent)
        logger.debug("Calling start_action...")
        action_start = time.time()
        start_action()
        action_elapsed = time.time() - action_start
        logger.debug("start_action completed in {:.2f}s, now polling for session_started...", action_elapsed)

        # Poll for the session_started file (created by SessionStart hook)
        # Remaining timeout after start_action completed
        remaining_timeout = timeout - action_elapsed
        success, poll_count, poll_elapsed = poll_until_counted(
            lambda: self._check_file_exists(session_started_path),
            timeout=remaining_timeout,
            poll_interval=0.05,
        )

        total_elapsed = action_elapsed + poll_elapsed
        if success:
            logger.info(
                "Session started after {:.2f}s (action={:.2f}s, poll={:.2f}s, polls={})",
                total_elapsed,
                action_elapsed,
                poll_elapsed,
                poll_count,
            )
            return

        raise AgentStartError(
            str(self.name),
            f"Agent did not signal readiness within {timeout}s (waited {total_elapsed:.2f}s). "
            "This may indicate a trust dialog appeared or Claude Code failed to start.",
        )

    def _check_file_exists(self, path: Path) -> bool:
        """Check if a file exists on the host."""
        try:
            self.host.read_text_file(path)
            return True
        except FileNotFoundError:
            return False

    def assemble_command(
        self,
        host: OnlineHostInterface,
        agent_args: tuple[str, ...],
        command_override: CommandString | None,
    ) -> CommandString:
        """Assemble command with --resume || --session-id format for session resumption.

        The command format is: 'claude --resume UUID args || claude --session-id UUID args'
        This allows users to hit 'up' and 'enter' in tmux to resume the session (--resume)
        or create it with that ID (--session-id).
        """
        if command_override is not None:
            base = str(command_override)
        elif self.agent_config.command is not None:
            base = str(self.agent_config.command)
        else:
            raise NoCommandDefinedError(f"No command defined for agent type '{self.agent_type}'")

        # Use the agent ID as the stable UUID for session identification
        agent_uuid = str(self.id.get_uuid())

        # Build the additional arguments (cli_args + agent_args)
        additional_args = []
        if self.agent_config.cli_args:
            additional_args.append(self.agent_config.cli_args)
        if agent_args:
            additional_args.extend(agent_args)

        # Join additional args
        args_str = " ".join(additional_args) if additional_args else ""

        # Build both command variants
        resume_cmd = f"( find ~/.claude/ -name '{agent_uuid}' | grep . ) && {base} --resume {agent_uuid}"
        create_cmd = f"{base} --session-id {agent_uuid}"

        # Append additional args to both commands if present
        if args_str:
            resume_cmd = f"{resume_cmd} {args_str}"
            create_cmd = f"{create_cmd} {args_str}"

        # Build the environment exports
        # IS_SANDBOX is only set for remote hosts (not local)
        env_exports = f"export MAIN_CLAUDE_SESSION_ID={agent_uuid}"
        if not host.is_local:
            env_exports = f"export IS_SANDBOX=1 && {env_exports}"

        # Combine with || fallback
        return CommandString(f"{env_exports} && ( {resume_cmd} ) || {create_cmd}")

    def on_before_provisioning(
        self,
        host: OnlineHostInterface,
        options: CreateAgentOptions,
        mngr_ctx: MngrContext,
    ) -> None:
        """Validate preconditions before provisioning.

        This method performs read-only validation only. Actual setup
        happens in provision().

        For worktree mode: validates that the source directory is trusted
        in Claude's config (~/.claude.json).
        """
        if options.git and options.git.copy_mode == WorkDirCopyMode.WORKTREE:
            git_common_dir = find_git_common_dir(self.work_dir)
            if git_common_dir is not None:
                check_source_directory_trusted(git_common_dir.parent)

        config = self._get_claude_config()
        if not config.check_installation:
            logger.debug("Skipping claude installation check (check_installation=False)")
            return

        # FIXME: check that we either have an API key in the env, or that it is configured locally and credentials will be synced

    def get_provision_file_transfers(
        self,
        host: OnlineHostInterface,
        options: CreateAgentOptions,
        mngr_ctx: MngrContext,
    ) -> Sequence[FileTransferSpec]:
        """Return file transfers for claude settings."""
        config = self._get_claude_config()
        transfers: list[FileTransferSpec] = []

        # Transfer repo-local claude settings
        if config.sync_repo_settings:
            claude_dir = self.work_dir / ".claude"
            for file_path in claude_dir.rglob("*.local.*"):
                relative_path = file_path.relative_to(self.work_dir)
                transfers.append(
                    FileTransferSpec(local_path=file_path, agent_path=RelativePath(relative_path), is_required=True)
                )

        # Transfer override folder contents
        if config.override_settings_folder is not None:
            override_folder = config.override_settings_folder
            if override_folder.is_dir():
                for file_path in override_folder.rglob("*"):
                    if file_path.is_file():
                        relative_path = file_path.relative_to(override_folder)
                        remote_path = Path(".claude") / relative_path
                        transfers.append(
                            FileTransferSpec(
                                local_path=file_path,
                                agent_path=RelativePath(remote_path),
                                is_required=False,
                            )
                        )

        return transfers

    def _configure_readiness_hooks(self, host: OnlineHostInterface) -> None:
        """Configure Claude hooks for readiness signaling in the agent's work_dir.

        This writes hooks to .claude/settings.local.json in the agent's work_dir.
        The hooks signal when Claude is ready for input by creating/removing a
        'waiting' file in the agent's state directory.

        Uses file locking on local hosts to prevent race conditions.
        Creates a backup before modifying and skips if hooks already exist.
        """
        hooks_config = _build_readiness_hooks_config()
        settings_path = self.work_dir / ".claude" / "settings.local.json"

        if host.is_local:
            self._configure_readiness_hooks_local(settings_path, hooks_config)
        else:
            self._configure_readiness_hooks_remote(host, settings_path, hooks_config)

    def _configure_readiness_hooks_local(self, settings_path: Path, hooks_config: dict[str, Any]) -> None:
        """Configure readiness hooks on a local host with file locking."""
        # Ensure parent directory exists
        settings_path.parent.mkdir(parents=True, exist_ok=True)

        # Create the file if it doesn't exist
        if not settings_path.exists():
            settings_path.write_text("{}")

        with open(settings_path, "r+") as f:
            fcntl.flock(f.fileno(), fcntl.LOCK_EX)
            try:
                # Read existing content
                f.seek(0)
                content = f.read()
                existing_settings = json.loads(content) if content.strip() else {}

                # Merge hooks, checking for duplicates
                if not _merge_hooks_config(existing_settings, hooks_config):
                    logger.debug("Readiness hooks already configured in {}", settings_path)
                    return

                # Write atomically: write to temp file in same directory, then rename
                temp_path = settings_path.with_suffix(".json.tmp")
                with open(temp_path, "w") as tmp:
                    json.dump(existing_settings, tmp, indent=2)
                    tmp.write("\n")
                    tmp.flush()
                    os.fsync(tmp.fileno())
                temp_path.rename(settings_path)

                logger.debug("Configured readiness hooks in {}", settings_path)
            finally:
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)

    def _configure_readiness_hooks_remote(
        self, host: OnlineHostInterface, settings_path: Path, hooks_config: dict[str, Any]
    ) -> None:
        """Configure readiness hooks on a remote host."""
        # Read existing settings if present
        existing_settings: dict[str, Any] = {}
        try:
            content = host.read_text_file(settings_path)
            existing_settings = json.loads(content)
        except FileNotFoundError:
            pass

        # Merge hooks, checking for duplicates
        if not _merge_hooks_config(existing_settings, hooks_config):
            logger.debug("Readiness hooks already configured in {}", settings_path)
            return

        # Write the merged settings
        logger.debug("Configuring readiness hooks in {}", settings_path)
        host.write_text_file(settings_path, json.dumps(existing_settings, indent=2) + "\n")

    def provision(
        self,
        host: OnlineHostInterface,
        options: CreateAgentOptions,
        mngr_ctx: MngrContext,
    ) -> None:
        """Extend trust for worktrees and install Claude if needed."""
        if options.git and options.git.copy_mode == WorkDirCopyMode.WORKTREE:
            git_common_dir = find_git_common_dir(self.work_dir)
            if git_common_dir is not None:
                source_path = git_common_dir.parent
                extend_claude_trust_to_worktree(source_path, self.work_dir)

        config = self._get_claude_config()

        # ensure that claude is installed
        if config.check_installation:
            is_installed = _check_claude_installed(host)
            if is_installed:
                logger.debug("Claude is already installed on the host")
            else:
                logger.warning("Claude is not installed on the host")

                if host.is_local:
                    # For local hosts, prompt the user for consent (if interactive)
                    if mngr_ctx.is_interactive:
                        if _prompt_user_for_installation():
                            logger.debug("User consented to install claude locally")
                        else:
                            raise PluginMngrError(
                                "Claude is not installed. Please install it manually with:\n"
                                "  curl -fsSL https://claude.ai/install.sh | bash"
                            )
                    else:
                        # Non-interactive mode: fail with a clear message
                        raise PluginMngrError(
                            "Claude is not installed. Please install it manually with:\n"
                            "  curl -fsSL https://claude.ai/install.sh | bash"
                        )
                else:
                    # FIXME: for remote hosts, we need to check whether the user has allowed automatic installation for remote hosts
                    #  in the global MngrConfig (we'll need to add that config option there, defaulting to True)
                    #  If they have not enabled that, we must raise an error here
                    pass

                # Install claude
                logger.info("Installing claude...")
                _install_claude(host)
                logger.info("Claude installed successfully")

        # transfer some extra files to remote hosts (if configured):
        if not host.is_local:
            if config.sync_home_settings:
                logger.info("Transferring claude home directory settings to remote host...")
                # transfer anything in ~/.claude/skills/, ~/.claude/agents/, and ~/.claude/commands/:
                local_claude_dir = Path.home() / ".claude"
                for local_config_path in [
                    local_claude_dir / "settings.json",
                    local_claude_dir / "skills",
                    local_claude_dir / "agents",
                    local_claude_dir / "commands",
                ]:
                    if local_config_path.exists():
                        if local_config_path.is_dir():
                            for file_path in local_config_path.rglob("*"):
                                if file_path.is_file():
                                    relative_path = file_path.relative_to(local_claude_dir)
                                    remote_path = Path(".claude") / relative_path
                                    host.write_text_file(remote_path, file_path.read_text())
                        else:
                            relative_path = local_config_path.relative_to(local_claude_dir)
                            remote_path = Path(".claude") / relative_path
                            host.write_text_file(remote_path, local_config_path.read_text())

            if config.sync_claude_json:
                claude_json_path = Path.home() / ".claude.json"
                if claude_json_path.exists():
                    logger.info("Transferring ~/.claude.json to remote host...")
                    host.write_text_file(Path(".claude.json"), claude_json_path.read_text())
                else:
                    logger.debug("Skipping ~/.claude.json (file does not exist)")

            if config.sync_claude_credentials:
                credentials_path = Path.home() / ".claude" / ".credentials.json"
                if credentials_path.exists():
                    logger.info("Transferring ~/.claude/.credentials.json to remote host...")
                    host.write_text_file(Path(".claude/.credentials.json"), credentials_path.read_text())
                else:
                    logger.debug("Skipping ~/.claude/.credentials.json (file does not exist)")

        # Configure readiness hooks (for both local and remote hosts)
        if config.configure_readiness_hooks:
            self._configure_readiness_hooks(host)

    def on_destroy(self, host: OnlineHostInterface) -> None:
        """Clean up Claude trust entries for this agent's work directory."""
        removed = remove_claude_trust_for_path(self.work_dir)
        if removed:
            logger.debug("Removed Claude trust entry for {}", self.work_dir)


@hookimpl
def register_agent_type() -> tuple[str, type[AgentInterface] | None, type[AgentTypeConfig]]:
    """Register the claude agent type."""
    return ("claude", ClaudeAgent, ClaudeAgentConfig)
