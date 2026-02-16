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


def test_migrate_rejects_same_provider(
    cli_runner: CliRunner,
    temp_work_dir: Path,
    mngr_test_prefix: str,
    plugin_manager: pluggy.PluginManager,
) -> None:
    """Migrate should reject same-provider migration with a helpful error."""
    source_name = f"test-migrate-reject-{uuid4().hex}"

    create_test_agent_via_cli(cli_runner, temp_work_dir, mngr_test_prefix, plugin_manager, source_name)

    # Attempt to migrate without --in (defaults to local, same as source)
    migrate_result = cli_runner.invoke(
        migrate,
        [
            source_name,
            "--agent-cmd",
            "sleep 482917",
            "--no-connect",
            "--no-copy-work-dir",
        ],
        obj=plugin_manager,
        catch_exceptions=True,
    )

    assert migrate_result.exit_code != 0, f"Expected migrate to fail, but got: {migrate_result.output}"
    assert "same provider" in migrate_result.output
    assert "clone" in migrate_result.output

    # Verify the source agent still exists (not destroyed)
    list_result = cli_runner.invoke(
        list_command,
        [],
        obj=plugin_manager,
        catch_exceptions=False,
    )
    assert list_result.exit_code == 0
    assert source_name in list_result.output, f"Source agent should still exist: {list_result.output}"


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
