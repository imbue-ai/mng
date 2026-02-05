"""Modal function to snapshot and shut down a host.

This function is deployed as a Modal web endpoint and can be invoked to:
1. Snapshot a running Modal sandbox
2. Store the snapshot ID in the host's volume record
3. Terminate the sandbox

All code is self-contained in this file - no imports from the mngr codebase.

Required environment variable (must be set when deploying):
- MNGR_MODAL_APP_NAME: The Modal app name (e.g., "mngr-<user_id>-modal")
"""

import json
import logging
import os
from datetime import datetime
from datetime import timezone
from pathlib import Path
from typing import Any

import modal
from fastapi import HTTPException


class ConfigurationError(RuntimeError):
    """Raised when required configuration is missing."""


if modal.is_local():
    APP_NAME = os.environ.get("MNGR_MODAL_APP_NAME")
    if APP_NAME is None:
        raise ConfigurationError("MNGR_MODAL_APP_NAME environment variable must be set")
    output_app_name_file = Path(".mngr/dev/build/app_name")
    output_app_name_file.parent.mkdir(parents=True, exist_ok=True)
    output_app_name_file.write_text(APP_NAME)
else:
    APP_NAME = Path("/deployment/app_name").read_text().strip()

image = (
    modal.Image.debian_slim()
    .uv_pip_install("fastapi[standard]")
    .add_local_file(".mngr/dev/build/app_name", "/deployment/app_name", copy=True)
)

app = modal.App(name=APP_NAME, image=image)
VOLUME_NAME = f"{APP_NAME}-state"
volume = modal.Volume.from_name(VOLUME_NAME, create_if_missing=True)


def _read_host_record(host_id: str) -> dict[str, Any] | None:
    """Read a host record from the volume.

    Reloads the volume first to ensure we have the latest data,
    as Modal volumes aren't automatically refreshed between function calls.
    """
    # Reload the volume to get latest data (changes made externally)
    volume.reload()
    path = f"/vol/{host_id}.json"
    try:
        with open(path) as f:
            return json.load(f)
    except FileNotFoundError:
        return None


def _write_host_record(host_record: dict[str, Any]) -> None:
    """Write a host record to the volume."""
    host_id = host_record["certified_host_data"]["host_id"]
    path = f"/vol/{host_id}.json"
    with open(path, "w") as f:
        json.dump(host_record, f, indent=2)
    volume.commit()


def _write_agent_records(host_id: str, agents: list[dict[str, Any]]) -> None:
    """Write agent records to the volume.

    Each agent is stored at /vol/{host_id}/{agent_id}.json so that
    stopped hosts can still show their agents in mngr list.
    """
    if not agents:
        return

    # Create the host directory if it doesn't exist
    host_dir = f"/vol/{host_id}"
    os.makedirs(host_dir, exist_ok=True)

    # Write each agent's data
    for agent in agents:
        agent_id = agent.get("id")
        if agent_id:
            agent_path = f"{host_dir}/{agent_id}.json"
            with open(agent_path, "w") as f:
                json.dump(agent, f, indent=2)

    volume.commit()


@app.function(volumes={"/vol": volume})
@modal.fastapi_endpoint(method="POST", docs=True)
def snapshot_and_shutdown(request_body: dict[str, Any]) -> dict[str, Any]:
    """Snapshot a Modal sandbox and shut it down.

    Request body should contain sandbox_id (Modal sandbox object ID) and
    host_id (mngr host ID). Optionally accepts snapshot_name, agents
    (list of agent data to persist to the volume), and stop_reason
    ('PAUSED' for idle shutdown, 'STOPPED' for user-requested stop).
    """
    logger = logging.getLogger("snapshot_and_shutdown")

    try:
        try:
            sandbox_id = request_body.get("sandbox_id")
            host_id = request_body.get("host_id")
            snapshot_name = request_body.get("snapshot_name")
            agents = request_body.get("agents", [])
            stop_reason = request_body.get("stop_reason", "PAUSED")

            if not sandbox_id:
                raise HTTPException(status_code=400, detail="sandbox_id is required")
            if not host_id:
                raise HTTPException(status_code=400, detail="host_id is required")

            # Verify host record exists BEFORE creating snapshot to avoid orphaned images
            host_record = _read_host_record(host_id)
            if host_record is None:
                raise HTTPException(
                    status_code=404,
                    detail=f"Host record not found for host_id: {host_id}",
                )

            # Get the sandbox by ID
            sandbox = modal.Sandbox.from_id(sandbox_id)

            # Create the filesystem snapshot
            modal_image = sandbox.snapshot_filesystem()
            # Use the Modal image ID directly as the snapshot ID
            snapshot_id = modal_image.object_id
            created_at = datetime.now(timezone.utc).isoformat()

            if snapshot_name is None:
                short_id = snapshot_id[-8:]
                snapshot_name = f"snapshot-{short_id}"

            # Add the new snapshot to the certified_host_data (id is the Modal image ID)
            new_snapshot = {
                "id": snapshot_id,
                "name": snapshot_name,
                "created_at": created_at,
            }

            certified_data = host_record.get("certified_host_data", {})
            if "snapshots" not in certified_data:
                certified_data["snapshots"] = []
            certified_data["snapshots"].append(new_snapshot)

            # Record the stop reason (PAUSED for idle, STOPPED for user-requested)
            certified_data["stop_reason"] = stop_reason
            host_record["certified_host_data"] = certified_data

            # Write updated host record
            _write_host_record(host_record)

            # Write agent records so they appear in mngr list for stopped hosts
            _write_agent_records(host_id, agents)

            # Terminate the sandbox
            sandbox.terminate()

            return {
                "success": True,
                "snapshot_id": snapshot_id,
                "snapshot_name": snapshot_name,
            }

        except BaseException as e:
            logger.error("Error in snapshot_and_shutdown: " + str(e), exc_info=True)
            raise

    except HTTPException:
        raise
    except modal.exception.NotFoundError as e:
        raise HTTPException(status_code=404, detail=f"Sandbox not found: {e}") from None
    except modal.exception.InvalidError as e:
        # Invalid sandbox ID format also counts as "not found"
        raise HTTPException(status_code=404, detail=f"Invalid sandbox ID: {e}") from None
    except modal.exception.Error as e:
        raise HTTPException(status_code=500, detail=f"Modal error: {e}") from None
