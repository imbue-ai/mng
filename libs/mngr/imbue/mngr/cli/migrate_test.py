"""Unit tests for the migrate CLI command."""

import pluggy
from click.testing import CliRunner

from imbue.mngr.cli.migrate import _user_specified_quiet
from imbue.mngr.cli.migrate import migrate
from imbue.mngr.main import cli


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
