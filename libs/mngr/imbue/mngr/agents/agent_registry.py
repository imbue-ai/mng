from __future__ import annotations

from pydantic import Field

from imbue.imbue_common.frozen_model import FrozenModel
from imbue.imbue_common.pure import pure
from imbue.mngr.agents.base_agent import BaseAgent
from imbue.mngr.agents.default_plugins import claude_agent
from imbue.mngr.agents.default_plugins import codex_agent
from imbue.mngr.config.data_types import AgentTypeConfig
from imbue.mngr.config.data_types import MngrConfig
from imbue.mngr.config.data_types import merge_cli_args
from imbue.mngr.interfaces.agent import AgentInterface
from imbue.mngr.primitives import AgentTypeName

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
    pm.register(claude_agent)
    pm.register(codex_agent)

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


class ResolvedAgentType(FrozenModel):
    """Result of resolving an agent type, including parent type resolution for custom types."""

    agent_class: type[AgentInterface] = Field(description="The agent implementation class to use")
    agent_config: AgentTypeConfig = Field(description="The merged agent type config")


@pure
def _apply_custom_overrides_to_parent_config(
    parent_config: AgentTypeConfig,
    custom_config: AgentTypeConfig,
) -> AgentTypeConfig:
    """Apply custom type overrides onto a parent config instance.

    Handles the case where parent_config may be a subclass of AgentTypeConfig
    (e.g., ClaudeAgentConfig) by constructing a new instance of the parent's
    concrete class with the base fields overridden.
    """
    # Build update dict from custom config's base fields
    updates: dict[str, object] = {}

    if custom_config.command is not None:
        updates["command"] = custom_config.command

    merged_cli_args = merge_cli_args(parent_config.cli_args, custom_config.cli_args)
    if merged_cli_args != parent_config.cli_args:
        updates["cli_args"] = merged_cli_args

    # Permissions override (replace) the parent's permissions per documentation.
    if custom_config.permissions:
        updates["permissions"] = custom_config.permissions

    if not updates:
        return parent_config

    return parent_config.model_copy(update=updates)


def resolve_agent_type(
    agent_type: AgentTypeName,
    config: MngrConfig,
) -> ResolvedAgentType:
    """Resolve an agent type name to its class and merged config.

    For custom types (defined in config with a parent_type), resolves through
    the parent type to get the correct agent class and config class, then
    applies the custom type's overrides on top of the parent defaults.

    For plugin-registered or direct command types, returns the registered
    class and config directly.
    """
    custom_config = config.agent_types.get(agent_type)

    # If this is a custom type with a parent_type, resolve through the parent
    if custom_config is not None and custom_config.parent_type is not None:
        parent_type = custom_config.parent_type
        agent_class = get_agent_class(str(parent_type))
        config_class = get_agent_config_class(str(parent_type))

        # Start with the parent's default config and apply custom overrides
        parent_default_config = config_class()
        merged_config = _apply_custom_overrides_to_parent_config(parent_default_config, custom_config)

        return ResolvedAgentType(
            agent_class=agent_class,
            agent_config=merged_config,
        )

    # Not a custom type with parent -- use direct lookup
    agent_class = get_agent_class(str(agent_type))
    config_class = get_agent_config_class(str(agent_type))

    if custom_config is not None:
        # Custom config exists but has no parent_type (e.g., just overrides for an existing type)
        agent_config = custom_config
    else:
        agent_config = config_class()

    return ResolvedAgentType(
        agent_class=agent_class,
        agent_config=agent_config,
    )
