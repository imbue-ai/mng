import pytest

from imbue.changelings.errors import ChangelingConfigError
from imbue.changelings.primitives import ChangelingTemplateName
from imbue.changelings.templates import KNOWN_TEMPLATE_NAMES
from imbue.changelings.templates import TEMPLATE_MESSAGE_BY_NAME
from imbue.changelings.templates import get_template_message
from imbue.changelings.templates import is_known_template


class TestGetTemplateMessage:
    def test_code_guardian_returns_message(self) -> None:
        msg = get_template_message(ChangelingTemplateName("code-guardian"))
        assert "inconsistencies" in msg.lower()
        assert "changeling/code-guardian" in msg

    def test_fixme_fairy_returns_message(self) -> None:
        msg = get_template_message(ChangelingTemplateName("fixme-fairy"))
        assert "FIXME" in msg

    def test_unknown_template_raises(self) -> None:
        with pytest.raises(ChangelingConfigError, match="Unknown template"):
            get_template_message(ChangelingTemplateName("nonexistent-template"))

    def test_all_known_templates_have_messages(self) -> None:
        for name in KNOWN_TEMPLATE_NAMES:
            msg = get_template_message(name)
            assert isinstance(msg, str)
            assert len(msg) > 0


class TestIsKnownTemplate:
    def test_known_template(self) -> None:
        assert is_known_template(ChangelingTemplateName("code-guardian")) is True

    def test_unknown_template(self) -> None:
        assert is_known_template(ChangelingTemplateName("unknown")) is False


class TestTemplateRegistry:
    def test_expected_templates_exist(self) -> None:
        expected = {
            "code-guardian",
            "fixme-fairy",
            "test-troll",
            "coverage-hunter",
            "doc-regent",
            "docstring-scribe",
            "security-soldier",
            "issue-servant",
            "module-warden",
        }
        actual = {str(name) for name in KNOWN_TEMPLATE_NAMES}
        assert actual == expected

    def test_template_messages_match_known_names(self) -> None:
        assert set(TEMPLATE_MESSAGE_BY_NAME.keys()) == KNOWN_TEMPLATE_NAMES

    def test_all_template_messages_mention_changeling_prefix(self) -> None:
        for name, msg in TEMPLATE_MESSAGE_BY_NAME.items():
            assert "changeling/" in msg, f"Template '{name}' message should mention changeling/ branch/PR prefix"
