"""Integration tests for the list CLI command."""

import time
from pathlib import Path

import pluggy
from click.testing import CliRunner

from imbue.mngr.cli.create import create
from imbue.mngr.cli.list import list_command
from imbue.mngr.utils.testing import tmux_session_cleanup


def test_list_command_no_agents(
    cli_runner: CliRunner,
    plugin_manager: pluggy.PluginManager,
) -> None:
    """Test list command when no agents exist."""
    result = cli_runner.invoke(
        list_command,
        [],
        obj=plugin_manager,
        catch_exceptions=False,
    )

    assert result.exit_code == 0
    assert "No agents found" in result.output


def test_list_command_json_format_no_agents(
    cli_runner: CliRunner,
    plugin_manager: pluggy.PluginManager,
) -> None:
    """Test list command with JSON format when no agents exist."""
    result = cli_runner.invoke(
        list_command,
        ["--format", "json"],
        obj=plugin_manager,
        catch_exceptions=False,
    )

    assert result.exit_code == 0
    assert '"agents": []' in result.output


def test_list_command_with_agent(
    cli_runner: CliRunner,
    temp_work_dir: Path,
    mngr_test_prefix: str,
    plugin_manager: pluggy.PluginManager,
) -> None:
    """Test list command shows created agent."""
    agent_name = f"test-list-cli-{int(time.time())}"
    session_name = f"{mngr_test_prefix}{agent_name}"

    with tmux_session_cleanup(session_name):
        # Create an agent first
        create_result = cli_runner.invoke(
            create,
            [
                "--name",
                agent_name,
                "--agent-cmd",
                "sleep 837291",
                "--source",
                str(temp_work_dir),
                "--no-connect",
                "--await-ready",
                "--no-copy-work-dir",
                "--no-ensure-clean",
            ],
            obj=plugin_manager,
            catch_exceptions=False,
        )
        assert create_result.exit_code == 0

        # List agents
        result = cli_runner.invoke(
            list_command,
            [],
            obj=plugin_manager,
            catch_exceptions=False,
        )

        assert result.exit_code == 0
        assert agent_name in result.output


def test_list_command_json_format_with_agent(
    cli_runner: CliRunner,
    temp_work_dir: Path,
    mngr_test_prefix: str,
    plugin_manager: pluggy.PluginManager,
) -> None:
    """Test list command with JSON format shows agent data."""
    agent_name = f"test-list-json-{int(time.time())}"
    session_name = f"{mngr_test_prefix}{agent_name}"

    with tmux_session_cleanup(session_name):
        # Create an agent
        create_result = cli_runner.invoke(
            create,
            [
                "--name",
                agent_name,
                "--agent-cmd",
                "sleep 726483",
                "--source",
                str(temp_work_dir),
                "--no-connect",
                "--await-ready",
                "--no-copy-work-dir",
                "--no-ensure-clean",
            ],
            obj=plugin_manager,
            catch_exceptions=False,
        )
        assert create_result.exit_code == 0

        # List agents in JSON format
        result = cli_runner.invoke(
            list_command,
            ["--format", "json"],
            obj=plugin_manager,
            catch_exceptions=False,
        )

        assert result.exit_code == 0
        assert '"agents":' in result.output
        assert agent_name in result.output


def test_list_command_jsonl_format_with_agent(
    cli_runner: CliRunner,
    temp_work_dir: Path,
    mngr_test_prefix: str,
    plugin_manager: pluggy.PluginManager,
) -> None:
    """Test list command with JSONL format streams agent data."""
    agent_name = f"test-list-jsonl-{int(time.time())}"
    session_name = f"{mngr_test_prefix}{agent_name}"

    with tmux_session_cleanup(session_name):
        # Create an agent
        create_result = cli_runner.invoke(
            create,
            [
                "--name",
                agent_name,
                "--agent-cmd",
                "sleep 615283",
                "--source",
                str(temp_work_dir),
                "--no-connect",
                "--await-ready",
                "--no-copy-work-dir",
                "--no-ensure-clean",
            ],
            obj=plugin_manager,
            catch_exceptions=False,
        )
        assert create_result.exit_code == 0

        # List agents in JSONL format
        result = cli_runner.invoke(
            list_command,
            ["--format", "jsonl"],
            obj=plugin_manager,
            catch_exceptions=False,
        )

        assert result.exit_code == 0
        # JSONL format should have agent data as a single line
        assert agent_name in result.output


def test_list_command_with_include_filter(
    cli_runner: CliRunner,
    temp_work_dir: Path,
    mngr_test_prefix: str,
    plugin_manager: pluggy.PluginManager,
) -> None:
    """Test list command with include filter."""
    agent_name = f"test-list-filter-{int(time.time())}"
    session_name = f"{mngr_test_prefix}{agent_name}"

    with tmux_session_cleanup(session_name):
        # Create an agent
        create_result = cli_runner.invoke(
            create,
            [
                "--name",
                agent_name,
                "--agent-cmd",
                "sleep 504293",
                "--source",
                str(temp_work_dir),
                "--no-connect",
                "--await-ready",
                "--no-copy-work-dir",
                "--no-ensure-clean",
            ],
            obj=plugin_manager,
            catch_exceptions=False,
        )
        assert create_result.exit_code == 0

        # List with matching filter
        result = cli_runner.invoke(
            list_command,
            ["--include", f'name == "{agent_name}"'],
            obj=plugin_manager,
            catch_exceptions=False,
        )

        assert result.exit_code == 0
        assert agent_name in result.output


def test_list_command_with_exclude_filter(
    cli_runner: CliRunner,
    temp_work_dir: Path,
    mngr_test_prefix: str,
    plugin_manager: pluggy.PluginManager,
) -> None:
    """Test list command with exclude filter."""
    agent_name = f"test-list-exclude-{int(time.time())}"
    session_name = f"{mngr_test_prefix}{agent_name}"

    with tmux_session_cleanup(session_name):
        # Create an agent
        create_result = cli_runner.invoke(
            create,
            [
                "--name",
                agent_name,
                "--agent-cmd",
                "sleep 403182",
                "--source",
                str(temp_work_dir),
                "--no-connect",
                "--await-ready",
                "--no-copy-work-dir",
                "--no-ensure-clean",
            ],
            obj=plugin_manager,
            catch_exceptions=False,
        )
        assert create_result.exit_code == 0

        # List with exclusion filter
        result = cli_runner.invoke(
            list_command,
            ["--exclude", f'name == "{agent_name}"'],
            obj=plugin_manager,
            catch_exceptions=False,
        )

        assert result.exit_code == 0
        assert agent_name not in result.output


def test_list_command_on_error_continue(
    cli_runner: CliRunner,
    plugin_manager: pluggy.PluginManager,
) -> None:
    """Test list command with --on-error continue."""
    result = cli_runner.invoke(
        list_command,
        ["--on-error", "continue"],
        obj=plugin_manager,
        catch_exceptions=False,
    )

    assert result.exit_code == 0


def test_list_command_on_error_abort(
    cli_runner: CliRunner,
    plugin_manager: pluggy.PluginManager,
) -> None:
    """Test list command with --on-error abort (default behavior)."""
    result = cli_runner.invoke(
        list_command,
        ["--on-error", "abort"],
        obj=plugin_manager,
        catch_exceptions=False,
    )

    assert result.exit_code == 0


def test_list_command_format_template_not_implemented(
    cli_runner: CliRunner,
    plugin_manager: pluggy.PluginManager,
) -> None:
    """Test that --format-template raises NotImplementedError."""
    result = cli_runner.invoke(
        list_command,
        ["--format-template", "{name}"],
        obj=plugin_manager,
    )

    assert result.exit_code != 0
    # The NotImplementedError should result in an error exit code
    # It may be caught and logged as an error or raised directly
    assert result.exception is not None or "Aborted" in result.output


def test_list_command_fields_not_implemented(
    cli_runner: CliRunner,
    plugin_manager: pluggy.PluginManager,
) -> None:
    """Test that --fields raises NotImplementedError."""
    result = cli_runner.invoke(
        list_command,
        ["--fields", "name,status"],
        obj=plugin_manager,
    )

    assert result.exit_code != 0


def test_list_command_watch_not_implemented(
    cli_runner: CliRunner,
    plugin_manager: pluggy.PluginManager,
) -> None:
    """Test that --watch raises NotImplementedError."""
    result = cli_runner.invoke(
        list_command,
        ["--watch", "5"],
        obj=plugin_manager,
    )

    assert result.exit_code != 0


def test_list_command_running_filter_not_implemented(
    cli_runner: CliRunner,
    plugin_manager: pluggy.PluginManager,
) -> None:
    """Test that --running raises NotImplementedError."""
    result = cli_runner.invoke(
        list_command,
        ["--running"],
        obj=plugin_manager,
    )

    assert result.exit_code != 0


def test_list_command_stopped_filter_not_implemented(
    cli_runner: CliRunner,
    plugin_manager: pluggy.PluginManager,
) -> None:
    """Test that --stopped raises NotImplementedError."""
    result = cli_runner.invoke(
        list_command,
        ["--stopped"],
        obj=plugin_manager,
    )

    assert result.exit_code != 0


def test_list_command_local_filter_not_implemented(
    cli_runner: CliRunner,
    plugin_manager: pluggy.PluginManager,
) -> None:
    """Test that --local raises NotImplementedError."""
    result = cli_runner.invoke(
        list_command,
        ["--local"],
        obj=plugin_manager,
    )

    assert result.exit_code != 0


def test_list_command_remote_filter_not_implemented(
    cli_runner: CliRunner,
    plugin_manager: pluggy.PluginManager,
) -> None:
    """Test that --remote raises NotImplementedError."""
    result = cli_runner.invoke(
        list_command,
        ["--remote"],
        obj=plugin_manager,
    )

    assert result.exit_code != 0


def test_list_command_sort_not_implemented(
    cli_runner: CliRunner,
    plugin_manager: pluggy.PluginManager,
) -> None:
    """Test that non-default --sort raises NotImplementedError."""
    result = cli_runner.invoke(
        list_command,
        ["--sort", "name"],
        obj=plugin_manager,
    )

    assert result.exit_code != 0


def test_list_command_limit_not_implemented(
    cli_runner: CliRunner,
    plugin_manager: pluggy.PluginManager,
) -> None:
    """Test that --limit raises NotImplementedError."""
    result = cli_runner.invoke(
        list_command,
        ["--limit", "10"],
        obj=plugin_manager,
    )

    assert result.exit_code != 0
