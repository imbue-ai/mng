"""Tests for the snapshot_and_shutdown Modal function.

Unit tests verify the helper functions without deploying to Modal.
Acceptance tests deploy the function to Modal and verify end-to-end functionality.
"""

import io
import json
import os
import subprocess
from collections.abc import Generator
from typing import Any
from unittest.mock import MagicMock
from unittest.mock import patch

import httpx
import modal
import pytest

from imbue.mngr.conftest import register_modal_test_volume
from imbue.mngr.providers.modal.constants import MODAL_TEST_APP_PREFIX
from imbue.mngr.providers.modal.routes.deployment import deploy_function
from imbue.mngr.utils.polling import wait_for
from imbue.mngr.utils.testing import get_short_random_string

# Set env var before importing snapshot_and_shutdown module (required for unit tests)
os.environ.setdefault("MNGR_MODAL_APP_NAME", "mngr-test-unit")

# Import after setting env var since the module requires MNGR_MODAL_APP_NAME at import time
from imbue.mngr.providers.modal.routes.snapshot_and_shutdown import (
    _write_agent_records,
)


# =============================================================================
# Unit tests for _write_agent_records
# =============================================================================


def test_write_agent_records_with_empty_list() -> None:
    """_write_agent_records should return early when agents list is empty."""
    mock_volume = MagicMock()

    with patch("imbue.mngr.providers.modal.routes.snapshot_and_shutdown.volume", mock_volume):
        _write_agent_records("host-123", [])

    # Should not create any directories or files or call commit
    mock_volume.commit.assert_not_called()


def test_write_agent_records_writes_agent_files() -> None:
    """_write_agent_records should write each agent to a JSON file."""
    mock_volume = MagicMock()

    with (
        patch("imbue.mngr.providers.modal.routes.snapshot_and_shutdown.volume", mock_volume),
        patch("imbue.mngr.providers.modal.routes.snapshot_and_shutdown.os.makedirs") as mock_makedirs,
        patch("builtins.open", create=True) as mock_open,
    ):
        # Set up mock file handle
        mock_file = MagicMock()
        mock_open.return_value.__enter__.return_value = mock_file

        agents = [
            {"id": "agent-1", "name": "test-agent-1", "type": "claude"},
            {"id": "agent-2", "name": "test-agent-2", "type": "codex"},
        ]

        _write_agent_records("host-123", agents)

        # Verify directory was created
        mock_makedirs.assert_called_once_with("/vol/host-123", exist_ok=True)

        # Verify files were opened for writing
        assert mock_open.call_count == 2
        mock_open.assert_any_call("/vol/host-123/agent-1.json", "w")
        mock_open.assert_any_call("/vol/host-123/agent-2.json", "w")

        # Verify volume.commit() was called
        mock_volume.commit.assert_called_once()


def test_write_agent_records_skips_agents_without_id() -> None:
    """_write_agent_records should skip agents that don't have an 'id' field."""
    mock_volume = MagicMock()

    with (
        patch("imbue.mngr.providers.modal.routes.snapshot_and_shutdown.volume", mock_volume),
        patch("imbue.mngr.providers.modal.routes.snapshot_and_shutdown.os.makedirs"),
        patch("builtins.open", create=True) as mock_open,
    ):
        mock_file = MagicMock()
        mock_open.return_value.__enter__.return_value = mock_file

        # Agents without valid IDs should be skipped
        agents = [
            {"id": "agent-1", "name": "test-agent-1"},
            {"name": "no-id-agent"},
            {"id": None, "name": "null-id-agent"},
            {"id": "agent-3", "name": "test-agent-3"},
        ]

        _write_agent_records("host-456", agents)

        # Should only write files for agents with valid IDs
        assert mock_open.call_count == 2
        mock_open.assert_any_call("/vol/host-456/agent-1.json", "w")
        mock_open.assert_any_call("/vol/host-456/agent-3.json", "w")


def test_write_agent_records_writes_correct_json() -> None:
    """_write_agent_records should write the agent data as JSON with indentation."""
    mock_volume = MagicMock()

    # Capture what json.dump writes
    written_data: dict[str, Any] = {}

    def capture_json_dump(data: Any, f: Any, **kwargs: Any) -> None:
        written_data["agent"] = data

    with (
        patch("imbue.mngr.providers.modal.routes.snapshot_and_shutdown.volume", mock_volume),
        patch("imbue.mngr.providers.modal.routes.snapshot_and_shutdown.os.makedirs"),
        patch("builtins.open", MagicMock()),
        patch("imbue.mngr.providers.modal.routes.snapshot_and_shutdown.json.dump", capture_json_dump),
    ):
        agent = {"id": "agent-test", "name": "test-agent", "type": "claude", "work_dir": "/work"}
        _write_agent_records("host-789", [agent])

    # Verify the correct data was passed to json.dump
    assert written_data["agent"] == agent


# =============================================================================
# Acceptance tests (require Modal network access)
# =============================================================================


class DeploymentError(RuntimeError):
    """Raised when deploying the Modal function fails."""


class URLParseError(RuntimeError):
    """Raised when the function URL cannot be parsed from deploy output."""


def _get_test_app_name() -> str:
    """Generate a unique test app name with the mngr-test prefix."""
    return f"{MODAL_TEST_APP_PREFIX}snapshot-{get_short_random_string()}"


def _stop_app(app_name: str) -> None:
    """Stop and clean up a Modal app."""
    subprocess.run(
        ["uv", "run", "modal", "app", "stop", app_name],
        input=b"y\n",
        capture_output=True,
        timeout=60,
    )


def _delete_volume(volume_name: str) -> None:
    """Delete a Modal volume."""
    subprocess.run(
        ["uv", "run", "modal", "volume", "delete", volume_name, "--yes"],
        capture_output=True,
        timeout=60,
    )


def _warmup_function(url: str) -> None:
    """Send a warmup request to trigger cold start before tests run.

    This ensures the Modal container is warm and subsequent test requests
    complete within reasonable timeouts.
    """
    # Send a simple request that will fail validation but warm up the function
    # Use a longer timeout since this is the cold start
    try:
        httpx.post(url, json={}, timeout=180)
    except httpx.HTTPError:
        # Ignore errors - we just want to trigger the cold start
        pass


def _create_test_sandbox(app_name: str) -> tuple[modal.Sandbox, str]:
    """Create a test sandbox within the given app.

    Creates a simple sandbox that sleeps, suitable for testing snapshot functionality.
    """
    app = modal.App.lookup(app_name, create_if_missing=True)
    sandbox = modal.Sandbox.create(
        app=app,
        image=modal.Image.debian_slim(),
        timeout=300,
    )
    sandbox.exec("sleep", "3600")
    return sandbox, sandbox.object_id


def _write_host_record_to_volume(app_name: str, host_id: str) -> None:
    """Write a host record to the Modal volume for testing.

    Creates a minimal host record that the snapshot function can update.
    """
    volume_name = f"{app_name}-state"
    register_modal_test_volume(volume_name)
    volume = modal.Volume.from_name(volume_name, create_if_missing=True)

    host_record = {
        "host_id": host_id,
        "sandbox_id": "",
        "snapshots": [],
    }

    content = json.dumps(host_record, indent=2).encode("utf-8")
    with volume.batch_upload() as batch:
        batch.put_file(io.BytesIO(content), f"/{host_id}.json")


def _read_host_record_from_volume(app_name: str, host_id: str) -> dict[str, Any] | None:
    """Read a host record from the Modal volume."""
    volume_name = f"{app_name}-state"
    register_modal_test_volume(volume_name)
    volume = modal.Volume.from_name(volume_name)

    try:
        content = b"".join(volume.read_file(f"/{host_id}.json"))
        return json.loads(content.decode("utf-8"))
    except modal.exception.NotFoundError:
        return None


@pytest.fixture(scope="module")
def deployed_snapshot_function() -> Generator[tuple[str, str], None, None]:
    """Deploy the snapshot function for testing and clean up after.

    Yields a tuple of (app_name, function_url).
    """
    app_name = _get_test_app_name()
    # The deployed function creates a volume named {app_name}-state
    volume_name = f"{app_name}-state"
    register_modal_test_volume(volume_name)

    try:
        url = deploy_function("snapshot_and_shutdown", app_name, None)
        # Warm up the function to avoid cold start timeouts in tests
        _warmup_function(url)
        yield (app_name, url)
    finally:
        _stop_app(app_name)
        _delete_volume(volume_name)


@pytest.mark.acceptance
@pytest.mark.timeout(180)
def test_snapshot_and_shutdown_success(
    deployed_snapshot_function: tuple[str, str],
) -> None:
    """Test successful snapshot and shutdown of a sandbox.

    Creates a sandbox, writes a host record, calls the endpoint, and verifies:
    1. The response indicates success
    2. The host record was updated with snapshot info
    3. The sandbox was terminated
    """
    app_name, function_url = deployed_snapshot_function
    host_id = f"host-test-{get_short_random_string()}"

    # Create a test sandbox
    sandbox, sandbox_id = _create_test_sandbox(app_name)

    try:
        # Write initial host record to volume
        _write_host_record_to_volume(app_name, host_id)

        # Call the snapshot_and_shutdown endpoint
        response = httpx.post(
            function_url,
            json={
                "sandbox_id": sandbox_id,
                "host_id": host_id,
            },
            timeout=120,
        )

        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"

        result = response.json()
        assert result["success"] is True, f"Expected success=True: {result}"
        assert "snapshot_id" in result
        assert "modal_image_id" in result
        assert result["snapshot_id"].startswith("snap-")

        # Verify the host record was updated
        host_record = _read_host_record_from_volume(app_name, host_id)
        assert host_record is not None, "Host record not found after snapshot"
        assert len(host_record["snapshots"]) == 1
        assert host_record["snapshots"][0]["id"] == result["snapshot_id"]
        assert host_record["snapshots"][0]["modal_image_id"] == result["modal_image_id"]

        # Verify the sandbox was terminated by polling for termination
        def sandbox_terminated() -> bool:
            refreshed_sandbox = modal.Sandbox.from_id(sandbox_id)
            poll_result = refreshed_sandbox.poll()
            return poll_result is not None

        wait_for(sandbox_terminated, timeout=10.0, poll_interval=0.5, error_message="Sandbox should be terminated")

    finally:
        # Clean up sandbox if still running
        try:
            sandbox.terminate()
        except modal.exception.Error:
            pass


@pytest.mark.acceptance
@pytest.mark.timeout(180)
def test_snapshot_and_shutdown_missing_sandbox_id(
    deployed_snapshot_function: tuple[str, str],
) -> None:
    """Test that missing sandbox_id returns 400 error."""
    _, function_url = deployed_snapshot_function

    response = httpx.post(
        function_url,
        json={"host_id": "some-host-id"},
        timeout=60,
    )

    assert response.status_code == 400
    assert "sandbox_id" in response.text.lower()


@pytest.mark.acceptance
@pytest.mark.timeout(180)
def test_snapshot_and_shutdown_missing_host_id(
    deployed_snapshot_function: tuple[str, str],
) -> None:
    """Test that missing host_id returns 400 error."""
    _, function_url = deployed_snapshot_function

    response = httpx.post(
        function_url,
        json={"sandbox_id": "some-sandbox-id"},
        timeout=60,
    )

    assert response.status_code == 400
    assert "host_id" in response.text.lower()


@pytest.mark.acceptance
@pytest.mark.timeout(180)
def test_snapshot_and_shutdown_nonexistent_sandbox(
    deployed_snapshot_function: tuple[str, str],
) -> None:
    """Test that a nonexistent sandbox returns 404 error."""
    app_name, function_url = deployed_snapshot_function
    host_id = f"host-test-{get_short_random_string()}"

    # Write a host record so we can verify the sandbox lookup fails
    _write_host_record_to_volume(app_name, host_id)

    response = httpx.post(
        function_url,
        json={
            "sandbox_id": "sb-nonexistent-id-12345",
            "host_id": host_id,
        },
        timeout=60,
    )

    assert response.status_code == 404
    assert "sandbox" in response.text.lower() or "not found" in response.text.lower()


@pytest.mark.acceptance
@pytest.mark.timeout(180)
def test_snapshot_and_shutdown_nonexistent_host_record(
    deployed_snapshot_function: tuple[str, str],
) -> None:
    """Test that a nonexistent host record returns 404 error."""
    app_name, function_url = deployed_snapshot_function
    host_id = f"host-nonexistent-{get_short_random_string()}"

    # Create a real sandbox but don't create a host record
    sandbox, sandbox_id = _create_test_sandbox(app_name)

    try:
        response = httpx.post(
            function_url,
            json={
                "sandbox_id": sandbox_id,
                "host_id": host_id,
            },
            timeout=60,
        )

        assert response.status_code == 404
        assert "host" in response.text.lower() or "not found" in response.text.lower()

    finally:
        try:
            sandbox.terminate()
        except modal.exception.Error:
            pass
