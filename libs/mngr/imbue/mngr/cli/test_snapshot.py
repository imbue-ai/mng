"""Integration tests for the snapshot CLI command."""

import time
from pathlib import Path

import pluggy
from click.testing import CliRunner

from imbue.mngr.cli.create import create
from imbue.mngr.cli.snapshot import snapshot
from imbue.mngr.utils.testing import tmux_session_cleanup

# =============================================================================
# Tests with real local agents
# =============================================================================


def test_snapshot_create_local_agent_rejects_unsupported_provider(
    cli_runner: CliRunner,
    temp_work_dir: Path,
    mngr_test_prefix: str,
    plugin_manager: pluggy.PluginManager,
) -> None:
    """Test that snapshot create fails for a local agent (unsupported provider)."""
    agent_name = f"test-snap-create-{int(time.time())}"
    session_name = f"{mngr_test_prefix}{agent_name}"

    with tmux_session_cleanup(session_name):
        cli_runner.invoke(
            create,
            [
                "--name",
                agent_name,
                "--agent-cmd",
                "sleep 748291",
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

        result = cli_runner.invoke(
            snapshot,
            ["create", agent_name],
            obj=plugin_manager,
            catch_exceptions=True,
        )

        assert result.exit_code != 0
        assert "does not support snapshots" in result.output


def test_snapshot_list_local_agent_rejects_unsupported_provider(
    cli_runner: CliRunner,
    temp_work_dir: Path,
    mngr_test_prefix: str,
    plugin_manager: pluggy.PluginManager,
) -> None:
    """Test that snapshot list fails for a local agent (unsupported provider)."""
    agent_name = f"test-snap-list-{int(time.time())}"
    session_name = f"{mngr_test_prefix}{agent_name}"

    with tmux_session_cleanup(session_name):
        cli_runner.invoke(
            create,
            [
                "--name",
                agent_name,
                "--agent-cmd",
                "sleep 748292",
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

        result = cli_runner.invoke(
            snapshot,
            ["list", agent_name],
            obj=plugin_manager,
            catch_exceptions=True,
        )

        assert result.exit_code != 0
        assert "does not support snapshots" in result.output


def test_snapshot_destroy_local_agent_rejects_unsupported_provider(
    cli_runner: CliRunner,
    temp_work_dir: Path,
    mngr_test_prefix: str,
    plugin_manager: pluggy.PluginManager,
) -> None:
    """Test that snapshot destroy fails for a local agent (unsupported provider)."""
    agent_name = f"test-snap-destroy-{int(time.time())}"
    session_name = f"{mngr_test_prefix}{agent_name}"

    with tmux_session_cleanup(session_name):
        cli_runner.invoke(
            create,
            [
                "--name",
                agent_name,
                "--agent-cmd",
                "sleep 748293",
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

        result = cli_runner.invoke(
            snapshot,
            ["destroy", agent_name, "--all-snapshots", "--force"],
            obj=plugin_manager,
            catch_exceptions=True,
        )

        assert result.exit_code != 0
        assert "does not support snapshots" in result.output


def test_snapshot_create_dry_run_resolves_local_agent(
    cli_runner: CliRunner,
    temp_work_dir: Path,
    mngr_test_prefix: str,
    plugin_manager: pluggy.PluginManager,
) -> None:
    """Test that --dry-run resolves a local agent and shows it (returns before supports_snapshots check)."""
    agent_name = f"test-snap-dryrun-{int(time.time())}"
    session_name = f"{mngr_test_prefix}{agent_name}"

    with tmux_session_cleanup(session_name):
        cli_runner.invoke(
            create,
            [
                "--name",
                agent_name,
                "--agent-cmd",
                "sleep 748294",
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

        result = cli_runner.invoke(
            snapshot,
            ["create", agent_name, "--dry-run"],
            obj=plugin_manager,
            catch_exceptions=False,
        )

        assert result.exit_code == 0
        assert agent_name in result.output


def test_snapshot_create_dry_run_jsonl_resolves_local_agent(
    cli_runner: CliRunner,
    temp_work_dir: Path,
    mngr_test_prefix: str,
    plugin_manager: pluggy.PluginManager,
) -> None:
    """Test that --dry-run with --format jsonl outputs structured data on stdout."""
    agent_name = f"test-snap-dryrun-jsonl-{int(time.time())}"
    session_name = f"{mngr_test_prefix}{agent_name}"

    with tmux_session_cleanup(session_name):
        cli_runner.invoke(
            create,
            [
                "--name",
                agent_name,
                "--agent-cmd",
                "sleep 748295",
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

        result = cli_runner.invoke(
            snapshot,
            ["create", agent_name, "--dry-run", "--format", "jsonl"],
            obj=plugin_manager,
            catch_exceptions=False,
        )

        assert result.exit_code == 0
        assert "dry_run" in result.output
        assert agent_name in result.output


# =============================================================================
# Tests without agents (lightweight)
# =============================================================================


def test_snapshot_create_all_no_running_agents(
    cli_runner: CliRunner,
    plugin_manager: pluggy.PluginManager,
) -> None:
    """Test that snapshot create --all succeeds when no agents are running."""
    result = cli_runner.invoke(
        snapshot,
        ["create", "--all"],
        obj=plugin_manager,
        catch_exceptions=False,
    )
    assert result.exit_code == 0


def test_snapshot_list_all_no_running_agents(
    cli_runner: CliRunner,
    plugin_manager: pluggy.PluginManager,
) -> None:
    """Test that snapshot list --all succeeds when no agents are running."""
    result = cli_runner.invoke(
        snapshot,
        ["list", "--all"],
        obj=plugin_manager,
        catch_exceptions=False,
    )
    assert result.exit_code == 0


def test_snapshot_create_nonexistent_agent_errors(
    cli_runner: CliRunner,
    plugin_manager: pluggy.PluginManager,
) -> None:
    """Test that snapshot create for a nonexistent agent raises an error."""
    result = cli_runner.invoke(
        snapshot,
        ["create", "nonexistent-agent-99999"],
        obj=plugin_manager,
        catch_exceptions=True,
    )
    assert result.exit_code != 0


def test_snapshot_list_nonexistent_agent_errors(
    cli_runner: CliRunner,
    plugin_manager: pluggy.PluginManager,
) -> None:
    """Test that snapshot list for a nonexistent agent raises an error."""
    result = cli_runner.invoke(
        snapshot,
        ["list", "nonexistent-agent-99999"],
        obj=plugin_manager,
        catch_exceptions=True,
    )
    assert result.exit_code != 0


def test_snapshot_destroy_nonexistent_agent_errors(
    cli_runner: CliRunner,
    plugin_manager: pluggy.PluginManager,
) -> None:
    """Test that snapshot destroy for a nonexistent agent raises an error."""
    result = cli_runner.invoke(
        snapshot,
        ["destroy", "nonexistent-agent-99999", "--all-snapshots", "--force"],
        obj=plugin_manager,
        catch_exceptions=True,
    )
    assert result.exit_code != 0
