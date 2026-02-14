"""Integration and release tests for the snapshot CLI command."""

import json
import subprocess
import time
from pathlib import Path
from typing import Any

import pluggy
import pytest
from click.testing import CliRunner

from imbue.mngr.cli.snapshot import snapshot
from imbue.mngr.conftest import ModalSubprocessTestEnv
from imbue.mngr.utils.testing import create_test_agent_via_cli
from imbue.mngr.utils.testing import get_short_random_string
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
        create_test_agent_via_cli(cli_runner, temp_work_dir, mngr_test_prefix, plugin_manager, agent_name)

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
        create_test_agent_via_cli(cli_runner, temp_work_dir, mngr_test_prefix, plugin_manager, agent_name)

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
        create_test_agent_via_cli(cli_runner, temp_work_dir, mngr_test_prefix, plugin_manager, agent_name)

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
        create_test_agent_via_cli(cli_runner, temp_work_dir, mngr_test_prefix, plugin_manager, agent_name)

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
        create_test_agent_via_cli(cli_runner, temp_work_dir, mngr_test_prefix, plugin_manager, agent_name)

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


# =============================================================================
# Release tests (require Modal credentials and network access)
# =============================================================================


def _extract_json(output: str) -> dict[str, Any]:
    """Extract the final JSON object from command output.

    When running CLI commands via subprocess, logger output may precede the
    JSON blob on stdout. This finds the last line that looks like JSON.
    """
    for line in reversed(output.strip().splitlines()):
        line = line.strip()
        if line.startswith("{"):
            return json.loads(line)
    raise AssertionError(f"No JSON found in output:\n{output}")


def _create_modal_agent(
    agent_name: str,
    source_dir: Path,
    env: dict[str, str],
) -> None:
    """Create a Modal agent via the CLI subprocess."""
    result = subprocess.run(
        [
            "uv",
            "run",
            "mngr",
            "create",
            agent_name,
            "--agent-cmd",
            "sleep 3600",
            "--in",
            "modal",
            "--no-connect",
            "--await-ready",
            "--no-ensure-clean",
            "--source",
            str(source_dir),
            "--no-copy-work-dir",
        ],
        capture_output=True,
        text=True,
        timeout=300,
        env=env,
    )
    assert result.returncode == 0, f"Create agent failed: {result.stderr}\n{result.stdout}"


def _destroy_modal_agent(
    agent_name: str,
    env: dict[str, str],
) -> None:
    """Destroy a Modal agent via the CLI subprocess."""
    subprocess.run(
        ["uv", "run", "mngr", "destroy", agent_name, "--force"],
        capture_output=True,
        text=True,
        timeout=120,
        env=env,
    )


@pytest.fixture
def temp_source_dir(tmp_path: Path) -> Path:
    """Create a temporary source directory for Modal tests."""
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    (source_dir / "test.txt").write_text("test content")
    return source_dir


@pytest.mark.release
@pytest.mark.timeout(300)
def test_snapshot_create_list_destroy_on_modal(
    temp_source_dir: Path,
    modal_subprocess_env: ModalSubprocessTestEnv,
) -> None:
    """Test the full snapshot lifecycle on a Modal agent: create, list, destroy.

    Creates a real Modal agent, takes a snapshot, lists it to verify it exists,
    then destroys it and verifies it is gone.
    """
    agent_name = f"test-snap-lifecycle-{get_short_random_string()}"
    env = modal_subprocess_env.env

    _create_modal_agent(agent_name, temp_source_dir, env)
    try:
        # Create a snapshot
        create_result = subprocess.run(
            ["uv", "run", "mngr", "snapshot", "create", agent_name, "--format", "json"],
            capture_output=True,
            text=True,
            timeout=120,
            env=env,
        )
        assert create_result.returncode == 0, f"snapshot create failed: {create_result.stderr}\n{create_result.stdout}"
        create_data = _extract_json(create_result.stdout)
        assert create_data["count"] == 1
        snapshot_id = create_data["snapshots_created"][0]["snapshot_id"]

        # List snapshots and verify the new one appears
        list_result = subprocess.run(
            ["uv", "run", "mngr", "snapshot", "list", agent_name, "--format", "json"],
            capture_output=True,
            text=True,
            timeout=120,
            env=env,
        )
        assert list_result.returncode == 0, f"snapshot list failed: {list_result.stderr}\n{list_result.stdout}"
        list_data = _extract_json(list_result.stdout)
        assert list_data["count"] >= 1
        listed_ids = [s["id"] for s in list_data["snapshots"]]
        assert snapshot_id in listed_ids

        # Destroy the snapshot
        destroy_result = subprocess.run(
            [
                "uv",
                "run",
                "mngr",
                "snapshot",
                "destroy",
                agent_name,
                "--snapshot",
                snapshot_id,
                "--force",
                "--format",
                "json",
            ],
            capture_output=True,
            text=True,
            timeout=120,
            env=env,
        )
        assert destroy_result.returncode == 0, (
            f"snapshot destroy failed: {destroy_result.stderr}\n{destroy_result.stdout}"
        )
        destroy_data = _extract_json(destroy_result.stdout)
        assert destroy_data["count"] == 1

        # Verify the snapshot is gone
        list_after_result = subprocess.run(
            ["uv", "run", "mngr", "snapshot", "list", agent_name, "--format", "json"],
            capture_output=True,
            text=True,
            timeout=120,
            env=env,
        )
        assert list_after_result.returncode == 0
        list_after_data = _extract_json(list_after_result.stdout)
        remaining_ids = [s["id"] for s in list_after_data["snapshots"]]
        assert snapshot_id not in remaining_ids

    finally:
        _destroy_modal_agent(agent_name, env)


@pytest.mark.release
@pytest.mark.timeout(300)
def test_snapshot_create_with_name_on_modal(
    temp_source_dir: Path,
    modal_subprocess_env: ModalSubprocessTestEnv,
) -> None:
    """Test creating a named snapshot on Modal."""
    agent_name = f"test-snap-named-{get_short_random_string()}"
    snapshot_name = "my-checkpoint"
    env = modal_subprocess_env.env

    _create_modal_agent(agent_name, temp_source_dir, env)
    try:
        create_result = subprocess.run(
            [
                "uv",
                "run",
                "mngr",
                "snapshot",
                "create",
                agent_name,
                "--name",
                snapshot_name,
                "--format",
                "json",
            ],
            capture_output=True,
            text=True,
            timeout=120,
            env=env,
        )
        assert create_result.returncode == 0, f"snapshot create failed: {create_result.stderr}\n{create_result.stdout}"

        # List and verify the name appears
        list_result = subprocess.run(
            ["uv", "run", "mngr", "snapshot", "list", agent_name, "--format", "json"],
            capture_output=True,
            text=True,
            timeout=120,
            env=env,
        )
        assert list_result.returncode == 0
        list_data = _extract_json(list_result.stdout)
        snapshot_names = [s["name"] for s in list_data["snapshots"]]
        assert snapshot_name in snapshot_names

        # Clean up snapshot
        subprocess.run(
            ["uv", "run", "mngr", "snapshot", "destroy", agent_name, "--all-snapshots", "--force"],
            capture_output=True,
            text=True,
            timeout=120,
            env=env,
        )
    finally:
        _destroy_modal_agent(agent_name, env)


@pytest.mark.release
@pytest.mark.timeout(300)
def test_snapshot_destroy_all_on_modal(
    temp_source_dir: Path,
    modal_subprocess_env: ModalSubprocessTestEnv,
) -> None:
    """Test destroying all snapshots for a Modal agent."""
    agent_name = f"test-snap-destroyall-{get_short_random_string()}"
    env = modal_subprocess_env.env

    _create_modal_agent(agent_name, temp_source_dir, env)
    try:
        # Create two snapshots
        for _ in range(2):
            result = subprocess.run(
                ["uv", "run", "mngr", "snapshot", "create", agent_name],
                capture_output=True,
                text=True,
                timeout=120,
                env=env,
            )
            assert result.returncode == 0, f"snapshot create failed: {result.stderr}\n{result.stdout}"

        # Verify we have at least 2
        list_result = subprocess.run(
            ["uv", "run", "mngr", "snapshot", "list", agent_name, "--format", "json"],
            capture_output=True,
            text=True,
            timeout=120,
            env=env,
        )
        assert list_result.returncode == 0
        list_data = _extract_json(list_result.stdout)
        assert list_data["count"] >= 2

        # Destroy all
        destroy_result = subprocess.run(
            [
                "uv",
                "run",
                "mngr",
                "snapshot",
                "destroy",
                agent_name,
                "--all-snapshots",
                "--force",
                "--format",
                "json",
            ],
            capture_output=True,
            text=True,
            timeout=120,
            env=env,
        )
        assert destroy_result.returncode == 0
        destroy_data = _extract_json(destroy_result.stdout)
        assert destroy_data["count"] >= 2

        # Verify none remain
        list_after = subprocess.run(
            ["uv", "run", "mngr", "snapshot", "list", agent_name, "--format", "json"],
            capture_output=True,
            text=True,
            timeout=120,
            env=env,
        )
        assert list_after.returncode == 0
        assert _extract_json(list_after.stdout)["count"] == 0

    finally:
        _destroy_modal_agent(agent_name, env)
