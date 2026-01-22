"""Tests for agent registry."""

import pytest
from pydantic import Field

from imbue.mngr.agents.agent_registry import get_agent_class
from imbue.mngr.agents.agent_registry import get_agent_config_class
from imbue.mngr.agents.agent_registry import list_registered_agent_types
from imbue.mngr.agents.agent_registry import register_agent_config
from imbue.mngr.agents.default_plugins.claude_agent import ClaudeAgent
from imbue.mngr.agents.default_plugins.claude_agent import ClaudeAgentConfig
from imbue.mngr.agents.default_plugins.codex_agent import CodexAgentConfig
from imbue.mngr.config.data_types import AgentTypeConfig
from imbue.mngr.errors import ConfigParseError
from imbue.mngr.primitives import CommandString


def test_get_agent_config_class_returns_base_for_unregistered_type() -> None:
    """Unknown agent types should return the base AgentTypeConfig class."""
    config_class = get_agent_config_class("unknown-agent-type")
    assert config_class == AgentTypeConfig


def test_get_agent_config_class_returns_registered_type() -> None:
    """Registered agent types should return their specific config class."""
    config_class = get_agent_config_class("claude")
    assert config_class == ClaudeAgentConfig

    config_class = get_agent_config_class("codex")
    assert config_class == CodexAgentConfig


def test_list_registered_agent_types_includes_builtin_types() -> None:
    """Built-in agent types should be in the registry."""
    agent_types = list_registered_agent_types()
    assert "claude" in agent_types
    assert "codex" in agent_types


def test_codex_agent_config_has_default_command() -> None:
    """Codex agent config should have a default command."""
    config = CodexAgentConfig()
    assert config.command == CommandString("codex")


def test_register_custom_agent_type() -> None:
    """Should be able to register custom agent types."""

    class CustomAgentConfig(AgentTypeConfig):
        """Test custom agent config."""

        command: CommandString = Field(
            default=CommandString("custom-agent"),
            description="Custom agent command",
        )

    register_agent_config("test-custom", CustomAgentConfig)

    config_class = get_agent_config_class("test-custom")
    assert config_class == CustomAgentConfig

    config = config_class()
    assert config.command == CommandString("custom-agent")


def test_agent_type_config_merge_preserves_command() -> None:
    """Base AgentTypeConfig merge should handle command field."""
    base = AgentTypeConfig(command=CommandString("base-command"))
    override = AgentTypeConfig(command=CommandString("override-command"))

    merged = base.merge_with(override)

    assert merged.command == CommandString("override-command")


def test_agent_type_config_merge_keeps_base_command_when_override_none() -> None:
    """Merge should keep base command when override is None."""
    base = AgentTypeConfig(command=CommandString("base-command"))
    override = AgentTypeConfig()

    merged = base.merge_with(override)

    assert merged.command == CommandString("base-command")


def test_agent_type_config_merge_concatenates_cli_args() -> None:
    """Merge should concatenate cli_args from base and override."""
    base = AgentTypeConfig(cli_args="--verbose")
    override = AgentTypeConfig(cli_args="--debug")

    merged = base.merge_with(override)

    assert merged.cli_args == "--verbose --debug"


def test_agent_type_config_merge_cli_args_with_empty_base() -> None:
    """Merge should use override cli_args when base is empty."""
    base = AgentTypeConfig()
    override = AgentTypeConfig(cli_args="--debug")

    merged = base.merge_with(override)

    assert merged.cli_args == "--debug"


def test_agent_type_config_merge_cli_args_with_empty_override() -> None:
    """Merge should keep base cli_args when override is empty."""
    base = AgentTypeConfig(cli_args="--verbose")
    override = AgentTypeConfig()

    merged = base.merge_with(override)

    assert merged.cli_args == "--verbose"


def test_get_agent_class_returns_claude_agent_for_claude_type() -> None:
    """Claude agent type should return ClaudeAgent class."""
    agent_class = get_agent_class("claude")
    assert agent_class == ClaudeAgent


def test_claude_agent_config_merge_with_wrong_type_raises_error() -> None:
    """ClaudeAgentConfig.merge_with should raise ConfigParseError for wrong type."""
    base = ClaudeAgentConfig()
    override = CodexAgentConfig()

    with pytest.raises(ConfigParseError, match="Cannot merge ClaudeAgentConfig"):
        base.merge_with(override)
