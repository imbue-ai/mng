from pydantic import Field

from imbue.mng import hookimpl
from imbue.mng.config.data_types import AgentTypeConfig
from imbue.mng.errors import ConfigParseError
from imbue.mng.interfaces.agent import AgentInterface
from imbue.mng.primitives import CommandString


class PiCodingAgentConfig(AgentTypeConfig):
    """Config for the pi-coding agent type."""

    command: CommandString = Field(
        default=CommandString("pi"),
        description="Command to run the pi coding agent",
    )

    def merge_with(self, override: AgentTypeConfig) -> AgentTypeConfig:
        """Merge this config with an override config.

        Important note: despite the type signatures, any of these fields may be None
        in the override--this means that they were NOT set in the toml (and thus should
        be ignored).
        """
        if not isinstance(override, PiCodingAgentConfig):
            raise ConfigParseError("Cannot merge PiCodingAgentConfig with different agent config type")

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
    """Register the pi-coding agent type."""
    return ("pi-coding", None, PiCodingAgentConfig)
