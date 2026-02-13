"""Acceptance tests for the cleanup CLI command on Modal.

These tests require Modal credentials and network access. They are marked
with @pytest.mark.acceptance and are skipped by default. To run them:

    just test libs/mngr/imbue/mngr/cli/test_cleanup_acceptance.py

Or with pytest directly:

    pytest -m acceptance --timeout=300 -k cleanup
"""

import json
import subprocess
from pathlib import Path

import pytest

from imbue.mngr.conftest import ModalSubprocessTestEnv
from imbue.mngr.utils.polling import wait_for
from imbue.mngr.utils.testing import get_short_random_string


def _run_mngr_create_on_modal(
    agent_name: str,
    temp_source_dir: Path,
    env: dict[str, str],
) -> None:
    """Create an agent on Modal via subprocess. Asserts success."""
    result = subprocess.run(
        [
            "uv",
            "run",
            "mngr",
            "create",
            agent_name,
            "generic",
            "--in",
            "modal",
            "--no-connect",
            "--await-ready",
            "--no-ensure-clean",
            "--source",
            str(temp_source_dir),
            "--",
            "sleep 3600",
        ],
        capture_output=True,
        text=True,
        timeout=300,
        env=env,
    )
    assert result.returncode == 0, f"Create failed: {result.stderr}\n{result.stdout}"


def _run_mngr_list_json(env: dict[str, str]) -> dict:
    """Run mngr list --format json and return the parsed result."""
    result = subprocess.run(
        [
            "uv",
            "run",
            "mngr",
            "list",
            "--provider",
            "modal",
            "--format",
            "json",
        ],
        capture_output=True,
        text=True,
        timeout=60,
        env=env,
    )
    if result.returncode != 0:
        return {"agents": []}
    return json.loads(result.stdout)


def _agent_exists(agent_name: str, env: dict[str, str]) -> bool:
    """Check if an agent exists by listing agents and looking for the name."""
    list_result = _run_mngr_list_json(env)
    return any(agent.get("name") == agent_name for agent in list_result.get("agents", []))


@pytest.fixture
def temp_source_dir(tmp_path: Path) -> Path:
    """Create a temporary source directory for tests."""
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    (source_dir / "test.txt").write_text("test content")
    return source_dir


@pytest.mark.acceptance
@pytest.mark.timeout(300)
def test_cleanup_destroys_modal_agent(
    temp_source_dir: Path,
    modal_subprocess_env: ModalSubprocessTestEnv,
) -> None:
    """Test that cleanup --yes destroys an agent running on Modal.

    This is an end-to-end acceptance test that verifies:
    1. Agent is created on Modal
    2. cleanup --yes finds and destroys the agent
    3. Agent is no longer listed after cleanup
    """
    agent_name = f"test-cleanup-modal-{get_short_random_string()}"

    # Create agent on Modal
    _run_mngr_create_on_modal(agent_name, temp_source_dir, modal_subprocess_env.env)

    # Verify agent exists
    assert _agent_exists(agent_name, modal_subprocess_env.env), f"Agent {agent_name} should exist after creation"

    # Run cleanup to destroy it
    result = subprocess.run(
        [
            "uv",
            "run",
            "mngr",
            "cleanup",
            "--provider",
            "modal",
            "--yes",
        ],
        capture_output=True,
        text=True,
        timeout=120,
        env=modal_subprocess_env.env,
    )

    assert result.returncode == 0, f"Cleanup failed: {result.stderr}\n{result.stdout}"
    assert "destroyed" in result.stdout.lower(), f"Expected 'destroyed' in output: {result.stdout}"

    # Verify agent is gone (may take a moment for Modal to clean up)
    wait_for(
        lambda: not _agent_exists(agent_name, modal_subprocess_env.env),
        error_message=f"Agent {agent_name} should not exist after cleanup",
        timeout=60,
        poll_interval=5,
    )


@pytest.mark.acceptance
@pytest.mark.timeout(300)
def test_cleanup_dry_run_does_not_destroy_modal_agent(
    temp_source_dir: Path,
    modal_subprocess_env: ModalSubprocessTestEnv,
) -> None:
    """Test that cleanup --dry-run --yes lists but does not destroy a Modal agent."""
    agent_name = f"test-cleanup-modal-dry-{get_short_random_string()}"

    # Create agent on Modal
    _run_mngr_create_on_modal(agent_name, temp_source_dir, modal_subprocess_env.env)

    # Verify agent exists
    assert _agent_exists(agent_name, modal_subprocess_env.env), f"Agent {agent_name} should exist after creation"

    # Run cleanup in dry-run mode
    result = subprocess.run(
        [
            "uv",
            "run",
            "mngr",
            "cleanup",
            "--provider",
            "modal",
            "--dry-run",
            "--yes",
        ],
        capture_output=True,
        text=True,
        timeout=120,
        env=modal_subprocess_env.env,
    )

    assert result.returncode == 0, f"Cleanup dry-run failed: {result.stderr}\n{result.stdout}"
    assert "would destroy" in result.stdout.lower(), f"Expected 'would destroy' in output: {result.stdout}"
    assert agent_name in result.stdout, f"Expected agent name in output: {result.stdout}"

    # Verify agent still exists after dry-run
    assert _agent_exists(agent_name, modal_subprocess_env.env), f"Agent {agent_name} should still exist after dry-run"

    # Clean up the agent we created (don't leave it running)
    subprocess.run(
        [
            "uv",
            "run",
            "mngr",
            "destroy",
            agent_name,
            "--force",
        ],
        capture_output=True,
        text=True,
        timeout=120,
        env=modal_subprocess_env.env,
    )


@pytest.mark.acceptance
@pytest.mark.timeout(300)
def test_cleanup_json_output_with_modal_agent(
    temp_source_dir: Path,
    modal_subprocess_env: ModalSubprocessTestEnv,
) -> None:
    """Test that cleanup --yes --format json produces structured output for Modal agents."""
    agent_name = f"test-cleanup-modal-json-{get_short_random_string()}"

    # Create agent on Modal
    _run_mngr_create_on_modal(agent_name, temp_source_dir, modal_subprocess_env.env)

    # Run cleanup with JSON output
    result = subprocess.run(
        [
            "uv",
            "run",
            "mngr",
            "cleanup",
            "--provider",
            "modal",
            "--yes",
            "--format",
            "json",
        ],
        capture_output=True,
        text=True,
        timeout=120,
        env=modal_subprocess_env.env,
    )

    assert result.returncode == 0, f"Cleanup failed: {result.stderr}\n{result.stdout}"

    # The JSON result is the last line of stdout; earlier lines may contain
    # logger output from the provider layer (e.g. "Stopping Modal sandbox...")
    json_lines = [line for line in result.stdout.strip().split("\n") if line.startswith("{")]
    assert json_lines, f"No JSON output found in stdout: {result.stdout}"
    output = json.loads(json_lines[-1])
    assert agent_name in output["destroyed_agents"], f"Expected {agent_name} in destroyed_agents: {output}"
    assert output["destroyed_count"] >= 1
