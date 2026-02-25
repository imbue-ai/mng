"""Tests for the coder agent type and autofix skill installation."""

from pathlib import Path

import pluggy

from imbue.concurrency_group.concurrency_group import ConcurrencyGroup
from imbue.mng.agents.agent_registry import get_agent_class
from imbue.mng.agents.agent_registry import get_agent_config_class
from imbue.mng.agents.agent_registry import list_registered_agent_types
from imbue.mng.agents.agent_registry import resolve_agent_type
from imbue.mng.agents.default_plugins.autofix_skill import _AUTOFIX_SKILL_CONTENT
from imbue.mng.agents.default_plugins.autofix_skill import _AUTOFIX_VERIFY_AND_FIX_CONTENT
from imbue.mng.agents.default_plugins.autofix_skill import _SKILL_NAME
from imbue.mng.agents.default_plugins.autofix_skill import install_autofix_skill_locally
from imbue.mng.agents.default_plugins.claude_agent import ClaudeAgent
from imbue.mng.agents.default_plugins.claude_agent import ClaudeAgentConfig
from imbue.mng.agents.default_plugins.coder_agent import CoderAgent
from imbue.mng.agents.default_plugins.coder_agent import CoderAgentConfig
from imbue.mng.config.data_types import MngConfig
from imbue.mng.config.data_types import MngContext
from imbue.mng.conftest import make_mng_ctx
from imbue.mng.primitives import AgentTypeName
from imbue.mng.primitives import CommandString

# -- Registration tests -------------------------------------------------------


def test_coder_is_registered_in_agent_types() -> None:
    """The coder agent type should appear in the list of registered agent types."""
    assert "coder" in list_registered_agent_types()


def test_coder_agent_class_is_correct() -> None:
    """The coder agent type should return CoderAgent."""
    assert get_agent_class("coder") == CoderAgent


def test_coder_config_class_is_correct() -> None:
    """The coder agent type should return CoderAgentConfig."""
    assert get_agent_config_class("coder") == CoderAgentConfig


# -- Config inheritance tests --------------------------------------------------


def test_coder_config_inherits_claude_defaults() -> None:
    """CoderAgentConfig should have the same defaults as ClaudeAgentConfig."""
    config = CoderAgentConfig()
    assert config.command == CommandString("claude")
    assert config.sync_home_settings is True
    assert config.check_installation is True


def test_coder_config_has_no_custom_cli_args() -> None:
    """CoderAgentConfig should not add any custom cli_args."""
    config = CoderAgentConfig()
    assert config.cli_args == ()


# -- Type resolution tests -----------------------------------------------------


def test_resolve_coder_returns_correct_agent_and_config() -> None:
    """Resolving coder should return CoderAgent and CoderAgentConfig."""
    mng_config = MngConfig()
    resolved = resolve_agent_type(AgentTypeName("coder"), mng_config)

    assert resolved.agent_class == CoderAgent
    assert isinstance(resolved.agent_config, CoderAgentConfig)
    assert resolved.agent_config.command == CommandString("claude")


# -- Subclass tests ------------------------------------------------------------


def test_coder_is_subclass_of_claude_agent() -> None:
    """CoderAgent should be a subclass of ClaudeAgent."""
    assert issubclass(CoderAgent, ClaudeAgent)


def test_coder_config_is_subclass_of_claude_config() -> None:
    """CoderAgentConfig should be a subclass of ClaudeAgentConfig."""
    assert issubclass(CoderAgentConfig, ClaudeAgentConfig)


# -- Skill content tests -------------------------------------------------------


def test_autofix_skill_content_has_valid_frontmatter() -> None:
    """The autofix skill content should have valid YAML frontmatter."""
    assert _AUTOFIX_SKILL_CONTENT.startswith("---\n")
    second_separator = _AUTOFIX_SKILL_CONTENT.index("---", 4)
    assert second_separator > 0
    frontmatter = _AUTOFIX_SKILL_CONTENT[4:second_separator]
    assert "name:" in frontmatter
    assert "description:" in frontmatter


def test_autofix_skill_content_is_substantial() -> None:
    """The autofix skill content should be a meaningful set of instructions."""
    assert len(_AUTOFIX_SKILL_CONTENT) > 100
    assert _SKILL_NAME == "autofix"


def test_autofix_verify_and_fix_content_is_substantial() -> None:
    """The verify-and-fix content should be a meaningful set of instructions."""
    assert len(_AUTOFIX_VERIFY_AND_FIX_CONTENT) > 100
    assert "Issue Categories" in _AUTOFIX_VERIFY_AND_FIX_CONTENT
    assert "Step 1: Gather Context" in _AUTOFIX_VERIFY_AND_FIX_CONTENT


def test_autofix_skill_content_contains_fix_loop_instructions() -> None:
    """The autofix skill should contain fix loop instructions."""
    assert "Fix Loop" in _AUTOFIX_SKILL_CONTENT
    assert "general-purpose" in _AUTOFIX_SKILL_CONTENT
    assert ".autofix/result" in _AUTOFIX_SKILL_CONTENT


# -- Skill installation tests --------------------------------------------------


def test_install_autofix_skill_locally_creates_files(
    temp_mng_ctx: MngContext,
) -> None:
    """install_autofix_skill_locally should create both SKILL.md and verify-and-fix.md."""
    skill_dir = Path.home() / ".claude" / "skills" / _SKILL_NAME
    skill_md = skill_dir / "SKILL.md"
    verify_fix_md = skill_dir / "verify-and-fix.md"

    assert not skill_md.exists()
    assert not verify_fix_md.exists()

    install_autofix_skill_locally(temp_mng_ctx)

    assert skill_md.exists()
    assert skill_md.read_text() == _AUTOFIX_SKILL_CONTENT
    assert verify_fix_md.exists()
    assert verify_fix_md.read_text() == _AUTOFIX_VERIFY_AND_FIX_CONTENT


def test_install_autofix_skill_locally_overwrites_existing(
    temp_mng_ctx: MngContext,
) -> None:
    """install_autofix_skill_locally should overwrite existing skill files."""
    skill_dir = Path.home() / ".claude" / "skills" / _SKILL_NAME
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text("old content")
    (skill_dir / "verify-and-fix.md").write_text("old content")

    install_autofix_skill_locally(temp_mng_ctx)

    assert (skill_dir / "SKILL.md").read_text() == _AUTOFIX_SKILL_CONTENT
    assert (skill_dir / "verify-and-fix.md").read_text() == _AUTOFIX_VERIFY_AND_FIX_CONTENT


def test_install_autofix_skill_locally_skips_when_unchanged(
    temp_mng_ctx: MngContext,
) -> None:
    """When skill content is already up to date, installation should be skipped."""
    skill_dir = Path.home() / ".claude" / "skills" / _SKILL_NAME
    skill_dir.mkdir(parents=True, exist_ok=True)
    skill_md = skill_dir / "SKILL.md"
    verify_fix_md = skill_dir / "verify-and-fix.md"
    skill_md.write_text(_AUTOFIX_SKILL_CONTENT)
    verify_fix_md.write_text(_AUTOFIX_VERIFY_AND_FIX_CONTENT)
    original_skill_mtime = skill_md.stat().st_mtime
    original_verify_mtime = verify_fix_md.stat().st_mtime

    install_autofix_skill_locally(temp_mng_ctx)

    # Files should not have been rewritten (mtime unchanged)
    assert skill_md.stat().st_mtime == original_skill_mtime
    assert verify_fix_md.stat().st_mtime == original_verify_mtime


def test_install_autofix_skill_locally_auto_approve(
    temp_config: MngConfig,
    temp_profile_dir: Path,
    plugin_manager: "pluggy.PluginManager",
) -> None:
    """With is_auto_approve=True, skill should install without prompting."""
    with ConcurrencyGroup(name="test-auto-approve") as cg:
        auto_approve_ctx = make_mng_ctx(
            temp_config,
            plugin_manager,
            temp_profile_dir,
            is_interactive=True,
            is_auto_approve=True,
            concurrency_group=cg,
        )
        skill_dir = Path.home() / ".claude" / "skills" / _SKILL_NAME
        skill_md = skill_dir / "SKILL.md"
        assert not skill_md.exists()

        install_autofix_skill_locally(auto_approve_ctx)

        assert skill_md.exists()
        assert skill_md.read_text() == _AUTOFIX_SKILL_CONTENT
