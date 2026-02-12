"""Release test for mngr enforce against a real Modal agent.

This test verifies the end-to-end enforce flow:
1. Create a Modal agent with a short idle timeout
2. Wait for the host to become idle
3. Run enforce --dry-run to confirm detection without action
4. Run enforce to stop the idle host
5. Verify the host was stopped via mngr list
6. Clean up by destroying the agent

These tests require Modal credentials and network access. They are marked
with @pytest.mark.release. To run:

    just test libs/mngr/imbue/mngr/providers/modal/test_modal_enforce.py
"""

import json
import subprocess
import time
from pathlib import Path

import pytest

from imbue.mngr.conftest import ModalSubprocessTestEnv
from imbue.mngr.utils.polling import wait_for
from imbue.mngr.utils.testing import get_short_random_string


def _run_mngr_list_json(env: dict[str, str], provider: str) -> dict:
    """Run mngr list with JSON output and return the parsed result."""
    result = subprocess.run(
        [
            "uv",
            "run",
            "mngr",
            "list",
            "--provider",
            provider,
            "--format",
            "json",
        ],
        capture_output=True,
        text=True,
        timeout=60,
        env=env,
    )
    assert result.returncode == 0, f"mngr list failed: {result.stderr}\n{result.stdout}"
    return json.loads(result.stdout)


def _get_host_state(env: dict[str, str], provider: str, host_name: str) -> str | None:
    """Get the state of a host by name. Returns None if not found."""
    list_result = _run_mngr_list_json(env, provider)
    for agent in list_result.get("agents", []):
        host = agent.get("host", {})
        if host.get("name") == host_name:
            return host.get("state")
    return None


def _run_mngr_enforce_json(
    env: dict[str, str],
    *,
    dry_run: bool,
    provider: str = "modal",
) -> dict:
    """Run mngr enforce with JSON output and return the parsed result."""
    cmd = [
        "uv",
        "run",
        "mngr",
        "enforce",
        "--provider",
        provider,
        "--format",
        "json",
        "--check-idle",
        "--no-check-timeouts",
    ]
    if dry_run:
        cmd.append("--dry-run")

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=120,
        env=env,
    )
    assert result.returncode == 0, f"mngr enforce failed: {result.stderr}\n{result.stdout}"
    return json.loads(result.stdout)


@pytest.fixture
def temp_source_dir(tmp_path: Path) -> Path:
    """Create a temporary source directory for tests."""
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    (source_dir / "test.txt").write_text("test content for enforce test")
    return source_dir


@pytest.mark.release
@pytest.mark.timeout(300)
def test_mngr_enforce_stops_idle_modal_host(
    temp_source_dir: Path,
    modal_subprocess_env: ModalSubprocessTestEnv,
) -> None:
    """Test that mngr enforce detects and stops an idle Modal host.

    This end-to-end test:
    1. Creates a Modal agent with a 30s idle timeout (boot mode)
    2. Waits ~40s for the host to exceed its idle timeout
    3. Runs enforce --dry-run to verify detection without action
    4. Runs enforce to actually stop the idle host
    5. Verifies the host was stopped via mngr list
    6. Cleans up by destroying the agent
    """
    agent_name = f"test-enforce-{get_short_random_string()}"
    env = modal_subprocess_env.env

    # Step 1: Create a Modal agent with a short idle timeout.
    # --idle-mode boot means only boot counts as activity, so the host
    # will be considered idle 30 seconds after boot.
    # --no-ensure-clean since the source dir is a fresh git repo with no remote.
    create_result = subprocess.run(
        [
            "uv",
            "run",
            "mngr",
            "create",
            agent_name,
            "generic",
            "--in",
            "modal",
            "--idle-timeout",
            "30",
            "--idle-mode",
            "boot",
            "--no-connect",
            "--await-ready",
            "--no-ensure-clean",
            "--source",
            str(temp_source_dir),
            "--",
            "sleep 86400",
        ],
        capture_output=True,
        text=True,
        timeout=300,
        env=env,
    )
    assert create_result.returncode == 0, f"Agent creation failed: {create_result.stderr}\n{create_result.stdout}"

    # Find the host name from mngr list
    list_result = _run_mngr_list_json(env, "modal")
    host_name = None
    for agent in list_result.get("agents", []):
        if agent.get("name") == agent_name:
            host_name = agent.get("host", {}).get("name")
            break
    assert host_name is not None, f"Could not find host for agent {agent_name}"

    try:
        # Verify the host is running
        state = _get_host_state(env, "modal", host_name)
        assert state == "running", f"Expected host to be running, got: {state}"

        # Step 2: Wait ~40 seconds for the host to exceed its 30s idle timeout.
        time.sleep(40)

        # Step 3: Run enforce --dry-run to confirm detection without action.
        dry_run_result = _run_mngr_enforce_json(env, dry_run=True)
        assert dry_run_result["idle_violations"] >= 1, (
            f"Expected at least 1 idle violation in dry run, got: {dry_run_result}"
        )
        assert dry_run_result["dry_run"] is True
        # Verify our host is in the actions
        dry_run_actions = dry_run_result.get("actions", [])
        our_action = next(
            (a for a in dry_run_actions if a["host_name"] == host_name),
            None,
        )
        assert our_action is not None, (
            f"Expected to find action for host {host_name} in dry run, got: {dry_run_actions}"
        )
        assert our_action["action"] == "stop_host"
        assert our_action["is_dry_run"] is True

        # Verify host is still running after dry run (no action taken)
        state_after_dry_run = _get_host_state(env, "modal", host_name)
        assert state_after_dry_run == "running", (
            f"Host should still be running after dry run, got: {state_after_dry_run}"
        )

        # Step 4: Run enforce (no dry-run) to actually stop the idle host.
        enforce_result = _run_mngr_enforce_json(env, dry_run=False)
        assert enforce_result["idle_violations"] >= 1, f"Expected at least 1 idle violation, got: {enforce_result}"
        assert enforce_result["dry_run"] is False
        enforce_actions = enforce_result.get("actions", [])
        our_enforce_action = next(
            (a for a in enforce_actions if a["host_name"] == host_name),
            None,
        )
        assert our_enforce_action is not None, (
            f"Expected to find action for host {host_name} in enforce, got: {enforce_actions}"
        )
        assert our_enforce_action["action"] == "stop_host"
        assert our_enforce_action["is_dry_run"] is False

        # Step 5: Verify the host was stopped via mngr list.
        # The stop may take a moment to propagate, so poll briefly.
        def host_is_not_running() -> bool:
            s = _get_host_state(env, "modal", host_name)
            return s is not None and s != "running"

        wait_for(
            host_is_not_running,
            timeout=60.0,
            poll_interval=5.0,
            error_message=f"Host {host_name} did not stop within 60 seconds after enforce",
        )

        final_state = _get_host_state(env, "modal", host_name)
        assert final_state in ("stopped", "paused", "destroyed"), (
            f"Expected host to be stopped/paused/destroyed, got: {final_state}"
        )

    finally:
        # Step 6: Clean up by destroying the agent.
        destroy_result = subprocess.run(
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
            env=env,
        )
        # Log but don't assert on destroy -- best-effort cleanup.
        # The session-scoped Modal cleanup fixture will handle any leftovers.
        if destroy_result.returncode != 0:
            print(f"Warning: destroy failed for {agent_name}: {destroy_result.stderr}\n{destroy_result.stdout}")
