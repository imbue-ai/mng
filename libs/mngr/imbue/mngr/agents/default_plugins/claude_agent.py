from __future__ import annotations

from pydantic import Field

from imbue.mngr import hookimpl
from imbue.mngr.agents.base_agent import BaseAgent
from imbue.mngr.config.data_types import AgentTypeConfig
from imbue.mngr.errors import NoCommandDefinedError
from imbue.mngr.interfaces.agent import AgentInterface
from imbue.mngr.primitives import CommandString


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
        return CommandString(f"export MAIN_CLAUDE_SESSION_ID={agent_uuid} && ( {resume_cmd} ) || {create_cmd}")


class ClaudeAgentConfig(AgentTypeConfig):
    """Config for the claude agent type."""

    command: CommandString = Field(
        default=CommandString("claude"),
        description="Command to run claude agent",
    )


@hookimpl
def register_agent_type() -> tuple[str, type[AgentInterface] | None, type[AgentTypeConfig]]:
    """Register the claude agent type."""
    return ("claude", ClaudeAgent, ClaudeAgentConfig)
