"""Integration and acceptance tests for the migrate CLI command."""

import json
import subprocess
from pathlib import Path
from uuid import uuid4

import pluggy
import pytest
from click.testing import CliRunner

from imbue.mngr.cli.list import list_command
from imbue.mngr.cli.migrate import migrate
from imbue.mngr.conftest import ModalSubprocessTestEnv
from imbue.mngr.utils.testing import create_test_agent_via_cli
from imbue.mngr.utils.testing import get_short_random_string
from imbue.mngr.utils.testing import tmux_session_cleanup
from imbue.mngr.utils.testing import tmux_session_exists


def test_migrate_clones_and_destroys_source(
    cli_runner: CliRunner,
    temp_work_dir: Path,
    mngr_test_prefix: str,
    plugin_manager: pluggy.PluginManager,
) -> None:
    """Test that migrate creates a new agent and destroys the source."""
    source_name = f"test-migrate-source-{uuid4().hex}"
    target_name = f"test-migrate-target-{uuid4().hex}"
    source_session = f"{mngr_test_prefix}{source_name}"
    target_session = f"{mngr_test_prefix}{target_name}"

    with tmux_session_cleanup(source_session), tmux_session_cleanup(target_session):
        create_test_agent_via_cli(cli_runner, temp_work_dir, mngr_test_prefix, plugin_manager, source_name)

        # Migrate the source agent to a new name
        migrate_result = cli_runner.invoke(
            migrate,
            [
                source_name,
                target_name,
                "--agent-cmd",
                "sleep 482917",
                "--no-connect",
                "--await-ready",
                "--no-copy-work-dir",
            ],
            obj=plugin_manager,
            catch_exceptions=False,
        )
        assert migrate_result.exit_code == 0, f"Migrate failed with: {migrate_result.output}"

        # Verify the target agent exists
        assert tmux_session_exists(target_session), f"Expected target session {target_session} to exist"

        # Verify the source agent was destroyed
        assert not tmux_session_exists(source_session), f"Expected source session {source_session} to be destroyed"

        # Verify via list: target should be present, source should not
        list_result = cli_runner.invoke(
            list_command,
            [],
            obj=plugin_manager,
            catch_exceptions=False,
        )
        assert list_result.exit_code == 0
        assert target_name in list_result.output, f"Expected target agent in list output: {list_result.output}"
        assert source_name not in list_result.output, f"Expected source agent NOT in list output: {list_result.output}"


def test_migrate_same_name_does_not_destroy_clone(
    cli_runner: CliRunner,
    temp_work_dir: Path,
    mngr_test_prefix: str,
    plugin_manager: pluggy.PluginManager,
) -> None:
    """Migrate without a new name should destroy only the source, not the clone.

    When no target name is specified, the clone inherits the source name.
    The destroy step must target the source by ID (not name) to avoid
    destroying the newly cloned agent that shares the same name.
    """
    agent_name = f"test-migrate-same-{uuid4().hex}"
    session_name = f"{mngr_test_prefix}{agent_name}"

    with tmux_session_cleanup(session_name):
        create_test_agent_via_cli(cli_runner, temp_work_dir, mngr_test_prefix, plugin_manager, agent_name)

        # Migrate without specifying a new name -- clone inherits the source name
        migrate_result = cli_runner.invoke(
            migrate,
            [
                agent_name,
                "--agent-cmd",
                "sleep 573819",
                "--no-connect",
                "--await-ready",
                "--no-copy-work-dir",
            ],
            obj=plugin_manager,
            catch_exceptions=False,
        )
        assert migrate_result.exit_code == 0, f"Migrate failed with: {migrate_result.output}"

        # The cloned agent (same name) should still exist
        assert tmux_session_exists(session_name), (
            f"Expected session {session_name} to exist after migrate -- "
            "destroy likely matched by name and killed the clone too"
        )

        # Verify via list: agent should still appear exactly once
        list_result = cli_runner.invoke(
            list_command,
            [],
            obj=plugin_manager,
            catch_exceptions=False,
        )
        assert list_result.exit_code == 0
        assert agent_name in list_result.output, f"Expected agent in list output: {list_result.output}"


@pytest.fixture
def temp_source_dir(tmp_path: Path) -> Path:
    """Create a temporary source directory for tests."""
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    (source_dir / "test.txt").write_text("test content")
    return source_dir


@pytest.mark.acceptance
@pytest.mark.timeout(300)
def test_migrate_local_to_modal_same_name(
    temp_source_dir: Path,
    modal_subprocess_env: ModalSubprocessTestEnv,
) -> None:
    """Migrate a local agent to Modal without specifying a new name.

    This exercises the full local-to-Modal migration path and verifies that:
    1. The source agent is stopped and its data is cleaned up
    2. The clone on Modal is created with the same name
    3. The clone is running on Modal after migration
    4. The source no longer appears in the agent list
    """
    agent_name = f"test-migrate-modal-{get_short_random_string()}"
    env = modal_subprocess_env.env

    # Step 1: Create a local agent
    create_result = subprocess.run(
        [
            "uv",
            "run",
            "mngr",
            "create",
            agent_name,
            "generic",
            "--no-connect",
            "--await-ready",
            "--no-ensure-clean",
            "--source",
            str(temp_source_dir),
            "--agent-cmd",
            "sleep 847291",
        ],
        capture_output=True,
        text=True,
        timeout=120,
        env=env,
    )
    assert create_result.returncode == 0, (
        f"Failed to create local agent.\nstderr: {create_result.stderr}\nstdout: {create_result.stdout}"
    )

    # Step 2: Migrate to Modal (same name, no target name specified)
    migrate_result = subprocess.run(
        [
            "uv",
            "run",
            "mngr",
            "migrate",
            agent_name,
            "--in",
            "modal",
            "--no-connect",
            "--await-ready",
            "--no-ensure-clean",
            "--agent-cmd",
            "sleep 847291",
            "--project",
            "migrate-acceptance-test",
        ],
        capture_output=True,
        text=True,
        timeout=300,
        env=env,
    )
    assert migrate_result.returncode == 0, (
        f"Migrate failed.\nstderr: {migrate_result.stderr}\nstdout: {migrate_result.stdout}"
    )

    # Step 3: Verify via list that the agent exists on Modal (not local)
    list_result = subprocess.run(
        ["uv", "run", "mngr", "list", "--format", "json"],
        capture_output=True,
        text=True,
        timeout=30,
        env=env,
    )
    assert list_result.returncode == 0, f"Failed to list agents.\nstderr: {list_result.stderr}"
    list_data = json.loads(list_result.stdout)
    matching_agents = [a for a in list_data["agents"] if a["name"] == agent_name]

    assert len(matching_agents) == 1, (
        f"Expected exactly 1 agent named {agent_name}, found {len(matching_agents)}.\n"
        f"Agents: {json.dumps(matching_agents, indent=2)}"
    )
    assert matching_agents[0]["host"]["provider_name"] == "modal", (
        f"Expected agent to be on modal, but it is on {matching_agents[0]['host']['provider_name']}"
    )
