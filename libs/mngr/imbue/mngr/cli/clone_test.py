"""Unit tests for the clone CLI command."""

import pluggy
from click.testing import CliRunner

from imbue.mngr.cli.clone import clone
from imbue.mngr.main import cli


def test_clone_command_exists() -> None:
    """The 'clone' command should be registered on the CLI group."""
    assert "clone" in cli.commands


def test_clone_is_not_create() -> None:
    """Clone should be a distinct command object from create."""
    assert cli.commands["clone"] is not cli.commands["create"]


def test_clone_requires_source_agent(
    cli_runner: CliRunner,
    plugin_manager: pluggy.PluginManager,
) -> None:
    """Clone should error when no arguments are provided."""
    result = cli_runner.invoke(
        clone,
        [],
        obj=plugin_manager,
        catch_exceptions=True,
    )

    assert result.exit_code != 0
    assert "SOURCE_AGENT" in result.output


def test_clone_rejects_from_agent_option(
    cli_runner: CliRunner,
    plugin_manager: pluggy.PluginManager,
) -> None:
    """Clone should reject --from-agent in remaining args."""
    result = cli_runner.invoke(
        clone,
        ["source-agent", "--from-agent", "other-agent"],
        obj=plugin_manager,
        catch_exceptions=True,
    )

    assert result.exit_code != 0
    assert "--from-agent" in result.output


def test_clone_rejects_source_agent_option(
    cli_runner: CliRunner,
    plugin_manager: pluggy.PluginManager,
) -> None:
    """Clone should reject --source-agent in remaining args."""
    result = cli_runner.invoke(
        clone,
        ["source-agent", "--source-agent", "other-agent"],
        obj=plugin_manager,
        catch_exceptions=True,
    )

    assert result.exit_code != 0
    assert "--source-agent" in result.output


def test_clone_rejects_from_agent_equals_form(
    cli_runner: CliRunner,
    plugin_manager: pluggy.PluginManager,
) -> None:
    """Clone should reject --from-agent=value form in remaining args."""
    result = cli_runner.invoke(
        clone,
        ["source-agent", "--from-agent=other-agent"],
        obj=plugin_manager,
        catch_exceptions=True,
    )

    assert result.exit_code != 0
    assert "--from-agent" in result.output
