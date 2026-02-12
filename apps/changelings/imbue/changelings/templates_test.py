"""Tests for changeling built-in templates."""

from imbue.changelings.primitives import ChangelingTemplateName
from imbue.changelings.templates import BUILTIN_TEMPLATES
from imbue.changelings.templates import get_template
from imbue.changelings.templates import list_template_names


def test_code_guardian_template_exists() -> None:
    """The code-guardian template should be defined in BUILTIN_TEMPLATES."""
    template = get_template(ChangelingTemplateName("code-guardian"))
    assert template is not None


def test_code_guardian_template_uses_code_guardian_agent_type() -> None:
    """The code-guardian template should use the code-guardian mngr agent type."""
    template = get_template(ChangelingTemplateName("code-guardian"))
    assert template is not None
    assert template.agent_type == "code-guardian"


def test_code_guardian_template_has_default_message_with_inconsistency_instructions() -> None:
    """The code-guardian default message should instruct the agent to identify inconsistencies."""
    template = get_template(ChangelingTemplateName("code-guardian"))
    assert template is not None
    assert "inconsistencies" in template.default_message.lower()
    assert "commit" in template.default_message.lower()
    assert "PR" in template.default_message


def test_fixme_fairy_template_exists() -> None:
    """The fixme-fairy template should be defined."""
    template = get_template(ChangelingTemplateName("fixme-fairy"))
    assert template is not None
    assert template.agent_type == "claude"


def test_get_template_returns_none_for_unknown_template() -> None:
    """get_template should return None for unknown template names."""
    result = get_template(ChangelingTemplateName("nonexistent-template"))
    assert result is None


def test_list_template_names_returns_all_built_in_names() -> None:
    """list_template_names should return all built-in template names."""
    names = list_template_names()
    assert len(names) == len(BUILTIN_TEMPLATES)
    assert ChangelingTemplateName("code-guardian") in names
    assert ChangelingTemplateName("fixme-fairy") in names


def test_all_templates_have_required_fields() -> None:
    """Every built-in template should have agent_type, default_message, and description."""
    for name, template in BUILTIN_TEMPLATES.items():
        assert template.agent_type, f"Template {name} missing agent_type"
        assert template.default_message, f"Template {name} missing default_message"
        assert template.description, f"Template {name} missing description"
