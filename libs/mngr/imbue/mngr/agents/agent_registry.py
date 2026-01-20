from __future__ import annotations

from pydantic import Field

from imbue.mngr import hookimpl
from imbue.mngr.agents.base_agent import BaseAgent
from imbue.mngr.config.data_types import AgentTypeConfig
from imbue.mngr.errors import NoCommandDefinedError
from imbue.mngr.interfaces.agent import AgentInterface
from imbue.mngr.primitives import AgentTypeName
from imbue.mngr.primitives import CommandString

# =============================================================================
# Agent Registry
# =============================================================================

_agent_class_registry: dict[AgentTypeName, type[AgentInterface]] = {}
_agent_config_registry: dict[AgentTypeName, type[AgentTypeConfig]] = {}
# Use a mutable container to track state without 'global' keyword
_registry_state: dict[str, bool] = {"agents_loaded": False}


def load_agents_from_plugins(pm) -> None:
    """Load agent types from plugins via the register_agent_type hook."""
    if _registry_state["agents_loaded"]:
        return

    # Register built-in agent type classes (each has a hookimpl static method)
    pm.register(ClaudeAgentConfig)
    pm.register(CodexAgentConfig)

    # Call the hook to get all agent type registrations
    # Each implementation returns a single tuple
    all_registrations = pm.hook.register_agent_type()

    for registration in all_registrations:
        if registration is not None:
            agent_type_name, agent_class, config_class = registration
            _register_agent_internal(agent_type_name, agent_class, config_class)

    _registry_state["agents_loaded"] = True


def _register_agent_internal(
    agent_type: str,
    agent_class: type[AgentInterface] | None = None,
    config_class: type[AgentTypeConfig] | None = None,
) -> None:
    """Internal function to register an agent type."""
    key = AgentTypeName(agent_type)
    if agent_class is not None:
        _agent_class_registry[key] = agent_class
    if config_class is not None:
        _agent_config_registry[key] = config_class


def get_agent_class(agent_type: str) -> type[AgentInterface]:
    """Get the agent class, defaulting to BaseAgent."""
    key = AgentTypeName(agent_type)
    if key not in _agent_class_registry:
        return BaseAgent
    return _agent_class_registry[key]


def get_agent_config_class(agent_type: str) -> type[AgentTypeConfig]:
    """Get the config class for an agent type.

    Returns the base AgentTypeConfig if no specific type is registered.
    """
    key = AgentTypeName(agent_type)
    if key not in _agent_config_registry:
        return AgentTypeConfig
    return _agent_config_registry[key]


def list_registered_agent_types() -> list[str]:
    """List all registered agent type names."""
    all_types = set(_agent_class_registry.keys()) | set(_agent_config_registry.keys())
    return sorted(str(k) for k in all_types)


def _register_agent(
    agent_type: str,
    agent_class: type[AgentInterface] | None = None,
    config_class: type[AgentTypeConfig] | None = None,
) -> None:
    """Register agent class and/or config for an agent type at runtime.

    This is a convenience function for programmatic registration, useful for
    testing or dynamic agent type creation. For plugins, prefer using the
    @hookimpl decorator with register_agent_type().
    """
    _register_agent_internal(agent_type, agent_class, config_class)


def register_agent_config(
    agent_type: str,
    config_class: type[AgentTypeConfig],
) -> None:
    """Register an agent config class for an agent type.

    This function exists primarily for testing and programmatic registration.
    For plugins, prefer using the @hookimpl decorator with register_agent_type().
    """
    _register_agent(agent_type, config_class=config_class)


# =============================================================================
# Built-in Agent Classes
# =============================================================================


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


# =============================================================================
# Built-in Agent Config Classes
# =============================================================================


class ClaudeAgentConfig(AgentTypeConfig):
    """Config for the claude agent type."""

    command: CommandString = Field(
        default=CommandString("claude"),
        description="Command to run claude agent",
    )

    @staticmethod
    @hookimpl
    def register_agent_type() -> tuple[str, type[AgentInterface] | None, type[AgentTypeConfig]]:
        """Register the claude agent type."""
        return ("claude", ClaudeAgent, ClaudeAgentConfig)


class CodexAgentConfig(AgentTypeConfig):
    """Config for the codex agent type."""

    command: CommandString = Field(
        default=CommandString("codex"),
        description="Command to run codex agent",
    )

    @staticmethod
    @hookimpl
    def register_agent_type() -> tuple[str, type[AgentInterface] | None, type[AgentTypeConfig]]:
        """Register the codex agent type."""
        return ("codex", None, CodexAgentConfig)
