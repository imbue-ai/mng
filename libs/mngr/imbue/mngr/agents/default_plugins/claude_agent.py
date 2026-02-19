from __future__ import annotations

import json
import os
import shlex
from collections.abc import Sequence
from pathlib import Path
from typing import Any
from typing import Callable
from typing import Final

import click
from loguru import logger
from pydantic import Field

from imbue.concurrency_group.concurrency_group import ConcurrencyGroup
from imbue.concurrency_group.errors import ProcessSetupError
from imbue.imbue_common.logging import log_span
from imbue.mngr import hookimpl
from imbue.mngr.agents.base_agent import BaseAgent
from imbue.mngr.agents.default_plugins.claude_config import ClaudeDirectoryNotTrustedError
from imbue.mngr.agents.default_plugins.claude_config import ClaudeEffortCalloutNotDismissedError
from imbue.mngr.agents.default_plugins.claude_config import add_claude_trust_for_path
from imbue.mngr.agents.default_plugins.claude_config import build_readiness_hooks_config
from imbue.mngr.agents.default_plugins.claude_config import check_claude_dialogs_dismissed
from imbue.mngr.agents.default_plugins.claude_config import dismiss_effort_callout
from imbue.mngr.agents.default_plugins.claude_config import ensure_claude_dialogs_dismissed
from imbue.mngr.agents.default_plugins.claude_config import extend_claude_trust_to_worktree
from imbue.mngr.agents.default_plugins.claude_config import is_effort_callout_dismissed
from imbue.mngr.agents.default_plugins.claude_config import is_source_directory_trusted
from imbue.mngr.agents.default_plugins.claude_config import merge_hooks_config
from imbue.mngr.agents.default_plugins.claude_config import remove_claude_trust_for_path
from imbue.mngr.config.data_types import AgentTypeConfig
from imbue.mngr.config.data_types import MngrContext
from imbue.mngr.errors import AgentStartError
from imbue.mngr.errors import NoCommandDefinedError
from imbue.mngr.errors import PluginMngrError
from imbue.mngr.hosts.common import is_macos
from imbue.mngr.interfaces.agent import AgentInterface
from imbue.mngr.interfaces.data_types import FileTransferSpec
from imbue.mngr.interfaces.data_types import RelativePath
from imbue.mngr.interfaces.host import CreateAgentOptions
from imbue.mngr.interfaces.host import OnlineHostInterface
from imbue.mngr.primitives import CommandString
from imbue.mngr.primitives import WorkDirCopyMode
from imbue.mngr.providers.ssh_host_setup import load_resource_script
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
    convert_macos_credentials: bool = Field(
        default=True,
        description="Whether to convert macOS keychain credentials to flat files for remote hosts",
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
        "mngr needs to add a trust entry for this directory to ~/.claude.json\n"
        "so that Claude Code can start without showing a trust dialog.\n",
        source_path,
    )
    return click.confirm("Would you like to update ~/.claude.json to trust this directory?", default=False)


def _prompt_user_for_effort_callout_dismissal() -> bool:
    """Prompt the user to dismiss the Claude Code effort callout."""
    logger.info(
        "\nClaude Code wants you to know that you can set model effort with /model.\n"
        "mngr needs to dismiss this callout in ~/.claude.json so that Claude Code\n"
        "can start without it interfering with automated input.\n",
    )
    return click.confirm("Would you like to update ~/.claude.json to dismiss this?", default=False)


def _claude_json_has_primary_api_key() -> bool:
    """Check if ~/.claude.json contains a non-empty primaryApiKey."""
    claude_json_path = Path.home() / ".claude.json"
    if not claude_json_path.exists():
        return False
    try:
        config_data = json.loads(claude_json_path.read_text())
        return bool(config_data.get("primaryApiKey"))
    except (json.JSONDecodeError, OSError):
        return False


def _read_macos_keychain_credential(label: str, concurrency_group: ConcurrencyGroup) -> str | None:
    """Read a credential from the macOS keychain by label."""
    try:
        result = concurrency_group.run_process_to_completion(
            ["security", "find-generic-password", "-l", label, "-w"],
            is_checked_after=False,
        )
    except ProcessSetupError:
        logger.debug("macOS security binary not found")
        return None
    if result.returncode != 0:
        logger.debug("No keychain credential found for label {!r}", label)
        return None
    return result.stdout.strip()


def _provision_background_scripts(host: OnlineHostInterface) -> None:
    """Write the background task scripts to $MNGR_HOST_DIR/commands/.

    Provisions export_transcript.sh and claude_background_tasks.sh so they
    can be launched by the agent's assemble_command at runtime.
    """
    commands_dir = host.host_dir / "commands"
    host.execute_command(f"mkdir -p {shlex.quote(str(commands_dir))}", timeout_seconds=5.0)

    for script_name in ("export_transcript.sh", "claude_background_tasks.sh"):
        script_content = load_resource_script(script_name)
        script_path = commands_dir / script_name
        with log_span("Writing {} to host", script_name):
            host.write_file(script_path, script_content.encode(), mode="0755")


def _has_api_credentials_available(
    host: OnlineHostInterface,
    options: CreateAgentOptions,
    config: ClaudeAgentConfig,
    concurrency_group: ConcurrencyGroup,
) -> bool:
    """Check whether API credentials appear to be available for Claude Code.

    Checks environment variables (process env for local hosts, agent env vars,
    host env vars), local credentials file (~/.claude/.credentials.json), and
    primaryApiKey in ~/.claude.json.

    Returns True if any credential source is detected, False otherwise.
    """
    # Local hosts inherit the process environment via tmux
    if host.is_local and os.environ.get("ANTHROPIC_API_KEY"):
        return True

    for env_var in options.environment.env_vars:
        if env_var.key == "ANTHROPIC_API_KEY":
            return True

    if host.get_env_var("ANTHROPIC_API_KEY"):
        return True

    # Check credentials file or macOS keychain (OAuth tokens)
    credentials_path = Path.home() / ".claude" / ".credentials.json"
    is_oauth_available = credentials_path.exists() or (
        config.convert_macos_credentials
        and is_macos()
        and _read_macos_keychain_credential("Claude Code-credentials", concurrency_group) is not None
    )
    if is_oauth_available:
        if host.is_local:
            return True
        if config.sync_claude_credentials:
            return True

    # Check primaryApiKey in ~/.claude.json or macOS keychain (API key)
    is_api_key_available = _claude_json_has_primary_api_key() or (
        config.convert_macos_credentials
        and is_macos()
        and _read_macos_keychain_credential("Claude Code", concurrency_group) is not None
    )
    if is_api_key_available:
        if host.is_local:
            return True
        if config.sync_claude_json:
            return True

    return False


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

    def wait_for_ready_signal(
        self, is_creating: bool, start_action: Callable[[], None], timeout: float | None = None
    ) -> None:
        """Wait for the agent to become ready, executing start_action then polling.

        Polls for the 'session_started' file that the SessionStart hook creates.
        This indicates Claude Code has started and is ready for input.

        Raises AgentStartError if the agent doesn't signal readiness within the timeout.
        """
        if timeout is None:
            timeout = _READY_SIGNAL_TIMEOUT_SECONDS

        # this file is removed when we start the agent, see assemble_command, and created by the SessionStart hook when the session is ready
        session_started_path = self._get_agent_dir() / "session_started"

        with log_span("Waiting for session_started file (timeout={}s)", timeout):
            # Run the start action (e.g., start the agent)
            with log_span("Calling start_action..."):
                super().wait_for_ready_signal(is_creating, start_action, timeout)

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

    def _build_background_tasks_command(self, session_name: str) -> str:
        """Build a shell command that starts the background tasks script.

        The background tasks script (provisioned to $MNGR_HOST_DIR/commands/)
        handles both activity tracking and transcript export. It runs in the
        background while the tmux session is alive.
        """
        script_path = "$MNGR_HOST_DIR/commands/claude_background_tasks.sh"
        return f"( {script_path} {shlex.quote(session_name)} ) &"

    def assemble_command(
        self,
        host: OnlineHostInterface,
        agent_args: tuple[str, ...],
        command_override: CommandString | None,
    ) -> CommandString:
        """Assemble command with --resume || --session-id format for session resumption.

        The command format is: 'claude --resume $SID args || claude --session-id UUID args'
        This allows users to hit 'up' and 'enter' in tmux to resume the session (--resume)
        or create it with that ID (--session-id). The resume path uses $MAIN_CLAUDE_SESSION_ID,
        resolved at runtime from the session tracking file (falling back to the agent UUID on
        first run).

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
        all_extra_args = self.agent_config.cli_args + agent_args
        args_str = " ".join(all_extra_args) if all_extra_args else ""

        # Read the latest session ID from the tracking file written by the SessionStart hook.
        # This handles session replacement (e.g., exit plan mode, /clear, compaction) where
        # Claude Code creates a new session with a different UUID. Falls back to the agent UUID
        # if the tracking file doesn't exist (first run) or is empty (crash during write).
        sid_export = (
            f'_MNGR_READ_SID=$(cat "$MNGR_AGENT_STATE_DIR/claude_session_id" 2>/dev/null || true);'
            f' export MAIN_CLAUDE_SESSION_ID="${{_MNGR_READ_SID:-{agent_uuid}}}"'
        )

        # Build both command variants using the dynamic session ID
        resume_cmd = f'( find ~/.claude/ -name "$MAIN_CLAUDE_SESSION_ID" | grep . ) && {base} --resume "$MAIN_CLAUDE_SESSION_ID"'
        create_cmd = f"{base} --session-id {agent_uuid}"

        # Append additional args to both commands if present
        if args_str:
            resume_cmd = f"{resume_cmd} {args_str}"
            create_cmd = f"{create_cmd} {args_str}"

        # Build the environment exports
        # IS_SANDBOX is only set for remote hosts (not local)
        env_exports = f"export IS_SANDBOX=1 && {sid_export}" if not host.is_local else sid_export

        # Build the background tasks command (activity tracking + transcript export)
        session_name = f"{self.mngr_ctx.config.prefix}{self.name}"
        background_cmd = self._build_background_tasks_command(session_name)

        # Combine: start background tasks, export env (including session ID), then run the main command (and make sure we get rid of the session started marker on each run so that wait_for_ready_signal works correctly for both new and resumed sessions)
        return CommandString(
            f"{background_cmd} {env_exports} && rm -rf $MNGR_AGENT_STATE_DIR/session_started && ( {resume_cmd} ) || {create_cmd}"
        )

    def on_before_provisioning(
        self,
        host: OnlineHostInterface,
        options: CreateAgentOptions,
        mngr_ctx: MngrContext,
    ) -> None:
        """Validate preconditions before provisioning (read-only).

        This method performs read-only validation only. No writes to
        disk or interactive prompts -- actual setup happens in provision().

        For worktree mode on non-interactive runs: validates that all
        known Claude startup dialogs (trust, effort callout) are dismissed
        so we fail early with a clear message. Interactive and auto-approve
        runs skip these checks because provision() will handle them.
        """
        if options.git and options.git.copy_mode == WorkDirCopyMode.WORKTREE:
            if not host.is_local:
                raise PluginMngrError(
                    "Worktree mode is not supported on remote hosts.\n"
                    "Claude trust extension requires local filesystem access. "
                    "Use --copy or --clone instead."
                )
            if not mngr_ctx.is_interactive and not mngr_ctx.is_auto_approve:
                git_common_dir = find_git_common_dir(self.work_dir, mngr_ctx.concurrency_group)
                if git_common_dir is not None:
                    source_path = git_common_dir.parent
                    check_claude_dialogs_dismissed(source_path)

        config = self._get_claude_config()
        if not config.check_installation:
            logger.debug("Skipped claude installation check (check_installation=False)")
            return

        if not _has_api_credentials_available(host, options, config, mngr_ctx.concurrency_group):
            logger.warning(
                "No API credentials detected for Claude Code. The agent may fail to start.\n"
                "Provide credentials via one of:\n"
                "  - Set ANTHROPIC_API_KEY environment variable (use --pass-env ANTHROPIC_API_KEY)\n"
                "  - Run 'claude login' to create ~/.claude/.credentials.json"
            )

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
        The hooks signal when Claude is actively processing by creating/removing an
        'active' file in the agent's state directory.

        Skips if hooks already exist.
        """
        # Future improvement: use `claude --settings <path>` to load hooks from
        # outside the worktree (e.g. the agent state dir), eliminating the need
        # to write to .claude/settings.local.json and check that it's gitignored.
        settings_relative = Path(".claude") / "settings.local.json"
        settings_path = self.work_dir / settings_relative

        # Only check gitignore if git is available and this is a git repository
        is_git_repo = host.execute_command(
            "git rev-parse --is-inside-work-tree",
            cwd=self.work_dir,
            timeout_seconds=5.0,
        )
        if is_git_repo.success:
            # Verify .claude/settings.local.json is gitignored to avoid unstaged changes
            result = host.execute_command(
                f"git check-ignore -q {shlex.quote(str(settings_relative))}",
                cwd=self.work_dir,
                timeout_seconds=5.0,
            )
            if not result.success:
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

    def _ensure_no_blocking_dialogs(self, source_path: Path, mngr_ctx: MngrContext) -> None:
        """Ensure all known Claude startup dialogs are dismissed for source_path.

        For auto-approve mode, silently dismisses all dialogs. For interactive
        mode, prompts the user for each undismissed dialog. For non-interactive
        mode, raises the appropriate error.
        """
        if mngr_ctx.is_auto_approve:
            ensure_claude_dialogs_dismissed(source_path)
            return

        if not is_source_directory_trusted(source_path):
            if not mngr_ctx.is_interactive or not _prompt_user_for_trust(source_path):
                raise ClaudeDirectoryNotTrustedError(str(source_path))
            add_claude_trust_for_path(source_path)

        if not is_effort_callout_dismissed():
            if not mngr_ctx.is_interactive or not _prompt_user_for_effort_callout_dismissal():
                raise ClaudeEffortCalloutNotDismissedError()
            dismiss_effort_callout()

    def provision(
        self,
        host: OnlineHostInterface,
        options: CreateAgentOptions,
        mngr_ctx: MngrContext,
    ) -> None:
        """Extend trust for worktrees and install Claude if needed.

        For worktree-mode agents, ensures all Claude startup dialogs are
        dismissed and extends trust to the worktree.
        """
        if options.git and options.git.copy_mode == WorkDirCopyMode.WORKTREE:
            git_common_dir = find_git_common_dir(self.work_dir, mngr_ctx.concurrency_group)
            if git_common_dir is not None:
                source_path = git_common_dir.parent
                self._ensure_no_blocking_dialogs(source_path, mngr_ctx)
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
                    # For local hosts, auto-approve or prompt the user for consent
                    if mngr_ctx.is_auto_approve:
                        logger.debug("Auto-approving claude installation (--yes)")
                    elif mngr_ctx.is_interactive:
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
                    if not mngr_ctx.config.is_remote_agent_installation_allowed:
                        raise PluginMngrError(
                            "Claude is not installed on the remote host and automatic remote installation is disabled. "
                            "Set is_remote_agent_installation_allowed = true in your mngr config to enable automatic installation, "
                            "or install Claude manually on the remote host."
                        )
                    else:
                        logger.debug("Automatic remote agent installation is enabled, proceeding")

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
                    # Set global fields that prevent startup dialogs from intercepting
                    # automated input via tmux send-keys:
                    claude_json_data = json.loads(claude_json_path.read_text())
                    claude_json_data["bypassPermissionsModeAccepted"] = True
                    claude_json_data["effortCalloutDismissed"] = True
                    # If the local file lacks primaryApiKey, try the macOS keychain
                    if not claude_json_data.get("primaryApiKey") and config.convert_macos_credentials and is_macos():
                        keychain_api_key = _read_macos_keychain_credential("Claude Code", mngr_ctx.concurrency_group)
                        if keychain_api_key is not None:
                            logger.info("Merging macOS keychain API key into ~/.claude.json for remote host...")
                            claude_json_data["primaryApiKey"] = keychain_api_key
                    host.write_text_file(Path(".claude.json"), json.dumps(claude_json_data, indent=2) + "\n")
                else:
                    logger.debug("Skipped ~/.claude.json (file does not exist)")

            if config.sync_claude_credentials:
                credentials_path = Path.home() / ".claude" / ".credentials.json"
                if credentials_path.exists():
                    logger.info("Transferring ~/.claude/.credentials.json to remote host...")
                    host.write_text_file(Path(".claude/.credentials.json"), credentials_path.read_text())
                elif config.convert_macos_credentials and is_macos():
                    # No local credentials file, but keychain may have OAuth tokens
                    keychain_credentials = _read_macos_keychain_credential(
                        "Claude Code-credentials", mngr_ctx.concurrency_group
                    )
                    if keychain_credentials is not None:
                        logger.info("Writing macOS keychain OAuth credentials to remote host...")
                        host.write_text_file(Path(".claude/.credentials.json"), keychain_credentials)
                    else:
                        logger.debug(
                            "Skipped ~/.claude/.credentials.json (file does not exist, no keychain credentials)"
                        )
                else:
                    logger.debug("Skipped ~/.claude/.credentials.json (file does not exist)")

        # Configure readiness hooks (for both local and remote hosts)
        self._configure_readiness_hooks(host)

        # Provision background task scripts to the host commands directory
        _provision_background_scripts(host)

    def on_destroy(self, host: OnlineHostInterface) -> None:
        """Clean up Claude trust entries for this agent's work directory."""
        removed = remove_claude_trust_for_path(self.work_dir)
        if removed:
            logger.debug("Removed Claude trust entry for {}", self.work_dir)


@hookimpl
def register_agent_type() -> tuple[str, type[AgentInterface] | None, type[AgentTypeConfig]]:
    """Register the claude agent type."""
    return ("claude", ClaudeAgent, ClaudeAgentConfig)
