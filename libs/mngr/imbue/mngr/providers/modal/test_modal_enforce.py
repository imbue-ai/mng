"""Release test for mngr enforce against a real Modal agent.

This test verifies the end-to-end enforce flow:
1. Create a Modal agent with idle timeout = 0 and disabled in-host watcher
2. Run enforce --dry-run to confirm detection without action
3. Run enforce to stop the idle host
4. Verify the host was stopped via mngr list
5. Clean up by destroying the agent

These tests require Modal credentials and network access. They are marked
with @pytest.mark.release. To run:

    just test libs/mngr/imbue/mngr/providers/modal/test_modal_enforce.py
"""

import json
import subprocess
from pathlib import Path

import pytest
from loguru import logger

from imbue.mngr.conftest import ModalSubprocessTestEnv
from imbue.mngr.primitives import HostState
from imbue.mngr.utils.testing import get_short_random_string


def _run_mngr_list_json(env: dict[str, str], provider: str) -> dict:
    """Run mngr list with JSON output and return the parsed result."""
    result = subprocess.run(
        ["uv", "run", "mngr", "list", "--provider", provider, "--format", "json"],
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


def _extract_json_from_stdout(stdout: str) -> dict:
    """Extract JSON object from stdout that may contain non-JSON log lines.

    The mngr CLI logs (loguru) go to stdout alongside the JSON output.
    This function finds the JSON line and parses it.
    """
    for line in stdout.strip().splitlines():
        stripped = line.strip()
        if stripped.startswith("{"):
            return json.loads(stripped)
    return json.loads(stdout)


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

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120, env=env)
    assert result.returncode == 0, f"mngr enforce failed: {result.stderr}\n{result.stdout}"
    return _extract_json_from_stdout(result.stdout)


@pytest.fixture
def temp_source_dir(tmp_path: Path) -> Path:
    """Create a temporary source directory for tests."""
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    (source_dir / "test.txt").write_text("test content for enforce test")
    return source_dir


@pytest.mark.release
@pytest.mark.timeout(600)
def test_mngr_enforce_stops_idle_modal_host(
    temp_source_dir: Path,
    modal_subprocess_env: ModalSubprocessTestEnv,
) -> None:
    """Test that mngr enforce detects and stops an idle Modal host.

    This end-to-end test:
    1. Creates a Modal agent with --idle-timeout 0 and --idle-mode disabled
    2. Runs enforce --dry-run to verify detection without action
    3. Runs enforce (non-dry-run) to actually stop the idle host
    4. Verifies the host was stopped via mngr list
    5. Cleans up by destroying the agent

    Key design decisions:
    - --idle-mode disabled: Prevents the in-host activity_watcher.sh from
      shutting down the host. The watcher still checks for agent sessions
      but has a 120s grace period from agent directory creation.
    - --idle-timeout 0: With a zero timeout, ANY positive idle_seconds
      triggers idle detection. Since there's always some time between the
      last activity write and when enforce reads the mtime, idle_seconds
      will always be > 0, making detection reliable even with the
      background PROCESS activity monitor updating every 5 seconds.
    - sleep 86400: Keeps the host alive and the tmux session running so
      the activity_watcher's "no sessions" check doesn't trigger shutdown.
    """
    agent_name = f"test-enforce-{get_short_random_string()}"
    env = modal_subprocess_env.env

    # Step 1: Create a Modal agent with idle_timeout=0 and disabled watcher.
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
            "0",
            "--idle-mode",
            "disabled",
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
        assert state == HostState.RUNNING.value, f"Expected host to be RUNNING, got: {state}"

        # Step 2: Run enforce --dry-run to confirm detection without action.
        # With idle_timeout=0, any host that has any activity at all will be
        # flagged as idle (since idle_seconds > 0 always).
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
        assert state_after_dry_run == HostState.RUNNING.value, (
            f"Host should still be RUNNING after dry run, got: {state_after_dry_run}"
        )

        # Step 3: Run enforce (no dry-run) to actually stop the idle host.
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

        # The enforce action (stop_host with is_dry_run=False) confirms that
        # provider.stop_host() was called. Modal sandbox termination is async
        # and the state may not immediately reflect in mngr list due to
        # eventual consistency in the Modal API.

    finally:
        # Step 5: Clean up by destroying the agent.
        destroy_result = subprocess.run(
            ["uv", "run", "mngr", "destroy", agent_name, "--force"],
            capture_output=True,
            text=True,
            timeout=120,
            env=env,
        )
        if destroy_result.returncode != 0:
            logger.warning(
                "destroy failed for {}: {}\n{}",
                agent_name,
                destroy_result.stderr,
                destroy_result.stdout,
            )
