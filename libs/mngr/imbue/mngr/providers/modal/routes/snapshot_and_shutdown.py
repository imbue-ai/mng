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
import os
import uuid
from datetime import datetime
from datetime import timezone
from typing import Any

import modal
from fastapi import HTTPException


class ConfigurationError(RuntimeError):
    """Raised when required configuration is missing."""


# Get configuration from environment variables
# When running locally (during `modal deploy`), this must be set.
# When running in Modal's cloud, the app/volume names are already bound
# by Modal's infrastructure, so we use a placeholder.
APP_NAME = os.environ.get("MNGR_MODAL_APP_NAME")

if modal.is_local():
    # During deployment, we need the real app name
    if APP_NAME is None:
        raise ConfigurationError("MNGR_MODAL_APP_NAME environment variable must be set")
    VOLUME_NAME = f"{APP_NAME}-state"
    # Create a secret that passes the app name to the remote function
    app_name_secret = modal.Secret.from_dict({"MNGR_MODAL_APP_NAME": APP_NAME})
else:
    # When running in Modal's cloud, the env var is injected by the secret
    # For module-level code, we use placeholder values since the actual
    # resources are already bound by Modal's infrastructure
    APP_NAME = APP_NAME if APP_NAME is not None else "mngr-placeholder"
    VOLUME_NAME = f"{APP_NAME}-state"
    app_name_secret = modal.Secret.from_dict({})

# Create the Modal app and volume reference
image = modal.Image.debian_slim().pip_install("fastapi[standard]")
app = modal.App(name=APP_NAME, image=image)
volume = modal.Volume.from_name(VOLUME_NAME, create_if_missing=True)


def _generate_snapshot_id() -> str:
    """Generate a unique snapshot ID in the format snap-<random_hex>."""
    return f"snap-{uuid.uuid4().hex}"


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
    host_id = host_record["host_id"]
    path = f"/vol/{host_id}.json"
    with open(path, "w") as f:
        json.dump(host_record, f, indent=2)
    volume.commit()


@app.function(volumes={"/vol": volume}, secrets=[app_name_secret])
@modal.fastapi_endpoint(method="POST", docs=True)
def snapshot_and_shutdown(request_body: dict[str, Any]) -> dict[str, Any]:
    """Snapshot a Modal sandbox and shut it down.

    Request body should contain sandbox_id (Modal sandbox object ID) and
    host_id (mngr host ID). Optionally accepts snapshot_name.
    """
    sandbox_id = request_body.get("sandbox_id")
    host_id = request_body.get("host_id")
    snapshot_name = request_body.get("snapshot_name")

    if not sandbox_id:
        raise HTTPException(status_code=400, detail="sandbox_id is required")
    if not host_id:
        raise HTTPException(status_code=400, detail="host_id is required")

    try:
        # Get the sandbox by ID
        sandbox = modal.Sandbox.from_id(sandbox_id)

        # Create the filesystem snapshot
        modal_image = sandbox.snapshot_filesystem()
        modal_image_id = modal_image.object_id

        # Generate snapshot ID and metadata
        mngr_snapshot_id = _generate_snapshot_id()
        created_at = datetime.now(timezone.utc).isoformat()

        if snapshot_name is None:
            short_id = mngr_snapshot_id[-8:]
            snapshot_name = f"snapshot-{short_id}"

        # Read existing host record
        host_record = _read_host_record(host_id)
        if host_record is None:
            raise HTTPException(
                status_code=404,
                detail=f"Host record not found for host_id: {host_id}",
            )

        # Add the new snapshot to the record
        new_snapshot = {
            "id": mngr_snapshot_id,
            "name": snapshot_name,
            "created_at": created_at,
            "modal_image_id": modal_image_id,
        }

        if "snapshots" not in host_record:
            host_record["snapshots"] = []
        host_record["snapshots"].append(new_snapshot)

        # Write updated host record
        _write_host_record(host_record)

        # Terminate the sandbox
        sandbox.terminate()

        return {
            "success": True,
            "snapshot_id": mngr_snapshot_id,
            "modal_image_id": modal_image_id,
            "snapshot_name": snapshot_name,
        }

    except HTTPException:
        raise
    except modal.exception.NotFoundError as e:
        raise HTTPException(status_code=404, detail=f"Sandbox not found: {e}") from None
    except modal.exception.InvalidError as e:
        # Invalid sandbox ID format also counts as "not found"
        raise HTTPException(status_code=404, detail=f"Invalid sandbox ID: {e}") from None
    except modal.exception.Error as e:
        raise HTTPException(status_code=500, detail=f"Modal error: {e}") from None
