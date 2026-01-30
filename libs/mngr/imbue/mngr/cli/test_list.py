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


def test_list_command_with_host_provider_filter(
    cli_runner: CliRunner,
    temp_work_dir: Path,
    mngr_test_prefix: str,
    plugin_manager: pluggy.PluginManager,
) -> None:
    """Test list command with host.provider CEL filter.

    This test verifies that the standard CEL dot notation 'host.provider' works correctly.
    Nested dictionaries are automatically converted to CEL-compatible objects via json_to_cel().
    """
    agent_name = f"test-list-host-provider-{int(time.time())}"
    session_name = f"{mngr_test_prefix}{agent_name}"

    with tmux_session_cleanup(session_name):
        # Create an agent (will be on local provider)
        create_result = cli_runner.invoke(
            create,
            [
                "--name",
                agent_name,
                "--agent-cmd",
                "sleep 403183",
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

        # List with host.provider filter - should find the agent
        result = cli_runner.invoke(
            list_command,
            ["--include", 'host.provider == "local"'],
            obj=plugin_manager,
            catch_exceptions=False,
        )

        assert result.exit_code == 0
        assert agent_name in result.output

        # List with non-matching host.provider filter - should NOT find the agent
        result_no_match = cli_runner.invoke(
            list_command,
            ["--include", 'host.provider == "docker"'],
            obj=plugin_manager,
            catch_exceptions=False,
        )

        assert result_no_match.exit_code == 0
        assert agent_name not in result_no_match.output


def test_list_command_with_host_name_filter(
    cli_runner: CliRunner,
    temp_work_dir: Path,
    mngr_test_prefix: str,
    plugin_manager: pluggy.PluginManager,
) -> None:
    """Test list command with host.name CEL filter.

    Verifies that the standard CEL dot notation 'host.name' works in CEL filters.
    """
    agent_name = f"test-list-host-name-{int(time.time())}"
    session_name = f"{mngr_test_prefix}{agent_name}"

    with tmux_session_cleanup(session_name):
        # Create an agent
        create_result = cli_runner.invoke(
            create,
            [
                "--name",
                agent_name,
                "--agent-cmd",
                "sleep 403184",
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

        # List with host.name filter - local host is named "@local"
        result = cli_runner.invoke(
            list_command,
            ["--include", 'host.name == "@local"'],
            obj=plugin_manager,
            catch_exceptions=False,
        )

        assert result.exit_code == 0
        assert agent_name in result.output


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


def test_list_command_with_basic_fields(
    cli_runner: CliRunner,
    temp_work_dir: Path,
    mngr_test_prefix: str,
    plugin_manager: pluggy.PluginManager,
) -> None:
    """Test list command with basic field selection."""
    agent_name = f"test-list-fields-basic-{int(time.time())}"
    session_name = f"{mngr_test_prefix}{agent_name}"

    with tmux_session_cleanup(session_name):
        # Create an agent
        create_result = cli_runner.invoke(
            create,
            [
                "--name",
                agent_name,
                "--agent-cmd",
                "sleep 302171",
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

        # List with specific fields
        result = cli_runner.invoke(
            list_command,
            ["--fields", "id,name"],
            obj=plugin_manager,
            catch_exceptions=False,
        )

        assert result.exit_code == 0
        assert "ID" in result.output
        assert "NAME" in result.output
        assert agent_name in result.output
        # Should not show default fields like STATE or STATUS
        assert "STATE" not in result.output
        assert "STATUS" not in result.output


def test_list_command_with_nested_fields(
    cli_runner: CliRunner,
    temp_work_dir: Path,
    mngr_test_prefix: str,
    plugin_manager: pluggy.PluginManager,
) -> None:
    """Test list command with nested field selection."""
    agent_name = f"test-list-fields-nested-{int(time.time())}"
    session_name = f"{mngr_test_prefix}{agent_name}"

    with tmux_session_cleanup(session_name):
        # Create an agent
        create_result = cli_runner.invoke(
            create,
            [
                "--name",
                agent_name,
                "--agent-cmd",
                "sleep 201060",
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

        # List with nested fields
        result = cli_runner.invoke(
            list_command,
            ["--fields", "name,host.name,host.provider_name"],
            obj=plugin_manager,
            catch_exceptions=False,
        )

        assert result.exit_code == 0
        assert "NAME" in result.output
        assert "HOST_NAME" in result.output
        assert "HOST_PROVIDER_NAME" in result.output
        assert agent_name in result.output
        assert "@local" in result.output
        assert "local" in result.output


def test_list_command_with_field_aliases(
    cli_runner: CliRunner,
    temp_work_dir: Path,
    mngr_test_prefix: str,
    plugin_manager: pluggy.PluginManager,
) -> None:
    """Test list command with field aliases."""
    agent_name = f"test-list-fields-aliases-{int(time.time())}"
    session_name = f"{mngr_test_prefix}{agent_name}"

    with tmux_session_cleanup(session_name):
        # Create an agent
        create_result = cli_runner.invoke(
            create,
            [
                "--name",
                agent_name,
                "--agent-cmd",
                "sleep 109949",
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

        # List with field aliases
        result = cli_runner.invoke(
            list_command,
            ["--fields", "name,state,host,provider"],
            obj=plugin_manager,
            catch_exceptions=False,
        )

        assert result.exit_code == 0
        assert "NAME" in result.output
        assert "STATE" in result.output
        assert "HOST" in result.output
        assert "PROVIDER" in result.output
        assert agent_name in result.output
        # State should show "running" or "stopped" in lowercase
        assert "running" in result.output or "stopped" in result.output


def test_list_command_with_invalid_fields(
    cli_runner: CliRunner,
    temp_work_dir: Path,
    mngr_test_prefix: str,
    plugin_manager: pluggy.PluginManager,
) -> None:
    """Test list command with invalid field shows empty column."""
    agent_name = f"test-list-fields-invalid-{int(time.time())}"
    session_name = f"{mngr_test_prefix}{agent_name}"

    with tmux_session_cleanup(session_name):
        # Create an agent
        create_result = cli_runner.invoke(
            create,
            [
                "--name",
                agent_name,
                "--agent-cmd",
                "sleep 008838",
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

        # List with invalid field
        result = cli_runner.invoke(
            list_command,
            ["--fields", "name,invalid_field"],
            obj=plugin_manager,
            catch_exceptions=False,
        )

        # Should not fail, just show empty column
        assert result.exit_code == 0
        assert "NAME" in result.output
        assert "INVALID_FIELD" in result.output
        assert agent_name in result.output


def test_list_command_with_running_filter_alias(
    cli_runner: CliRunner,
    temp_work_dir: Path,
    mngr_test_prefix: str,
    plugin_manager: pluggy.PluginManager,
) -> None:
    """Test list command with --running filter alias."""
    agent_name = f"test-list-running-{int(time.time())}"
    session_name = f"{mngr_test_prefix}{agent_name}"

    with tmux_session_cleanup(session_name):
        # Create a running agent
        create_result = cli_runner.invoke(
            create,
            [
                "--name",
                agent_name,
                "--agent-cmd",
                "sleep 907727",
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

        # List with --running should show the agent
        result = cli_runner.invoke(
            list_command,
            ["--running"],
            obj=plugin_manager,
            catch_exceptions=False,
        )

        assert result.exit_code == 0
        assert agent_name in result.output


def test_list_command_with_stopped_filter_alias(
    cli_runner: CliRunner,
    plugin_manager: pluggy.PluginManager,
) -> None:
    """Test list command with --stopped filter alias (no agents to find)."""
    # Without any stopped agents, this should return no agents
    result = cli_runner.invoke(
        list_command,
        ["--stopped"],
        obj=plugin_manager,
        catch_exceptions=False,
    )

    assert result.exit_code == 0
    # Should indicate no agents found or empty output
    assert "No agents found" in result.output or "stopped" not in result.output.lower()


def test_list_command_with_local_filter_alias(
    cli_runner: CliRunner,
    temp_work_dir: Path,
    mngr_test_prefix: str,
    plugin_manager: pluggy.PluginManager,
) -> None:
    """Test list command with --local filter alias."""
    agent_name = f"test-list-local-{int(time.time())}"
    session_name = f"{mngr_test_prefix}{agent_name}"

    with tmux_session_cleanup(session_name):
        # Create a local agent
        create_result = cli_runner.invoke(
            create,
            [
                "--name",
                agent_name,
                "--agent-cmd",
                "sleep 806616",
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

        # List with --local should show the agent
        result = cli_runner.invoke(
            list_command,
            ["--local"],
            obj=plugin_manager,
            catch_exceptions=False,
        )

        assert result.exit_code == 0
        assert agent_name in result.output


def test_list_command_with_remote_filter_alias(
    cli_runner: CliRunner,
    temp_work_dir: Path,
    mngr_test_prefix: str,
    plugin_manager: pluggy.PluginManager,
) -> None:
    """Test list command with --remote filter alias (excludes local agents)."""
    agent_name = f"test-list-remote-{int(time.time())}"
    session_name = f"{mngr_test_prefix}{agent_name}"

    with tmux_session_cleanup(session_name):
        # Create a local agent
        create_result = cli_runner.invoke(
            create,
            [
                "--name",
                agent_name,
                "--agent-cmd",
                "sleep 705505",
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

        # List with --remote should NOT show the local agent
        result = cli_runner.invoke(
            list_command,
            ["--remote"],
            obj=plugin_manager,
            catch_exceptions=False,
        )

        assert result.exit_code == 0
        assert agent_name not in result.output
