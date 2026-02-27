from imbue.mng.config.data_types import AgentTypeConfig
from imbue.mng.primitives import AgentTypeName

# =============================================================================
# Agent Config Registry
# =============================================================================

_agent_config_registry: dict[AgentTypeName, type[AgentTypeConfig]] = {}


def register_agent_config(
    agent_type: str,
    config_class: type[AgentTypeConfig],
) -> None:
    """Register a config class for an agent type."""
    _agent_config_registry[AgentTypeName(agent_type)] = config_class


def get_agent_config_class(agent_type: str) -> type[AgentTypeConfig]:
    """Get the config class for an agent type.

    Returns the base AgentTypeConfig if no specific type is registered.
    """
    key = AgentTypeName(agent_type)
    if key not in _agent_config_registry:
        return AgentTypeConfig
    return _agent_config_registry[key]


def list_registered_agent_config_types() -> list[str]:
    """List all agent type names with registered config classes."""
    return sorted(str(k) for k in _agent_config_registry.keys())


def reset_agent_config_registry() -> None:
    """Reset the registry. Used for test isolation."""
    _agent_config_registry.clear()
