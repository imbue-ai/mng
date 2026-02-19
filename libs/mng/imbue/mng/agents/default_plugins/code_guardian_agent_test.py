"""Tests for the code-guardian agent type."""

from pathlib import Path

import pluggy

from imbue.concurrency_group.concurrency_group import ConcurrencyGroup
from imbue.mng.agents.agent_registry import get_agent_class
from imbue.mng.agents.agent_registry import get_agent_config_class
from imbue.mng.agents.agent_registry import list_registered_agent_types
from imbue.mng.agents.agent_registry import resolve_agent_type
from imbue.mng.agents.default_plugins.claude_agent import ClaudeAgent
from imbue.mng.agents.default_plugins.claude_agent import ClaudeAgentConfig
from imbue.mng.agents.default_plugins.code_guardian_agent import CodeGuardianAgent
from imbue.mng.agents.default_plugins.code_guardian_agent import CodeGuardianAgentConfig
from imbue.mng.agents.default_plugins.code_guardian_agent import _CODE_GUARDIAN_SKILL_CONTENT
from imbue.mng.agents.default_plugins.code_guardian_agent import _SKILL_NAME
from imbue.mng.agents.default_plugins.code_guardian_agent import _install_skill_locally
from imbue.mng.config.data_types import MngConfig
from imbue.mng.config.data_types import MngContext
from imbue.mng.conftest import make_mng_ctx
from imbue.mng.primitives import AgentTypeName
from imbue.mng.primitives import CommandString


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


def test_code_guardian_config_inherits_claude_cli_args() -> None:
    """CodeGuardianAgentConfig should inherit ClaudeAgentConfig's default cli_args."""
    config = CodeGuardianAgentConfig()
    assert config.cli_args == ClaudeAgentConfig().cli_args


def test_code_guardian_config_has_no_custom_cli_args() -> None:
    """CodeGuardianAgentConfig should not add any custom cli_args beyond ClaudeAgentConfig."""
    config = CodeGuardianAgentConfig()
    assert config.cli_args == ()


def test_resolve_code_guardian_type_returns_code_guardian_agent_and_config() -> None:
    """Resolving code-guardian should return CodeGuardianAgent with CodeGuardianAgentConfig."""
    mng_config = MngConfig()
    resolved = resolve_agent_type(AgentTypeName("code-guardian"), mng_config)

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
    assert issubclass(CodeGuardianAgent, ClaudeAgent)


def test_install_skill_locally_creates_skill_file_in_non_interactive_mode(
    temp_mng_ctx: MngContext,
) -> None:
    """In non-interactive mode, _install_skill_locally should create the skill file without prompting."""
    # temp_mng_ctx has is_interactive=False by default, and HOME is set to tmp_path
    skill_path = Path.home() / ".claude" / "skills" / _SKILL_NAME / "SKILL.md"
    assert not skill_path.exists()

    _install_skill_locally(temp_mng_ctx)

    assert skill_path.exists()
    content = skill_path.read_text()
    assert content == _CODE_GUARDIAN_SKILL_CONTENT


def test_install_skill_locally_overwrites_existing_skill_in_non_interactive_mode(
    temp_mng_ctx: MngContext,
) -> None:
    """In non-interactive mode, _install_skill_locally should overwrite an existing skill file."""
    skill_path = Path.home() / ".claude" / "skills" / _SKILL_NAME / "SKILL.md"
    skill_path.parent.mkdir(parents=True, exist_ok=True)
    skill_path.write_text("old content")

    _install_skill_locally(temp_mng_ctx)

    assert skill_path.read_text() == _CODE_GUARDIAN_SKILL_CONTENT


def test_install_skill_locally_skips_when_content_unchanged(
    temp_mng_ctx: MngContext,
) -> None:
    """When skill content is already up to date, installation should be skipped."""
    skill_path = Path.home() / ".claude" / "skills" / _SKILL_NAME / "SKILL.md"
    skill_path.parent.mkdir(parents=True, exist_ok=True)
    skill_path.write_text(_CODE_GUARDIAN_SKILL_CONTENT)
    original_mtime = skill_path.stat().st_mtime

    _install_skill_locally(temp_mng_ctx)

    # File should not have been rewritten (mtime unchanged)
    assert skill_path.stat().st_mtime == original_mtime


def test_install_skill_locally_auto_approve_installs_without_prompting(
    temp_config: MngConfig,
    temp_profile_dir: Path,
    plugin_manager: "pluggy.PluginManager",
) -> None:
    """With is_auto_approve=True and is_interactive=True, skill should install without prompting."""
    with ConcurrencyGroup(name="test-auto-approve") as cg:
        auto_approve_ctx = make_mng_ctx(
            temp_config,
            plugin_manager,
            temp_profile_dir,
            is_interactive=True,
            is_auto_approve=True,
            concurrency_group=cg,
        )
        skill_path = Path.home() / ".claude" / "skills" / _SKILL_NAME / "SKILL.md"
        assert not skill_path.exists()

        # This would hang if prompting occurred, but auto_approve bypasses it
        _install_skill_locally(auto_approve_ctx)

        assert skill_path.exists()
        assert skill_path.read_text() == _CODE_GUARDIAN_SKILL_CONTENT
