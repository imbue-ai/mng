# Tests for the shared CLI options and definition builder.

import click
import pytest

from imbue.changelings.cli.options import _parse_key_value_pairs
from imbue.changelings.cli.options import build_definition_from_cli
from imbue.changelings.conftest import make_test_changeling
from imbue.changelings.data_types import DEFAULT_INITIAL_MESSAGE
from imbue.changelings.data_types import DEFAULT_SCHEDULE
from imbue.changelings.data_types import DEFAULT_SECRETS
from imbue.changelings.primitives import ChangelingName
from imbue.changelings.primitives import CronSchedule
from imbue.changelings.primitives import GitRepoUrl

# -- _parse_key_value_pairs tests --


def test_parse_key_value_pairs_single_pair() -> None:
    result = _parse_key_value_pairs(("KEY=VALUE",))
    assert result == {"KEY": "VALUE"}


def test_parse_key_value_pairs_multiple_pairs() -> None:
    result = _parse_key_value_pairs(("A=1", "B=2", "C=3"))
    assert result == {"A": "1", "B": "2", "C": "3"}


def test_parse_key_value_pairs_value_containing_equals() -> None:
    """Values can contain '=' characters (only split on first '=')."""
    result = _parse_key_value_pairs(("KEY=a=b=c",))
    assert result == {"KEY": "a=b=c"}


def test_parse_key_value_pairs_empty_value() -> None:
    result = _parse_key_value_pairs(("KEY=",))
    assert result == {"KEY": ""}


def test_parse_key_value_pairs_empty_tuple() -> None:
    result = _parse_key_value_pairs(())
    assert result == {}


def test_parse_key_value_pairs_missing_equals_raises() -> None:
    with pytest.raises(click.BadParameter, match="Expected KEY=VALUE"):
        _parse_key_value_pairs(("NO_EQUALS_HERE",))


# -- build_definition_from_cli tests (no base) --


def test_build_definition_defaults_agent_type_to_name() -> None:
    """When agent_type is not specified, it should default to the changeling name."""
    definition = build_definition_from_cli(
        name="fixme-fairy",
        schedule=None,
        repo=None,
        branch=None,
        message=None,
        agent_type=None,
        secrets=(),
        env_vars=(),
        extra_mngr_args=None,
        mngr_options=(),
        enabled=None,
        base=None,
    )

    assert definition.agent_type == "fixme-fairy"


def test_build_definition_uses_explicit_agent_type() -> None:
    """When agent_type is specified, it should override the name default."""
    definition = build_definition_from_cli(
        name="my-guardian",
        schedule=None,
        repo=None,
        branch=None,
        message=None,
        agent_type="claude",
        secrets=(),
        env_vars=(),
        extra_mngr_args=None,
        mngr_options=(),
        enabled=None,
        base=None,
    )

    assert definition.agent_type == "claude"


def test_build_definition_from_scratch_uses_model_defaults() -> None:
    """When building without a base, unspecified fields should use model defaults."""
    definition = build_definition_from_cli(
        name="test",
        schedule=None,
        repo=None,
        branch=None,
        message=None,
        agent_type=None,
        secrets=(),
        env_vars=(),
        extra_mngr_args=None,
        mngr_options=(),
        enabled=None,
        base=None,
    )

    assert definition.name == ChangelingName("test")
    assert definition.schedule == CronSchedule(DEFAULT_SCHEDULE)
    assert definition.repo is None
    assert definition.branch == "main"
    assert definition.initial_message == DEFAULT_INITIAL_MESSAGE
    assert definition.secrets == DEFAULT_SECRETS
    assert definition.env_vars == {}
    assert definition.mngr_options == {}
    assert definition.extra_mngr_args == ""
    assert definition.is_enabled is True


def test_build_definition_from_scratch_with_all_fields() -> None:
    """When all fields are specified, they should all be set on the definition."""
    definition = build_definition_from_cli(
        name="full-test",
        schedule="0 4 * * 1",
        repo="git@github.com:org/repo.git",
        branch="develop",
        message="Custom message",
        agent_type="custom-agent",
        secrets=("MY_KEY",),
        env_vars=("DEBUG=true",),
        extra_mngr_args="--verbose",
        mngr_options=("gpu=a10g",),
        enabled=False,
        base=None,
    )

    assert definition.name == ChangelingName("full-test")
    assert definition.schedule == CronSchedule("0 4 * * 1")
    assert definition.repo == GitRepoUrl("git@github.com:org/repo.git")
    assert definition.branch == "develop"
    assert definition.initial_message == "Custom message"
    assert definition.agent_type == "custom-agent"
    assert definition.secrets == ("MY_KEY",)
    assert definition.env_vars == {"DEBUG": "true"}
    assert definition.extra_mngr_args == "--verbose"
    assert definition.mngr_options == {"gpu": "a10g"}
    assert definition.is_enabled is False


# -- build_definition_from_cli tests (with base) --


def test_build_definition_with_base_keeps_base_values_when_no_overrides() -> None:
    """When all CLI args are empty/None, the base definition should be returned unchanged."""
    base = make_test_changeling(
        name="original",
        agent_type="code-guardian",
        branch="develop",
        initial_message="Original message",
    )

    definition = build_definition_from_cli(
        name="original",
        schedule=None,
        repo=None,
        branch=None,
        message=None,
        agent_type=None,
        secrets=(),
        env_vars=(),
        extra_mngr_args=None,
        mngr_options=(),
        enabled=None,
        base=base,
    )

    assert definition.agent_type == "code-guardian"
    assert definition.branch == "develop"
    assert definition.initial_message == "Original message"


def test_build_definition_with_base_overrides_specified_fields() -> None:
    """CLI args should override base values when specified."""
    base = make_test_changeling(
        name="original",
        agent_type="code-guardian",
        branch="main",
    )

    definition = build_definition_from_cli(
        name="original",
        schedule="0 5 * * *",
        repo=None,
        branch="develop",
        message="New message",
        agent_type="claude",
        secrets=(),
        env_vars=(),
        extra_mngr_args=None,
        mngr_options=(),
        enabled=None,
        base=base,
    )

    assert definition.schedule == CronSchedule("0 5 * * *")
    assert definition.branch == "develop"
    assert definition.initial_message == "New message"
    assert definition.agent_type == "claude"


def test_build_definition_with_base_overrides_secrets_when_specified() -> None:
    """Explicit --secret args should replace the base secrets."""
    base = make_test_changeling(secrets=("ORIGINAL_KEY",))

    definition = build_definition_from_cli(
        name="test-changeling",
        schedule=None,
        repo=None,
        branch=None,
        message=None,
        agent_type=None,
        secrets=("NEW_KEY", "OTHER_KEY"),
        env_vars=(),
        extra_mngr_args=None,
        mngr_options=(),
        enabled=None,
        base=base,
    )

    assert definition.secrets == ("NEW_KEY", "OTHER_KEY")


def test_build_definition_with_base_overrides_mngr_options_when_specified() -> None:
    """Explicit -o/--option args should replace the base mngr_options."""
    base = make_test_changeling(mngr_options={"old_key": "old_value"})

    definition = build_definition_from_cli(
        name="test-changeling",
        schedule=None,
        repo=None,
        branch=None,
        message=None,
        agent_type=None,
        secrets=(),
        env_vars=(),
        extra_mngr_args=None,
        mngr_options=("new_key=new_value",),
        enabled=None,
        base=base,
    )

    assert definition.mngr_options == {"new_key": "new_value"}
