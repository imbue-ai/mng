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
from imbue.mngr.interfaces.data_types import RelativePath
from imbue.mngr.interfaces.host import CreateAgentOptions
from imbue.mngr.interfaces.host import HostInterface
from imbue.mngr.primitives import AgentTypeName
from imbue.mngr.primitives import CommandString

_TYPE_NAME = AgentTypeName("claude")


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
    sync_home_settings: bool = Field(
        default=True,
        description="Whether to sync Claude settings from ~/.claude/ to a remote host",
    )
    sync_claude_json: bool = Field(
        default=True,
        description="Whether to sync the local ~/.claude.json to a remote host (useful for API key settings and permissions)",
    )
    sync_claude_credentials: bool = Field(
        default=True,
        description="Whether to sync the local ~/.claude/.credentials.json to a remote host",
    )
    sync_repo_settings: bool = Field(
        default=True,
        description="Whether to sync unversioned .claude/ settings from the repo to the agent work_dir",
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


@hookimpl
def register_agent_type() -> tuple[str, type[AgentInterface] | None, type[AgentTypeConfig]]:
    """Register the claude agent type."""
    return ("claude", ClaudeAgent, ClaudeAgentConfig)


def _is_claude_agent(agent: AgentInterface) -> bool:
    """Check if the agent is a claude agent."""
    return agent.agent_type == _TYPE_NAME


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
    install_command = "curl -fsSL https://claude.ai/install.sh | bash"
    result = host.execute_command(install_command, timeout_seconds=300.0)
    if not result.success:
        raise PluginMngrError(f"Failed to install claude. stderr: {result.stderr}")


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

    This hook performs read-only validation only. Actual installation
    happens in provision_agent.

    For remote hosts: warn and proceed (installation happens in provision_agent)
    For local hosts: warn and prompt user for consent (installation happens in provision_agent)
    """
    if not _is_claude_agent(agent):
        return

    config = _get_claude_config(agent)
    if not config.check_installation:
        logger.debug("Skipping claude installation check (check_installation=False)")
        return

    # FIXME: check that we either have an API key in the env, or that it is configured locally and credentials will be synced


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


@hookimpl
def provision_agent(
    agent: AgentInterface,
    host: HostInterface,
    options: CreateAgentOptions,
    mngr_ctx: MngrContext,
) -> None:
    """Install claude if needed.

    For local hosts: user consent was already obtained in on_before_agent_provisioning
    For remote hosts: installation is automatic
    """
    if not _is_claude_agent(agent):
        return

    config = _get_claude_config(agent)

    # ensure that claude is installed
    if config.check_installation:
        is_installed = _check_claude_installed(host)
        if is_installed:
            logger.debug("Claude is already installed on the host")
        else:
            logger.warning("Claude is not installed on the host")

            if host.is_local:
                # For local hosts, prompt the user for consent
                # FIXME: this needs to understand whether we're running in interactive mode or not, should be part of MngrContext
                if not _prompt_user_for_installation():
                    raise PluginMngrError(
                        "Claude is not installed. Please install it manually with:\n"
                        "  curl -fsSL https://claude.ai/install.sh | bash"
                    )
            else:
                # FIXME: for remote hosts, we need to check whether the user has configured automatic installation
                #  and if not, raise an error here
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
            for local_folder in [
                Path.home() / ".claude" / "skills",
                Path.home() / ".claude" / "agents",
                Path.home() / ".claude" / "commands",
            ]:
                if local_folder.is_dir():
                    for file_path in local_folder.rglob("*"):
                        if file_path.is_file():
                            relative_path = file_path.relative_to(Path.home() / ".claude")
                            remote_path = Path.home() / ".claude" / relative_path
                            host.write_text_file(
                                remote_path,
                                file_path.read_text(),
                            )

        if config.sync_claude_json:
            claude_json_path = Path.home() / ".claude.json"
            if claude_json_path.exists():
                logger.info("Transferring ~/.claude.json to remote host...")
                host.write_text_file(
                    Path.home() / ".claude.json",
                    claude_json_path.read_text(),
                )
            else:
                logger.debug("Skipping ~/.claude.json (file does not exist)")

        if config.sync_claude_credentials:
            credentials_path = Path.home() / ".claude" / ".credentials.json"
            if credentials_path.exists():
                logger.info("Transferring ~/.claude/.credentials.json to remote host...")
                host.write_text_file(
                    Path.home() / ".claude" / ".credentials.json",
                    credentials_path.read_text(),
                )
            else:
                logger.debug("Skipping ~/.claude/.credentials.json (file does not exist)")
