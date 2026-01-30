"""Integration tests for the list CLI command."""

import time
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path
from typing import NamedTuple

import pluggy
import pytest
from click.testing import CliRunner

from imbue.mngr.cli.create import create
from imbue.mngr.cli.list import list_command
from imbue.mngr.utils.testing import cleanup_tmux_session


class SharedAgentInfo(NamedTuple):
    """Information about a shared test agent."""

    name: str
    session_name: str


@contextmanager
def _create_shared_agent(
    cli_runner: CliRunner,
    temp_work_dir: Path,
    mngr_test_prefix: str,
    plugin_manager: pluggy.PluginManager,
) -> Generator[SharedAgentInfo, None, None]:
    """Create a shared agent for multiple list tests.

    This context manager creates an agent and cleans it up afterward.
    Multiple tests can use the same agent to avoid the overhead of
    creating a new agent for each test.
    """
    agent_name = f"test-list-shared-{int(time.time())}"
    session_name = f"{mngr_test_prefix}{agent_name}"

    try:
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
        assert create_result.exit_code == 0, f"Failed to create shared agent: {create_result.output}"
        yield SharedAgentInfo(name=agent_name, session_name=session_name)
    finally:
        cleanup_tmux_session(session_name)


@pytest.fixture
def shared_agent(
    cli_runner: CliRunner,
    temp_work_dir: Path,
    mngr_test_prefix: str,
    plugin_manager: pluggy.PluginManager,
) -> Generator[SharedAgentInfo, None, None]:
    """Fixture that provides a shared agent for list tests."""
    with _create_shared_agent(cli_runner, temp_work_dir, mngr_test_prefix, plugin_manager) as agent:
        yield agent


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


def test_list_command_formats_and_filters(
    cli_runner: CliRunner,
    plugin_manager: pluggy.PluginManager,
    shared_agent: SharedAgentInfo,
) -> None:
    """Test list command with various formats and filters.

    This consolidated test verifies:
    - Default table format shows agent
    - JSON format shows agent data
    - JSONL format streams agent data
    - Include filter matches agent by name
    - Exclude filter excludes agent by name
    - Host provider filter (CEL dot notation) works
    - Host name filter (CEL dot notation) works
    """
    # Test default format
    result = cli_runner.invoke(
        list_command,
        [],
        obj=plugin_manager,
        catch_exceptions=False,
    )
    assert result.exit_code == 0
    assert shared_agent.name in result.output

    # Test JSON format
    result = cli_runner.invoke(
        list_command,
        ["--format", "json"],
        obj=plugin_manager,
        catch_exceptions=False,
    )
    assert result.exit_code == 0
    assert '"agents":' in result.output
    assert shared_agent.name in result.output

    # Test JSONL format
    result = cli_runner.invoke(
        list_command,
        ["--format", "jsonl"],
        obj=plugin_manager,
        catch_exceptions=False,
    )
    assert result.exit_code == 0
    assert shared_agent.name in result.output

    # Test include filter - should find agent
    result = cli_runner.invoke(
        list_command,
        ["--include", f'name == "{shared_agent.name}"'],
        obj=plugin_manager,
        catch_exceptions=False,
    )
    assert result.exit_code == 0
    assert shared_agent.name in result.output

    # Test exclude filter - should NOT find agent
    result = cli_runner.invoke(
        list_command,
        ["--exclude", f'name == "{shared_agent.name}"'],
        obj=plugin_manager,
        catch_exceptions=False,
    )
    assert result.exit_code == 0
    assert shared_agent.name not in result.output

    # Test host.provider filter (CEL dot notation) - should find agent
    result = cli_runner.invoke(
        list_command,
        ["--include", 'host.provider == "local"'],
        obj=plugin_manager,
        catch_exceptions=False,
    )
    assert result.exit_code == 0
    assert shared_agent.name in result.output

    # Test non-matching host.provider filter - should NOT find agent
    result = cli_runner.invoke(
        list_command,
        ["--include", 'host.provider == "docker"'],
        obj=plugin_manager,
        catch_exceptions=False,
    )
    assert result.exit_code == 0
    assert shared_agent.name not in result.output

    # Test host.name filter (CEL dot notation) - local host is "@local"
    result = cli_runner.invoke(
        list_command,
        ["--include", 'host.name == "@local"'],
        obj=plugin_manager,
        catch_exceptions=False,
    )
    assert result.exit_code == 0
    assert shared_agent.name in result.output


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


def test_list_command_field_selection(
    cli_runner: CliRunner,
    plugin_manager: pluggy.PluginManager,
    shared_agent: SharedAgentInfo,
) -> None:
    """Test list command field selection options.

    This consolidated test verifies:
    - Basic field selection (id, name)
    - Nested field selection (host.name, host.provider_name)
    - Field aliases (state, host, provider)
    - Invalid field handling (shows empty column)
    """
    # Test basic field selection
    result = cli_runner.invoke(
        list_command,
        ["--fields", "id,name"],
        obj=plugin_manager,
        catch_exceptions=False,
    )
    assert result.exit_code == 0
    assert "ID" in result.output
    assert "NAME" in result.output
    assert shared_agent.name in result.output
    # Should not show default fields like STATE or STATUS
    assert "STATE" not in result.output
    assert "STATUS" not in result.output

    # Test nested field selection
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
    assert shared_agent.name in result.output
    assert "@local" in result.output
    assert "local" in result.output

    # Test field aliases
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
    assert shared_agent.name in result.output
    # State should show "running" or "stopped" in lowercase
    assert "running" in result.output or "stopped" in result.output

    # Test invalid field handling
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
    assert shared_agent.name in result.output
