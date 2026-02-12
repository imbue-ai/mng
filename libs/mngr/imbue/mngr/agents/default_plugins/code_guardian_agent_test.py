"""Tests for the code-guardian agent type."""

from imbue.mngr.agents.agent_registry import get_agent_class
from imbue.mngr.agents.agent_registry import get_agent_config_class
from imbue.mngr.agents.agent_registry import list_registered_agent_types
from imbue.mngr.agents.agent_registry import resolve_agent_type
from imbue.mngr.agents.default_plugins.code_guardian_agent import CodeGuardianAgent
from imbue.mngr.agents.default_plugins.code_guardian_agent import CodeGuardianAgentConfig
from imbue.mngr.agents.default_plugins.code_guardian_agent import _CODE_GUARDIAN_SKILL_CONTENT
from imbue.mngr.agents.default_plugins.code_guardian_agent import _SKILL_NAME
from imbue.mngr.config.data_types import MngrConfig
from imbue.mngr.primitives import AgentTypeName
from imbue.mngr.primitives import CommandString


def test_code_guardian_is_registered_in_agent_types() -> None:
    """Code-guardian should appear in the list of registered agent types."""
    agent_types = list_registered_agent_types()
    assert "code-guardian" in agent_types


def test_code_guardian_agent_class_is_code_guardian_agent() -> None:
    """Code-guardian should use CodeGuardianAgent as its agent class."""
    agent_class = get_agent_class("code-guardian")
    assert agent_class == CodeGuardianAgent


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


def test_code_guardian_config_includes_agents_and_agent_flags() -> None:
    """CodeGuardianAgentConfig cli_args should include --agents and --agent flags."""
    config = CodeGuardianAgentConfig()
    assert "--agents" in config.cli_args
    assert "--agent code-guardian" in config.cli_args


def test_code_guardian_config_agents_json_contains_skill_name() -> None:
    """The --agents JSON should reference the code-guardian skill."""
    config = CodeGuardianAgentConfig()
    assert '"code-guardian"' in config.cli_args
    assert "primary skill" in config.cli_args


def test_resolve_code_guardian_type_returns_code_guardian_agent_and_config() -> None:
    """Resolving code-guardian should return CodeGuardianAgent with CodeGuardianAgentConfig."""
    mngr_config = MngrConfig()
    resolved = resolve_agent_type(AgentTypeName("code-guardian"), mngr_config)

    assert resolved.agent_class == CodeGuardianAgent
    assert isinstance(resolved.agent_config, CodeGuardianAgentConfig)
    assert resolved.agent_config.command == CommandString("claude")


def test_code_guardian_skill_content_contains_inconsistency_instructions() -> None:
    """The embedded skill content should contain the identify-inconsistencies instructions."""
    assert "inconsistencies" in _CODE_GUARDIAN_SKILL_CONTENT.lower()
    assert "SKILL.md" not in _CODE_GUARDIAN_SKILL_CONTENT
    assert "_tasks/inconsistencies/" in _CODE_GUARDIAN_SKILL_CONTENT
    assert "code-guardian" in _CODE_GUARDIAN_SKILL_CONTENT


def test_code_guardian_skill_content_has_valid_frontmatter() -> None:
    """The skill content should have valid YAML frontmatter with name and description."""
    assert _CODE_GUARDIAN_SKILL_CONTENT.startswith("---\n")
    # Check that frontmatter ends
    second_separator = _CODE_GUARDIAN_SKILL_CONTENT.index("---", 4)
    assert second_separator > 0
    frontmatter = _CODE_GUARDIAN_SKILL_CONTENT[4:second_separator]
    assert "name:" in frontmatter
    assert "description:" in frontmatter


def test_code_guardian_skill_content_is_substantial() -> None:
    """The skill content should be a meaningful set of instructions."""
    assert len(_CODE_GUARDIAN_SKILL_CONTENT) > 100
    assert _SKILL_NAME == "code-guardian"


def test_code_guardian_agent_is_subclass_of_claude_agent() -> None:
    """CodeGuardianAgent should be a subclass of ClaudeAgent."""
    assert CodeGuardianAgent is not None
    assert issubclass(CodeGuardianAgent, CodeGuardianAgent.__bases__[0])
