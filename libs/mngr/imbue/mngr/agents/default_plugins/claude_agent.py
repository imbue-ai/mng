from __future__ import annotations

import json
import shlex
from collections.abc import Sequence
from pathlib import Path
from typing import Any
from typing import Callable
from typing import Final

import click
from loguru import logger
from pydantic import Field

from imbue.imbue_common.logging import log_span
from imbue.mngr import hookimpl
from imbue.mngr.agents.base_agent import BaseAgent
from imbue.mngr.agents.default_plugins.claude_config import ClaudeDirectoryNotTrustedError
from imbue.mngr.agents.default_plugins.claude_config import add_claude_trust_for_path
from imbue.mngr.agents.default_plugins.claude_config import build_readiness_hooks_config
from imbue.mngr.agents.default_plugins.claude_config import check_source_directory_trusted
from imbue.mngr.agents.default_plugins.claude_config import extend_claude_trust_to_worktree
from imbue.mngr.agents.default_plugins.claude_config import merge_hooks_config
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


def _prompt_user_for_trust(source_path: Path) -> bool:
    """Prompt the user to trust a directory for Claude Code."""
    logger.info(
        "\nSource directory {} is not yet trusted by Claude Code.\n"
        "mngr needs to add a trust entry to ~/.claude.json so that Claude Code\n"
        "can start without showing a trust dialog.\n",
        source_path,
    )
    return click.confirm("Would you like to trust this directory?", default=False)


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

        with log_span("Waiting for session_started file (timeout={}s)", timeout):
            # Remove any stale marker file
            rm_cmd = f"rm -f {shlex.quote(str(session_started_path))}"
            self.host.execute_command(rm_cmd, timeout_seconds=1.0)

            # Run the start action (e.g., start the agent)
            with log_span("Calling start_action..."):
                start_action()

            # Poll for the session_started file (created by SessionStart hook)
            success, poll_count, poll_elapsed = poll_until_counted(
                lambda: self._check_file_exists(session_started_path),
                timeout=timeout,
                poll_interval=0.05,
            )

            if success:
                return

            raise AgentStartError(
                str(self.name),
                f"Agent did not signal readiness within {timeout}s. "
                "This may indicate a trust dialog appeared or Claude Code failed to start.",
            )

    def _build_activity_updater_command(self, session_name: str) -> str:
        """Build a shell command that starts the activity updater in the background.

        The activity updater continuously updates the agent's activity file
        ($MNGR_AGENT_STATE_DIR/activity/agent) as long as the tmux session exists
        AND the .claude/active file is present (indicating the agent is actively
        processing, not idle). Uses a pidfile to prevent duplicate instances for
        the same session.
        """
        parts = [
            "(",
            f"_MNGR_ACT_LOCK=/tmp/mngr_act_{session_name}.pid;",
            'if [ -f "$_MNGR_ACT_LOCK" ] &&',
            'kill -0 "$(cat "$_MNGR_ACT_LOCK" 2>/dev/null)" 2>/dev/null;',
            "then exit 0; fi;",
            'echo $$ > "$_MNGR_ACT_LOCK";',
            """trap 'rm -f "$_MNGR_ACT_LOCK"' EXIT;""",
            'mkdir -p "$MNGR_AGENT_STATE_DIR/activity";',
            f"while tmux has-session -t '{session_name}' 2>/dev/null; do",
            "if [ -f .claude/active ]; then",
            """printf '{"time": %d, "source": "activity_updater"}'""",
            '"$(($(date +%s) * 1000))" > "$MNGR_AGENT_STATE_DIR/activity/agent";',
            "fi;",
            "sleep 15; done;",
            'rm -f "$_MNGR_ACT_LOCK"',
            ") &",
        ]
        return " ".join(parts)

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

        An activity updater is started in the background to keep the agent's activity
        timestamp up-to-date while the tmux session is alive.
        """
        if command_override is not None:
            base = str(command_override)
        elif self.agent_config.command is not None:
            base = str(self.agent_config.command)
        else:
            raise NoCommandDefinedError(f"No command defined for agent type '{self.agent_type}'")

        # Use the agent ID as the stable UUID for session identification
        agent_uuid = str(self.id.get_uuid())

        # Build the additional arguments (cli_args from config + agent_args from CLI)
        args_str = ""

        # FIXME: it's strange that cli_args is a str and agent_args is a tuple[str, ...].
        #  We should probably update both to be able to handle either style of argument (at the interface level)
        #  And convert them to tuple[str, ...] in these data types.
        if self.agent_config.cli_args:
            args_str += self.agent_config.cli_args

        if agent_args:
            args_str = (args_str + " ").lstrip() + " ".join(agent_args)

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

        # Build the activity updater background command
        session_name = f"{self.mngr_ctx.config.prefix}{self.name}"
        activity_cmd = self._build_activity_updater_command(session_name)

        # Combine: start activity updater in background, then run the main command
        return CommandString(f"{activity_cmd} {env_exports} && ( {resume_cmd} ) || {create_cmd}")

    def on_before_provisioning(
        self,
        host: OnlineHostInterface,
        options: CreateAgentOptions,
        mngr_ctx: MngrContext,
    ) -> None:
        """Validate preconditions before provisioning (read-only).

        This method performs read-only validation only. No writes to
        disk or interactive prompts -- actual setup happens in provision().

        For worktree mode on non-interactive runs: validates that the
        source directory is trusted in Claude's config (~/.claude.json)
        so we fail early with a clear message. Interactive runs skip
        this check because provision() will prompt the user if needed.
        """
        if options.git and options.git.copy_mode == WorkDirCopyMode.WORKTREE:
            if not host.is_local:
                raise PluginMngrError(
                    "Worktree mode is not supported on remote hosts.\n"
                    "Claude trust extension requires local filesystem access. "
                    "Use --copy or --clone instead."
                )
            if not mngr_ctx.is_interactive:
                git_common_dir = find_git_common_dir(self.work_dir)
                if git_common_dir is not None:
                    source_path = git_common_dir.parent
                    check_source_directory_trusted(source_path)

        config = self._get_claude_config()
        if not config.check_installation:
            logger.debug("Skipped claude installation check (check_installation=False)")
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

        Skips if hooks already exist.
        """
        # Future improvement: use `claude --settings <path>` to load hooks from
        # outside the worktree (e.g. the agent state dir), eliminating the need
        # to write to .claude/settings.local.json and check that it's gitignored.
        settings_relative = Path(".claude") / "settings.local.json"
        settings_path = self.work_dir / settings_relative

        # FIXME: it's not safe to assume that git exists or that this is a git repo--clean this up
        # Verify .claude/settings.local.json is gitignored to avoid unstaged changes (if this is even using git)
        result = host.execute_command(
            f"git check-ignore -q {shlex.quote(str(settings_relative))}",
            cwd=self.work_dir,
            timeout_seconds=5.0,
        )
        if not result.success:
            if "fatal: not a git repository" not in result.stderr:
                raise PluginMngrError(
                    f".claude/settings.local.json is not gitignored in {self.work_dir}.\n"
                    "mngr needs to write Claude hooks to this file, but it would appear as an unstaged change.\n"
                    f"Add '.claude/settings.local.json' to your .gitignore and try again. (original error: {result.stderr})"
                )

        hooks_config = build_readiness_hooks_config()

        # Read existing settings if present
        existing_settings: dict[str, Any] = {}
        try:
            content = host.read_text_file(settings_path)
            existing_settings = json.loads(content)
        except FileNotFoundError:
            pass

        # Merge hooks, checking for duplicates
        merged = merge_hooks_config(existing_settings, hooks_config)
        if merged is None:
            logger.debug("Readiness hooks already configured in {}", settings_path)
            return

        # Write the merged settings
        with log_span("Configuring readiness hooks in {}", settings_path):
            host.write_text_file(settings_path, json.dumps(merged, indent=2) + "\n")

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
                try:
                    extend_claude_trust_to_worktree(source_path, self.work_dir)
                except ClaudeDirectoryNotTrustedError:
                    if mngr_ctx.is_interactive and _prompt_user_for_trust(source_path):
                        add_claude_trust_for_path(source_path)
                        extend_claude_trust_to_worktree(source_path, self.work_dir)
                    else:
                        raise

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
                    logger.debug("Skipped ~/.claude.json (file does not exist)")

            if config.sync_claude_credentials:
                credentials_path = Path.home() / ".claude" / ".credentials.json"
                if credentials_path.exists():
                    logger.info("Transferring ~/.claude/.credentials.json to remote host...")
                    host.write_text_file(Path(".claude/.credentials.json"), credentials_path.read_text())
                else:
                    logger.debug("Skipped ~/.claude/.credentials.json (file does not exist)")

        # Configure readiness hooks (for both local and remote hosts)
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
