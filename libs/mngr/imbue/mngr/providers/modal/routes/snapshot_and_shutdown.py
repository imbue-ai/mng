"""Modal function to snapshot and shut down a host.

This function is deployed as a Modal web endpoint and can be invoked to:
1. Snapshot a running Modal sandbox
2. Store the snapshot ID in the host's volume record
3. Terminate the sandbox

All code is self-contained in this file - no imports from the mngr codebase.
"""

import json
import os
from datetime import datetime
from datetime import timezone

import modal

# Get configuration from environment variables
# These should be set when deploying the function
APP_NAME = os.environ.get("MNGR_MODAL_APP_NAME", "mngr-8caed3bc40df435fae5817ea0afdbf77-modal")
VOLUME_NAME = f"{APP_NAME}-state"

# Create the Modal app and volume reference
image = modal.Image.debian_slim().pip_install("fastapi[standard]")
app = modal.App(name=APP_NAME, image=image)
volume = modal.Volume.from_name(VOLUME_NAME, create_if_missing=True)


def _generate_snapshot_id() -> str:
    """Generate a unique snapshot ID in the format snap-<random_hex>."""
    import uuid

    return f"snap-{uuid.uuid4().hex}"


def _read_host_record(host_id: str) -> dict | None:
    """Read a host record from the volume.

    Returns None if the host record doesn't exist.
    """
    path = f"/vol/{host_id}.json"
    try:
        with open(path) as f:
            return json.load(f)
    except FileNotFoundError:
        return None


def _write_host_record(host_record: dict) -> None:
    """Write a host record to the volume."""
    host_id = host_record["host_id"]
    path = f"/vol/{host_id}.json"
    with open(path, "w") as f:
        json.dump(host_record, f, indent=2)
    volume.commit()


@app.function(volumes={"/vol": volume})
@modal.fastapi_endpoint(method="POST", docs=True)
def snapshot_and_shutdown(request_body: dict) -> dict:
    """Snapshot a Modal sandbox and shut it down.

    Request body should contain:
    - sandbox_id: The Modal sandbox object ID (e.g., "sb-...")
    - host_id: The mngr host ID (e.g., "host-...")
    - snapshot_name: Optional name for the snapshot (auto-generated if not provided)

    Returns:
    - success: Whether the operation succeeded
    - snapshot_id: The mngr snapshot ID (if successful)
    - modal_image_id: The Modal image ID for the snapshot (if successful)
    - error: Error message (if failed)
    """
    sandbox_id = request_body.get("sandbox_id")
    host_id = request_body.get("host_id")
    snapshot_name = request_body.get("snapshot_name")

    if not sandbox_id:
        return {"success": False, "error": "sandbox_id is required"}
    if not host_id:
        return {"success": False, "error": "host_id is required"}

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
            return {
                "success": False,
                "error": f"Host record not found for host_id: {host_id}",
            }

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

    except modal.exception.NotFoundError as e:
        return {"success": False, "error": f"Sandbox not found: {e}"}
    except Exception as e:
        return {"success": False, "error": str(e)}
