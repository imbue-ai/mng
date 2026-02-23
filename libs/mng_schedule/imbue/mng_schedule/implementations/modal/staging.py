"""Shared staging utilities for Modal deployments.

This module contains the install logic for staged deploy files. It is kept
separate from cron_runner.py so that it can be imported by tests without
triggering cron_runner's module-level Modal configuration.

IMPORTANT: This file must NOT import anything from imbue.* packages.
It is imported by cron_runner.py which runs standalone on Modal.
"""

import shutil
from pathlib import Path


def install_deploy_files(staging_base: Path = Path("/staging")) -> None:
    """Install staged deploy files to their expected locations in the container.

    The staging directory contains a "home/" subdirectory that mirrors the
    user's home directory structure. All files under "home/" are copied into
    the actual home directory, preserving their relative paths.
    """
    home_dir = staging_base / "home"
    if not home_dir.is_dir():
        return

    dest_home = Path.home()
    shutil.copytree(home_dir, dest_home, dirs_exist_ok=True)
