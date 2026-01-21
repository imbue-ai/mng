from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

import click
from loguru import logger
from pydantic import Field

from imbue.mngr import hookimpl
from imbue.mngr.agents.base_agent import BaseAgent
from imbue.mngr.config.data_types import AgentTypeConfig
from imbue.mngr.config.data_types import MngrContext
from imbue.mngr.errors import NoCommandDefinedError
from imbue.mngr.errors import PluginMngrError
from imbue.mngr.interfaces.agent import AgentInterface
from imbue.mngr.interfaces.data_types import FileTransferSpec
from imbue.mngr.interfaces.host import CreateAgentOptions
from imbue.mngr.interfaces.host import HostInterface
from imbue.mngr.primitives import AgentTypeName
from imbue.mngr.primitives import CommandString

# Files from ~/.claude/ that should be transferred (these are the user's settings)
_HOME_CLAUDE_SETTINGS_FILES: tuple[str, ...] = (
    "settings.json",
    "statsig/statsig_metadata.json",
)

# Files from .claude/ in the repo that should be transferred (unversioned settings)
_REPO_CLAUDE_SETTINGS_FILES: tuple[str, ...] = (
    "settings.local.json",
)

_CLAUDE_TYPE_NAME = AgentTypeName("claude")


class ClaudeAgent(BaseAgent):
    """Agent implementation for Claude with session resumption support."""

    def assemble_command(
        self,
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
        resume_cmd = f"find ~/.claude/ -name '{agent_uuid}' && {base} --resume {agent_uuid}"
        create_cmd = f"{base} --session-id {agent_uuid}"

        # Append additional args to both commands if present
        if args_str:
            resume_cmd = f"{resume_cmd} {args_str}"
            create_cmd = f"{create_cmd} {args_str}"

        # Combine with || fallback
        return CommandString(f"export CLAUDE_SESSION_ID={agent_uuid} && ( {resume_cmd} ) || {create_cmd}")


class ClaudeAgentConfig(AgentTypeConfig):
    """Config for the claude agent type."""

    command: CommandString = Field(
        default=CommandString("claude"),
        description="Command to run claude agent",
    )
    sync_home_claude_settings: bool = Field(
        default=True,
        description="Whether to sync Claude settings from ~/.claude/ to the remote host",
    )
    sync_repo_claude_settings: bool = Field(
        default=True,
        description="Whether to sync unversioned .claude/ settings from the repo to the remote",
    )
    extra_home_claude_folder: Path | None = Field(
        default=None,
        description="Extra folder to sync to the home dir ~/.claude/ folder on the remote "
        "(files are transferred after user settings, so they can override)",
    )
    extra_repo_claude_folder: Path | None = Field(
        default=None,
        description="Extra folder to sync to the repo .claude/ folder on the remote "
        "(files are transferred after repo settings, so they can override)",
    )
    skip_installation_check: bool = Field(
        default=False,
        description="Skip checking if claude is installed (assume it is already present)",
    )


@hookimpl
def register_agent_type() -> tuple[str, type[AgentInterface] | None, type[AgentTypeConfig]]:
    """Register the claude agent type."""
    return ("claude", ClaudeAgent, ClaudeAgentConfig)


def _is_claude_agent(agent: AgentInterface) -> bool:
    """Check if the agent is a claude agent."""
    return agent.agent_type == _CLAUDE_TYPE_NAME


def _get_claude_config(agent: AgentInterface) -> ClaudeAgentConfig:
    """Get the claude-specific config from the agent."""
    if isinstance(agent.agent_config, ClaudeAgentConfig):
        return agent.agent_config
    # Fall back to default config if not a ClaudeAgentConfig
    return ClaudeAgentConfig()


def _check_claude_installed(host: HostInterface) -> bool:
    """Check if claude is installed on the host."""
    result = host.execute_command("command -v claude", timeout_seconds=10.0)
    return result.success


def _install_claude(host: HostInterface) -> None:
    """Install claude on the host using the official installer."""
    logger.info("Installing claude...")
    install_command = "curl -fsSL https://claude.ai/install.sh | bash"
    result = host.execute_command(install_command, timeout_seconds=300.0)
    if not result.success:
        raise PluginMngrError(
            f"Failed to install claude. stderr: {result.stderr}"
        )
    logger.info("Claude installed successfully")


def _prompt_user_for_installation() -> bool:
    """Prompt the user to install claude locally."""
    logger.info("")
    logger.info("Claude is not installed on this machine.")
    logger.info("You can install it by running:")
    logger.info("  curl -fsSL https://claude.ai/install.sh | bash")
    logger.info("")
    return click.confirm("Would you like to install it now?", default=True)


@hookimpl
def on_before_agent_provisioning(
    agent: AgentInterface,
    host: HostInterface,
    options: CreateAgentOptions,
    mngr_ctx: MngrContext,
) -> None:
    """Validate that claude is available or can be installed.

    For remote hosts: warn and proceed (installation happens in provision_agent)
    For local hosts: warn and prompt user for installation
    """
    if not _is_claude_agent(agent):
        return

    config = _get_claude_config(agent)
    if config.skip_installation_check:
        logger.debug("Skipping claude installation check (skip_installation_check=True)")
        return

    # Skip installation check if user provided a command override
    # (they're not actually using claude)
    if options.command is not None:
        logger.debug("Skipping claude installation check (command override provided)")
        return

    is_installed = _check_claude_installed(host)

    if is_installed:
        logger.debug("Claude is already installed on the host")
        return

    logger.warning("Claude is not installed on the host")

    if host.is_local:
        # For local hosts, prompt the user
        if _prompt_user_for_installation():
            _install_claude(host)
        else:
            raise PluginMngrError(
                "Claude is not installed. Please install it manually with:\n"
                "  curl -fsSL https://claude.ai/install.sh | bash"
            )
    # For remote hosts, we just warn here and install in provision_agent


@hookimpl
def get_provision_file_transfers(
    agent: AgentInterface,
    host: HostInterface,
    options: CreateAgentOptions,
    mngr_ctx: MngrContext,
) -> Sequence[FileTransferSpec] | None:
    """Return file transfers for claude settings."""
    if not _is_claude_agent(agent):
        return None

    config = _get_claude_config(agent)
    transfers: list[FileTransferSpec] = []

    # Transfer home dir claude settings
    if config.sync_home_claude_settings:
        home_claude_dir = Path.home() / ".claude"
        for filename in _HOME_CLAUDE_SETTINGS_FILES:
            local_path = home_claude_dir / filename
            # Remote path should be in the user's home dir on the remote
            remote_path = Path("~/.claude") / filename
            transfers.append(
                FileTransferSpec(
                    local_path=local_path,
                    remote_path=remote_path,
                    is_required=False,
                )
            )

    # Transfer repo-local claude settings
    if config.sync_repo_claude_settings:
        # Use the source work_dir from options.target_path or current directory
        source_dir = options.target_path if options.target_path else Path.cwd()
        repo_claude_dir = source_dir / ".claude"
        for filename in _REPO_CLAUDE_SETTINGS_FILES:
            local_path = repo_claude_dir / filename
            # Remote path should be in the agent's work_dir
            remote_path = agent.work_dir / ".claude" / filename
            transfers.append(
                FileTransferSpec(
                    local_path=local_path,
                    remote_path=remote_path,
                    is_required=False,
                )
            )

    # Transfer extra home claude folder contents
    if config.extra_home_claude_folder is not None:
        extra_folder = config.extra_home_claude_folder
        if extra_folder.is_dir():
            for file_path in extra_folder.rglob("*"):
                if file_path.is_file():
                    relative_path = file_path.relative_to(extra_folder)
                    remote_path = Path("~/.claude") / relative_path
                    transfers.append(
                        FileTransferSpec(
                            local_path=file_path,
                            remote_path=remote_path,
                            is_required=False,
                        )
                    )

    # Transfer extra repo claude folder contents
    if config.extra_repo_claude_folder is not None:
        extra_folder = config.extra_repo_claude_folder
        if extra_folder.is_dir():
            for file_path in extra_folder.rglob("*"):
                if file_path.is_file():
                    relative_path = file_path.relative_to(extra_folder)
                    remote_path = agent.work_dir / ".claude" / relative_path
                    transfers.append(
                        FileTransferSpec(
                            local_path=file_path,
                            remote_path=remote_path,
                            is_required=False,
                        )
                    )

    return transfers


@hookimpl
def provision_agent(
    agent: AgentInterface,
    host: HostInterface,
    options: CreateAgentOptions,
    mngr_ctx: MngrContext,
) -> None:
    """Install claude on remote hosts if needed."""
    if not _is_claude_agent(agent):
        return

    config = _get_claude_config(agent)
    if config.skip_installation_check:
        return

    # Skip installation if user provided a command override (they're not actually using claude)
    if options.command is not None:
        return

    # Only auto-install on remote hosts (local was handled in on_before_agent_provisioning)
    if host.is_local:
        return

    is_installed = _check_claude_installed(host)
    if is_installed:
        return

    # Install on remote host
    logger.info("Installing claude on remote host...")
    _install_claude(host)
