"""Unit tests for the migrate CLI command."""

import pluggy
from click.testing import CliRunner

from imbue.mngr.cli.migrate import _extract_target_provider_name
from imbue.mngr.cli.migrate import _has_host_flag
from imbue.mngr.cli.migrate import _user_specified_quiet
from imbue.mngr.cli.migrate import migrate
from imbue.mngr.main import cli
from imbue.mngr.primitives import ProviderInstanceName


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
        ["nonexistent-agent-849271", "--in", "docker"],
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


# --- _extract_target_provider_name tests ---


def test_extract_target_provider_from_in_flag() -> None:
    """--in <provider> should be extracted."""
    result = _extract_target_provider_name(
        ["--in", "modal", "--agent-cmd", "sleep 1"],
        ["mngr", "migrate", "my-agent", "--in", "modal", "--agent-cmd", "sleep 1"],
    )
    assert result == ProviderInstanceName("modal")


def test_extract_target_provider_from_in_equals() -> None:
    """--in=<provider> should be extracted."""
    result = _extract_target_provider_name(
        ["--in=docker"],
        ["mngr", "migrate", "my-agent", "--in=docker"],
    )
    assert result == ProviderInstanceName("docker")


def test_extract_target_provider_from_new_host_flag() -> None:
    """--new-host <provider> should be extracted."""
    result = _extract_target_provider_name(
        ["--new-host", "modal"],
        ["mngr", "migrate", "my-agent", "--new-host", "modal"],
    )
    assert result == ProviderInstanceName("modal")


def test_extract_target_provider_returns_none_when_absent() -> None:
    """Returns None when no --in or --new-host is specified."""
    result = _extract_target_provider_name(
        ["--agent-cmd", "sleep 1"],
        ["mngr", "migrate", "my-agent", "--agent-cmd", "sleep 1"],
    )
    assert result is None


def test_extract_target_provider_ignores_in_after_dd() -> None:
    """--in after -- should be ignored (those are agent args, not create options)."""
    result = _extract_target_provider_name(
        ["--agent-cmd", "sleep 1", "--in", "modal"],
        ["mngr", "migrate", "my-agent", "--agent-cmd", "sleep 1", "--", "--in", "modal"],
    )
    assert result is None


# --- _has_host_flag tests ---


def test_has_host_flag_detects_host() -> None:
    assert (
        _has_host_flag(
            ["--host", "my-host"],
            ["mngr", "migrate", "my-agent", "--host", "my-host"],
        )
        is True
    )


def test_has_host_flag_detects_target_host() -> None:
    assert (
        _has_host_flag(
            ["--target-host", "my-host"],
            ["mngr", "migrate", "my-agent", "--target-host", "my-host"],
        )
        is True
    )


def test_has_host_flag_detects_host_equals() -> None:
    assert (
        _has_host_flag(
            ["--host=my-host"],
            ["mngr", "migrate", "my-agent", "--host=my-host"],
        )
        is True
    )


def test_has_host_flag_returns_false_when_absent() -> None:
    assert (
        _has_host_flag(
            ["--in", "modal"],
            ["mngr", "migrate", "my-agent", "--in", "modal"],
        )
        is False
    )


def test_has_host_flag_ignores_host_after_dd() -> None:
    """--host after -- should be ignored."""
    assert (
        _has_host_flag(
            ["--agent-cmd", "sleep 1", "--host", "my-host"],
            ["mngr", "migrate", "my-agent", "--agent-cmd", "sleep 1", "--", "--host", "my-host"],
        )
        is False
    )
