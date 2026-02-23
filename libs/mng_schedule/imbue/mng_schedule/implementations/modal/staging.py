"""Shared staging utilities for Modal deployments.

This module contains the install logic for staged deploy files. It is kept
separate from cron_runner.py so that it can be imported by tests without
triggering cron_runner's module-level Modal configuration.

IMPORTANT: This file must NOT import anything from imbue.* packages.
It is imported by cron_runner.py which runs standalone on Modal.
"""

import json
import os
import shutil
from pathlib import Path


def install_deploy_files(staging_base: Path = Path("/staging")) -> None:
    """Install staged deploy files to their expected locations in the container.

    Reads the manifest to determine where each file should be placed.
    Destination paths starting with "~" are expanded to the user's home directory.
    """
    manifest_path = staging_base / "deploy_files_manifest.json"
    if not manifest_path.exists():
        return

    manifest: dict[str, str] = json.loads(manifest_path.read_text())
    files_dir = staging_base / "deploy_files"

    for filename, dest_path_str in manifest.items():
        source = files_dir / filename
        if not source.exists():
            print(f"WARNING: staged file {filename} not found at {source}, skipping")
            continue

        # Expand ~ to home directory
        if dest_path_str.startswith("~"):
            dest_path = Path(os.path.expanduser(dest_path_str))
        else:
            dest_path = Path(dest_path_str)

        dest_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, dest_path)
