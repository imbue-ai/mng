"""Tests for the fixme-fairy agent type."""

from pathlib import Path

import pluggy

from imbue.concurrency_group.concurrency_group import ConcurrencyGroup
from imbue.mng.agents.agent_registry import get_agent_class
from imbue.mng.agents.agent_registry import get_agent_config_class
from imbue.mng.agents.agent_registry import list_registered_agent_types
from imbue.mng.agents.agent_registry import resolve_agent_type
from imbue.mng.agents.default_plugins.claude_agent import ClaudeAgent
from imbue.mng.agents.default_plugins.claude_agent import ClaudeAgentConfig
from imbue.mng.agents.default_plugins.fixme_fairy_agent import FixmeFairyAgent
from imbue.mng.agents.default_plugins.fixme_fairy_agent import FixmeFairyAgentConfig
from imbue.mng.agents.default_plugins.fixme_fairy_agent import _FIXME_FAIRY_SKILL_CONTENT
from imbue.mng.agents.default_plugins.fixme_fairy_agent import _SKILL_NAME
from imbue.mng.agents.default_plugins.fixme_fairy_agent import _install_skill_locally
from imbue.mng.config.data_types import MngConfig
from imbue.mng.config.data_types import MngContext
from imbue.mng.conftest import make_mng_ctx
from imbue.mng.primitives import AgentTypeName
from imbue.mng.primitives import CommandString


def test_fixme_fairy_is_registered_in_agent_types() -> None:
    """Fixme-fairy should appear in the list of registered agent types."""
    agent_types = list_registered_agent_types()
    assert "fixme-fairy" in agent_types


def test_fixme_fairy_agent_class_is_fixme_fairy_agent() -> None:
    """Fixme-fairy should use FixmeFairyAgent as its agent class."""
    agent_class = get_agent_class("fixme-fairy")
    assert agent_class == FixmeFairyAgent


def test_fixme_fairy_config_class_is_fixme_fairy_agent_config() -> None:
    """Fixme-fairy should return FixmeFairyAgentConfig."""
    config_class = get_agent_config_class("fixme-fairy")
    assert config_class == FixmeFairyAgentConfig


def test_fixme_fairy_config_inherits_claude_defaults() -> None:
    """FixmeFairyAgentConfig should have the same defaults as ClaudeAgentConfig."""
    config = FixmeFairyAgentConfig()
    assert config.command == CommandString("claude")
    assert config.sync_home_settings is True
    assert config.check_installation is True


def test_fixme_fairy_config_inherits_claude_cli_args() -> None:
    """FixmeFairyAgentConfig should inherit ClaudeAgentConfig's default cli_args."""
    config = FixmeFairyAgentConfig()
    assert config.cli_args == ClaudeAgentConfig().cli_args


def test_fixme_fairy_config_has_no_custom_cli_args() -> None:
    """FixmeFairyAgentConfig should not add any custom cli_args beyond ClaudeAgentConfig."""
    config = FixmeFairyAgentConfig()
    assert config.cli_args == ()


def test_resolve_fixme_fairy_type_returns_fixme_fairy_agent_and_config() -> None:
    """Resolving fixme-fairy should return FixmeFairyAgent with FixmeFairyAgentConfig."""
    mng_config = MngConfig()
    resolved = resolve_agent_type(AgentTypeName("fixme-fairy"), mng_config)

    assert resolved.agent_class == FixmeFairyAgent
    assert isinstance(resolved.agent_config, FixmeFairyAgentConfig)
    assert resolved.agent_config.command == CommandString("claude")


def test_fixme_fairy_skill_content_contains_fixme_instructions() -> None:
    """The embedded skill content should contain the FIXME-fixing instructions."""
    assert "fixme" in _FIXME_FAIRY_SKILL_CONTENT.lower()
    assert "SKILL.md" not in _FIXME_FAIRY_SKILL_CONTENT
    assert "uv run pytest" in _FIXME_FAIRY_SKILL_CONTENT
    assert "fixme-fairy" in _FIXME_FAIRY_SKILL_CONTENT


def test_fixme_fairy_skill_content_has_valid_frontmatter() -> None:
    """The skill content should have valid YAML frontmatter with name and description."""
    assert _FIXME_FAIRY_SKILL_CONTENT.startswith("---\n")
    # Check that frontmatter ends
    second_separator = _FIXME_FAIRY_SKILL_CONTENT.index("---", 4)
    assert second_separator > 0
    frontmatter = _FIXME_FAIRY_SKILL_CONTENT[4:second_separator]
    assert "name:" in frontmatter
    assert "description:" in frontmatter


def test_fixme_fairy_skill_content_is_substantial() -> None:
    """The skill content should be a meaningful set of instructions."""
    assert len(_FIXME_FAIRY_SKILL_CONTENT) > 100
    assert _SKILL_NAME == "fixme-fairy"


def test_fixme_fairy_agent_is_subclass_of_claude_agent() -> None:
    """FixmeFairyAgent should be a subclass of ClaudeAgent."""
    assert issubclass(FixmeFairyAgent, ClaudeAgent)


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
    assert content == _FIXME_FAIRY_SKILL_CONTENT


def test_install_skill_locally_overwrites_existing_skill_in_non_interactive_mode(
    temp_mng_ctx: MngContext,
) -> None:
    """In non-interactive mode, _install_skill_locally should overwrite an existing skill file."""
    skill_path = Path.home() / ".claude" / "skills" / _SKILL_NAME / "SKILL.md"
    skill_path.parent.mkdir(parents=True, exist_ok=True)
    skill_path.write_text("old content")

    _install_skill_locally(temp_mng_ctx)

    assert skill_path.read_text() == _FIXME_FAIRY_SKILL_CONTENT


def test_install_skill_locally_skips_when_content_unchanged(
    temp_mng_ctx: MngContext,
) -> None:
    """When skill content is already up to date, installation should be skipped."""
    skill_path = Path.home() / ".claude" / "skills" / _SKILL_NAME / "SKILL.md"
    skill_path.parent.mkdir(parents=True, exist_ok=True)
    skill_path.write_text(_FIXME_FAIRY_SKILL_CONTENT)
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
        assert skill_path.read_text() == _FIXME_FAIRY_SKILL_CONTENT
