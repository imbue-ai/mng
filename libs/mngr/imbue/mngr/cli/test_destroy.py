"""Tests for the destroy CLI command."""

import time
from contextlib import ExitStack
from pathlib import Path

import pluggy
import pytest
from click.testing import CliRunner

from imbue.mngr.cli.create import create
from imbue.mngr.cli.destroy import destroy
from imbue.mngr.cli.destroy import get_agent_name_from_session
from imbue.mngr.utils.polling import wait_for
from imbue.mngr.utils.testing import tmux_session_cleanup
from imbue.mngr.utils.testing import tmux_session_exists


def test_destroy_single_agent(
    cli_runner: CliRunner,
    temp_work_dir: Path,
    mngr_test_prefix: str,
    plugin_manager: pluggy.PluginManager,
) -> None:
    """Test destroying a single agent."""
    agent_name = f"test-destroy-single-{int(time.time())}"
    session_name = f"{mngr_test_prefix}{agent_name}"

    with tmux_session_cleanup(session_name):
        create_result = cli_runner.invoke(
            create,
            [
                "--name",
                agent_name,
                "--agent-cmd",
                "sleep 435782",
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

        assert create_result.exit_code == 0, f"Create failed: {create_result.output}"
        assert tmux_session_exists(session_name), f"Expected tmux session {session_name} to exist"

        destroy_result = cli_runner.invoke(
            destroy,
            [agent_name, "--force"],
            obj=plugin_manager,
            catch_exceptions=False,
        )

        assert destroy_result.exit_code == 0, f"Destroy failed: {destroy_result.output}"
        assert "Destroyed agent:" in destroy_result.output

        wait_for(
            lambda: not tmux_session_exists(session_name),
            error_message=f"Expected tmux session {session_name} to be destroyed",
        )


def test_destroy_single_agent_via_session(
    cli_runner: CliRunner,
    temp_work_dir: Path,
    mngr_test_prefix: str,
    plugin_manager: pluggy.PluginManager,
) -> None:
    """Test destroying a single agent using the --session option."""
    agent_name = f"test-destroy-session-{int(time.time())}"
    session_name = f"{mngr_test_prefix}{agent_name}"

    with tmux_session_cleanup(session_name):
        create_result = cli_runner.invoke(
            create,
            [
                "--name",
                agent_name,
                "--agent-cmd",
                "sleep 435783",
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

        assert create_result.exit_code == 0, f"Create failed: {create_result.output}"
        assert tmux_session_exists(session_name), f"Expected tmux session {session_name} to exist"

        destroy_result = cli_runner.invoke(
            destroy,
            ["--session", session_name, "--force"],
            obj=plugin_manager,
            catch_exceptions=False,
        )

        assert destroy_result.exit_code == 0, f"Destroy failed: {destroy_result.output}"
        assert "Destroyed agent:" in destroy_result.output

        wait_for(
            lambda: not tmux_session_exists(session_name),
            error_message=f"Expected tmux session {session_name} to be destroyed",
        )


def test_destroy_with_confirmation(
    cli_runner: CliRunner,
    temp_work_dir: Path,
    mngr_test_prefix: str,
    plugin_manager: pluggy.PluginManager,
) -> None:
    """Test destroying an agent with confirmation prompt."""
    agent_name = f"test-destroy-confirm-{int(time.time())}"
    session_name = f"{mngr_test_prefix}{agent_name}"

    with tmux_session_cleanup(session_name):
        create_result = cli_runner.invoke(
            create,
            [
                "--name",
                agent_name,
                "--agent-cmd",
                "sleep 679415",
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
        assert tmux_session_exists(session_name)

        destroy_result = cli_runner.invoke(
            destroy,
            [agent_name],
            input="y\n",
            obj=plugin_manager,
            catch_exceptions=False,
        )

        assert destroy_result.exit_code == 0
        assert "Are you sure you want to continue?" in destroy_result.output

        wait_for(
            lambda: not tmux_session_exists(session_name),
            error_message=f"Expected tmux session {session_name} to be destroyed",
        )


def test_destroy_nonexistent_agent(
    cli_runner: CliRunner,
    plugin_manager: pluggy.PluginManager,
) -> None:
    """Test destroying a non-existent agent."""
    result = cli_runner.invoke(
        destroy,
        ["nonexistent-agent"],
        obj=plugin_manager,
        catch_exceptions=True,
    )

    assert result.exit_code != 0


def test_destroy_prints_errors_if_any_identifier_not_found(
    cli_runner: CliRunner,
    temp_work_dir: Path,
    mngr_test_prefix: str,
    plugin_manager: pluggy.PluginManager,
) -> None:
    """Test that destroy fails if any specified identifier doesn't match an agent.

    When multiple agents are specified and some don't exist, the command should:
    1. Fail without destroying any agents
    2. Include all missing identifiers in the error message
    """
    agent_name = f"test-destroy-partial-{int(time.time())}"
    session_name = f"{mngr_test_prefix}{agent_name}"
    nonexistent_name1 = "nonexistent-agent-897231"
    nonexistent_name2 = "nonexistent-agent-643892"

    with tmux_session_cleanup(session_name):
        # Create one real agent
        create_result = cli_runner.invoke(
            create,
            [
                "--name",
                agent_name,
                "--agent-cmd",
                "sleep 782341",
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
        assert tmux_session_exists(session_name)

        # Try to destroy the real agent plus two non-existent ones
        destroy_result = cli_runner.invoke(
            destroy,
            [agent_name, nonexistent_name1, nonexistent_name2, "--force"],
            obj=plugin_manager,
            catch_exceptions=True,
        )

        # Command does not fail (because of the "--force" flag), but reports errors
        assert destroy_result.exit_code == 0

        # Error message should include both missing agent names
        error_message = destroy_result.output
        assert nonexistent_name1 in error_message
        assert nonexistent_name2 in error_message

        # The existing agent should NOT have been destroyed
        assert tmux_session_exists(session_name), "Existing agent should not be destroyed when some identifiers fail"


def test_destroy_dry_run(
    cli_runner: CliRunner,
    temp_work_dir: Path,
    mngr_test_prefix: str,
    plugin_manager: pluggy.PluginManager,
) -> None:
    """Test dry-run mode for destroy command."""
    agent_name = f"test-destroy-dryrun-{int(time.time())}"
    session_name = f"{mngr_test_prefix}{agent_name}"

    with tmux_session_cleanup(session_name):
        create_result = cli_runner.invoke(
            create,
            [
                "--name",
                agent_name,
                "--agent-cmd",
                "sleep 541286",
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
        assert tmux_session_exists(session_name)

        destroy_result = cli_runner.invoke(
            destroy,
            [agent_name, "--dry-run"],
            obj=plugin_manager,
            catch_exceptions=False,
        )

        assert destroy_result.exit_code == 0
        assert "Would destroy:" in destroy_result.output

        wait_for(
            lambda: tmux_session_exists(session_name),
            error_message="Agent session should still exist after dry-run",
        )


def test_destroy_multiple_agents(
    cli_runner: CliRunner,
    temp_work_dir: Path,
    mngr_test_prefix: str,
    plugin_manager: pluggy.PluginManager,
) -> None:
    """Test destroying multiple agents at once."""
    timestamp = int(time.time())
    agent_name1 = f"test-destroy-multi1-{timestamp}"
    agent_name2 = f"test-destroy-multi2-{timestamp}"
    session_name1 = f"{mngr_test_prefix}{agent_name1}"
    session_name2 = f"{mngr_test_prefix}{agent_name2}"

    with ExitStack() as stack:
        stack.enter_context(tmux_session_cleanup(session_name1))
        stack.enter_context(tmux_session_cleanup(session_name2))

        for agent_name in [agent_name1, agent_name2]:
            result = cli_runner.invoke(
                create,
                [
                    "--name",
                    agent_name,
                    "--agent-cmd",
                    "sleep 892736",
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
            assert result.exit_code == 0

        wait_for(
            lambda: tmux_session_exists(session_name1),
            error_message=f"Expected tmux session {session_name1} to exist",
        )
        wait_for(
            lambda: tmux_session_exists(session_name2),
            error_message=f"Expected tmux session {session_name2} to exist",
        )

        destroy_result = cli_runner.invoke(
            destroy,
            [agent_name1, agent_name2, "--force"],
            obj=plugin_manager,
            catch_exceptions=False,
        )

        assert destroy_result.exit_code == 0

        wait_for(
            lambda: not tmux_session_exists(session_name1) and not tmux_session_exists(session_name2),
            error_message="Expected both tmux sessions to be destroyed",
        )


# =============================================================================
# Tests for get_agent_name_from_session()
# =============================================================================


def test_get_agent_name_from_session_empty_session() -> None:
    """Test get_agent_name_from_session returns None for empty session name."""
    result = get_agent_name_from_session("", "mngr-")
    assert result is None


def test_get_agent_name_from_session_wrong_prefix() -> None:
    """Test get_agent_name_from_session returns None when session doesn't match prefix."""
    result = get_agent_name_from_session("other-session", "mngr-")
    assert result is None


def test_get_agent_name_from_session_success() -> None:
    """Test get_agent_name_from_session extracts agent name correctly."""
    result = get_agent_name_from_session("mngr-my-agent", "mngr-")
    assert result == "my-agent"


def test_get_agent_name_from_session_custom_prefix() -> None:
    """Test get_agent_name_from_session works with custom prefix."""
    result = get_agent_name_from_session("custom-prefix-agent-name", "custom-prefix-")
    assert result == "agent-name"


def test_get_agent_name_from_session_only_prefix() -> None:
    """Test get_agent_name_from_session returns None when session is just the prefix."""
    result = get_agent_name_from_session("mngr-", "mngr-")
    assert result is None


# =============================================================================
# Tests for --session CLI flag
# =============================================================================


def test_session_cannot_combine_with_agent_names(
    cli_runner: CliRunner,
    plugin_manager: pluggy.PluginManager,
) -> None:
    """Test that --session cannot be combined with agent names."""
    result = cli_runner.invoke(
        destroy,
        ["my-agent", "--session", "mngr-some-agent", "--force"],
        obj=plugin_manager,
        catch_exceptions=True,
    )

    assert result.exit_code != 0
    assert "Cannot specify --session with agent names or --all" in result.output


def test_session_cannot_combine_with_all(
    cli_runner: CliRunner,
    plugin_manager: pluggy.PluginManager,
) -> None:
    """Test that --session cannot be combined with --all."""
    result = cli_runner.invoke(
        destroy,
        ["--session", "mngr-some-agent", "--all", "--force"],
        obj=plugin_manager,
        catch_exceptions=True,
    )

    assert result.exit_code != 0
    assert "Cannot specify --session with agent names or --all" in result.output


def test_session_fails_with_invalid_prefix(
    cli_runner: CliRunner,
    plugin_manager: pluggy.PluginManager,
) -> None:
    """Test that --session fails when session doesn't match expected prefix format."""
    result = cli_runner.invoke(
        destroy,
        ["--session", "other-session-name", "--force"],
        obj=plugin_manager,
        catch_exceptions=True,
    )

    assert result.exit_code != 0
    assert "does not match the expected format" in result.output


@pytest.mark.parametrize(
    "session_name,prefix,expected_agent",
    [
        ("mngr-test-agent", "mngr-", "test-agent"),
        ("mngr-another", "mngr-", "another"),
        ("prefix-foo", "prefix-", "foo"),
    ],
)
def test_get_agent_name_from_session_various_inputs(session_name: str, prefix: str, expected_agent: str) -> None:
    """Test get_agent_name_from_session with various valid inputs."""
    result = get_agent_name_from_session(session_name, prefix)
    assert result == expected_agent
