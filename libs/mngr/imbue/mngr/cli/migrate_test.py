"""Unit tests for the migrate CLI command."""

import pluggy
from click.testing import CliRunner

from imbue.mngr.cli.migrate import _build_destroy_args
from imbue.mngr.cli.migrate import _user_specified_quiet
from imbue.mngr.cli.migrate import migrate
from imbue.mngr.main import cli
from imbue.mngr.primitives import AgentId


def test_migrate_command_exists() -> None:
    """The 'migrate' command should be registered on the CLI group."""
    assert "migrate" in cli.commands


def test_migrate_is_not_clone() -> None:
    """Migrate should be a distinct command object from clone."""
    assert cli.commands["migrate"] is not cli.commands["clone"]


def test_migrate_is_not_create() -> None:
    """Migrate should be a distinct command object from create."""
    assert cli.commands["migrate"] is not cli.commands["create"]


def test_migrate_requires_source_agent(
    cli_runner: CliRunner,
    plugin_manager: pluggy.PluginManager,
) -> None:
    """Migrate should error when no arguments are provided."""
    result = cli_runner.invoke(
        migrate,
        [],
        obj=plugin_manager,
        catch_exceptions=True,
    )

    assert result.exit_code != 0
    assert "SOURCE_AGENT" in result.output


def test_migrate_rejects_nonexistent_source_agent(
    cli_runner: CliRunner,
    plugin_manager: pluggy.PluginManager,
) -> None:
    """Migrate should error when the source agent does not exist."""
    result = cli_runner.invoke(
        migrate,
        ["nonexistent-agent-849271"],
        obj=plugin_manager,
        catch_exceptions=True,
    )

    assert result.exit_code != 0
    assert "not found" in result.output


def test_user_specified_quiet_detects_long_flag() -> None:
    assert _user_specified_quiet(("my-agent", "--quiet")) is True


def test_user_specified_quiet_detects_short_flag() -> None:
    assert _user_specified_quiet(("my-agent", "-q")) is True


def test_user_specified_quiet_false_when_absent() -> None:
    assert _user_specified_quiet(("my-agent", "--no-connect")) is False


def test_build_destroy_args_uses_agent_id() -> None:
    """Destroy args should contain the agent ID (not a name) to avoid name collisions."""
    agent_id = AgentId.generate()
    args = _build_destroy_args(agent_id)

    assert args[0] == str(agent_id)
    assert "--force" in args
    assert "--quiet" in args
    assert "--no-gc" in args


def test_build_destroy_args_does_not_contain_name() -> None:
    """Destroy args should only reference the agent by ID, never by name."""
    agent_id = AgentId.generate()
    args = _build_destroy_args(agent_id)

    # The first arg is the agent ID; no other arg should look like a name
    assert args[0].startswith("agent-")
    # All remaining args should be flags
    for arg in args[1:]:
        assert arg.startswith("-")
