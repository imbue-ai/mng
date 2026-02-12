"""Tests for the changeling run command."""

import sys

from imbue.changelings.cli.run import _resolve_message
from imbue.changelings.cli.run import build_mngr_create_command
from imbue.changelings.data_types import ChangelingDefinition
from imbue.changelings.primitives import ChangelingName
from imbue.changelings.primitives import ChangelingTemplateName
from imbue.changelings.templates import CODE_GUARDIAN_DEFAULT_MESSAGE


def _make_changeling(
    name: str = "test-changeling",
    template: str = "code-guardian",
    agent_type: str = "code-guardian",
    branch: str = "main",
    message: str | None = None,
    extra_mngr_args: str = "",
    env_vars: dict[str, str] | None = None,
) -> ChangelingDefinition:
    """Create a ChangelingDefinition for testing."""
    return ChangelingDefinition(
        name=ChangelingName(name),
        template=ChangelingTemplateName(template),
        agent_type=agent_type,
        branch=branch,
        message=message,
        extra_mngr_args=extra_mngr_args,
        env_vars=env_vars or {},
    )


def test_build_command_includes_python_executable_and_mngr_module() -> None:
    """The command should invoke Python with the mngr main module."""
    changeling = _make_changeling()
    cmd = build_mngr_create_command(changeling)

    assert cmd[0] == sys.executable
    assert cmd[1] == "-m"
    assert cmd[2] == "imbue.mngr.main"
    assert cmd[3] == "create"


def test_build_command_includes_agent_name_with_timestamp() -> None:
    """The agent name should include the changeling name and a timestamp."""
    changeling = _make_changeling(name="my-guardian")
    cmd = build_mngr_create_command(changeling)

    # The agent name is the 5th element (index 4)
    agent_name = cmd[4]
    assert agent_name.startswith("my-guardian-")
    # Should have a timestamp suffix like YYYY-MM-DD-HH-MM-SS
    suffix = agent_name[len("my-guardian-") :]
    parts = suffix.split("-")
    assert len(parts) == 6  # year, month, day, hour, minute, second


def test_build_command_uses_agent_type_from_definition() -> None:
    """The command should use the agent type from the changeling definition."""
    changeling = _make_changeling(agent_type="code-guardian")
    cmd = build_mngr_create_command(changeling)

    # The agent type is the 6th element (index 5)
    assert cmd[5] == "code-guardian"


def test_build_command_includes_no_connect_flag() -> None:
    """The command should include --no-connect since changelings run unattended."""
    changeling = _make_changeling()
    cmd = build_mngr_create_command(changeling)

    assert "--no-connect" in cmd


def test_build_command_includes_await_agent_stopped_flag() -> None:
    """The command should include --await-agent-stopped to wait for completion."""
    changeling = _make_changeling()
    cmd = build_mngr_create_command(changeling)

    assert "--await-agent-stopped" in cmd


def test_build_command_includes_creator_tag() -> None:
    """The command should tag the agent as created by changeling."""
    changeling = _make_changeling()
    cmd = build_mngr_create_command(changeling)

    tag_idx = cmd.index("CREATOR=changeling")
    assert cmd[tag_idx - 1] == "--tag"


def test_build_command_includes_changeling_name_tag() -> None:
    """The command should tag the agent with the changeling name."""
    changeling = _make_changeling(name="my-guardian")
    cmd = build_mngr_create_command(changeling)

    assert "CHANGELING=my-guardian" in cmd


def test_build_command_includes_base_branch() -> None:
    """The command should set --base-branch from the changeling definition."""
    changeling = _make_changeling(branch="develop")
    cmd = build_mngr_create_command(changeling)

    branch_idx = cmd.index("--base-branch")
    assert cmd[branch_idx + 1] == "develop"


def test_build_command_includes_new_branch_with_changeling_name() -> None:
    """The command should create a new branch named after the changeling."""
    changeling = _make_changeling(name="my-guardian")
    cmd = build_mngr_create_command(changeling)

    branch_idx = cmd.index("--new-branch")
    branch_name = cmd[branch_idx + 1]
    assert branch_name.startswith("changelings/my-guardian-")


def test_build_command_includes_message_from_template_default() -> None:
    """When no explicit message is set, the template's default message should be used."""
    changeling = _make_changeling(template="code-guardian", message=None)
    cmd = build_mngr_create_command(changeling)

    assert "--message" in cmd
    message_idx = cmd.index("--message")
    assert cmd[message_idx + 1] == CODE_GUARDIAN_DEFAULT_MESSAGE


def test_build_command_uses_explicit_message_over_template_default() -> None:
    """An explicit message in the changeling definition should override the template default."""
    changeling = _make_changeling(template="code-guardian", message="Custom instructions")
    cmd = build_mngr_create_command(changeling)

    message_idx = cmd.index("--message")
    assert cmd[message_idx + 1] == "Custom instructions"


def test_build_command_includes_env_vars() -> None:
    """Environment variables from the changeling should be passed via --env."""
    changeling = _make_changeling(env_vars={"API_KEY": "abc123", "DEBUG": "true"})
    cmd = build_mngr_create_command(changeling)

    assert "--env" in cmd
    assert "API_KEY=abc123" in cmd
    assert "DEBUG=true" in cmd


def test_build_command_includes_extra_mngr_args() -> None:
    """Extra mngr args from the changeling should be appended to the command."""
    changeling = _make_changeling(extra_mngr_args="--verbose --timeout 300")
    cmd = build_mngr_create_command(changeling)

    assert "--verbose" in cmd
    assert "--timeout" in cmd
    assert "300" in cmd


def test_build_command_omits_message_when_template_not_found_and_no_explicit_message() -> None:
    """When template is not found and no explicit message, --message should not appear."""
    changeling = _make_changeling(template="unknown-template", message=None)
    cmd = build_mngr_create_command(changeling)

    assert "--message" not in cmd


def test_resolve_message_returns_explicit_message() -> None:
    """_resolve_message should return the explicit message when set."""
    changeling = _make_changeling(message="Do this specific thing")
    result = _resolve_message(changeling)
    assert result == "Do this specific thing"


def test_resolve_message_falls_back_to_template_default() -> None:
    """_resolve_message should use the template default when no explicit message is set."""
    changeling = _make_changeling(template="code-guardian", message=None)
    result = _resolve_message(changeling)
    assert result == CODE_GUARDIAN_DEFAULT_MESSAGE


def test_resolve_message_returns_none_for_unknown_template_without_message() -> None:
    """_resolve_message should return None for unknown templates with no explicit message."""
    changeling = _make_changeling(template="unknown-template", message=None)
    result = _resolve_message(changeling)
    assert result is None
