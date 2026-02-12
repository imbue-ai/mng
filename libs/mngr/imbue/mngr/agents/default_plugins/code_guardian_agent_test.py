"""Tests for the code-guardian agent type."""

from imbue.mngr.agents.agent_registry import get_agent_class
from imbue.mngr.agents.agent_registry import get_agent_config_class
from imbue.mngr.agents.agent_registry import list_registered_agent_types
from imbue.mngr.agents.agent_registry import resolve_agent_type
from imbue.mngr.agents.default_plugins.claude_agent import ClaudeAgent
from imbue.mngr.agents.default_plugins.code_guardian_agent import CodeGuardianAgentConfig
from imbue.mngr.config.data_types import MngrConfig
from imbue.mngr.primitives import AgentTypeName
from imbue.mngr.primitives import CommandString


def test_code_guardian_is_registered_in_agent_types() -> None:
    """Code-guardian should appear in the list of registered agent types."""
    agent_types = list_registered_agent_types()
    assert "code-guardian" in agent_types


def test_code_guardian_agent_class_is_claude_agent() -> None:
    """Code-guardian should use ClaudeAgent as its agent class."""
    agent_class = get_agent_class("code-guardian")
    assert agent_class == ClaudeAgent


def test_code_guardian_config_class_is_code_guardian_agent_config() -> None:
    """Code-guardian should return CodeGuardianAgentConfig."""
    config_class = get_agent_config_class("code-guardian")
    assert config_class == CodeGuardianAgentConfig


def test_code_guardian_config_inherits_claude_defaults() -> None:
    """CodeGuardianAgentConfig should have the same defaults as ClaudeAgentConfig."""
    config = CodeGuardianAgentConfig()
    assert config.command == CommandString("claude")
    assert config.sync_home_settings is True
    assert config.check_installation is True


def test_resolve_code_guardian_type_returns_claude_agent_and_config() -> None:
    """Resolving code-guardian should return ClaudeAgent with CodeGuardianAgentConfig."""
    mngr_config = MngrConfig()
    resolved = resolve_agent_type(AgentTypeName("code-guardian"), mngr_config)

    assert resolved.agent_class == ClaudeAgent
    assert isinstance(resolved.agent_config, CodeGuardianAgentConfig)
    assert resolved.agent_config.command == CommandString("claude")
