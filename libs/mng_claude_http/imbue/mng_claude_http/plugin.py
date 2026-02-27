from pydantic import Field

from imbue.mng import hookimpl
from imbue.mng.config.data_types import AgentTypeConfig
from imbue.mng.errors import ConfigParseError
from imbue.mng.interfaces.agent import AgentInterface
from imbue.mng.primitives import CommandString


class ClaudeHttpAgentConfig(AgentTypeConfig):
    """Config for the claude-http agent type.

    This agent type runs a web server that provides a browser-based interface
    to Claude Code using the --sdk-url WebSocket protocol.
    """

    command: CommandString = Field(
        default=CommandString("python -m imbue.mng_claude_http.cli serve"),
        description="Command to start the claude-http web server",
    )

    def merge_with(self, override: AgentTypeConfig) -> AgentTypeConfig:
        if not isinstance(override, ClaudeHttpAgentConfig):
            raise ConfigParseError("Cannot merge ClaudeHttpAgentConfig with different agent config type")

        merged_parent_type = override.parent_type if override.parent_type is not None else self.parent_type
        merged_command = self.command
        if hasattr(override, "command") and override.command is not None:
            merged_command = override.command
        merged_cli_args = self.cli_args + override.cli_args if override.cli_args else self.cli_args
        merged_permissions = self.permissions
        if override.permissions is not None:
            merged_permissions = list(self.permissions) + list(override.permissions)

        return self.__class__(
            parent_type=merged_parent_type,
            cli_args=merged_cli_args,
            command=merged_command,
            permissions=merged_permissions,
        )


@hookimpl
def register_agent_type() -> tuple[str, type[AgentInterface] | None, type[AgentTypeConfig]]:
    """Register the claude-http agent type."""
    return ("claude-http", None, ClaudeHttpAgentConfig)
