"""Utilities for deploying Modal functions."""

import os
import subprocess
from pathlib import Path

from loguru import logger
from modal.functions import Function


def deploy_snapshot_function(app_name: str, environment_name: str) -> str | None:
    """Deploy the snapshot_and_shutdown function and return its URL.

    Deploys to Modal with the given app name and returns the URL.
    Returns None if deployment fails.
    """
    script_path = Path(__file__).parent / "routes" / "snapshot_and_shutdown.py"

    logger.debug("Deploying snapshot_and_shutdown function for app: {}", app_name)
    try:
        result = subprocess.run(
            [
                "uv",
                "run",
                "modal",
                "deploy",
                "--env",
                environment_name,
                str(script_path),
            ],
            capture_output=True,
            text=True,
            timeout=180,
            env={
                **os.environ,
                "MNGR_MODAL_APP_NAME": app_name,
            },
        )

        if result.returncode != 0:
            logger.warning("Failed to deploy snapshot function: {}", result.stderr)
            return None

        # get the URL out of the resulting Function object
        func = Function.from_name(name="snapshot_and_shutdown", app_name=app_name, environment_name=environment_name)
        web_url = func.get_web_url()
        if web_url:
            return web_url

        logger.warning("Could not find function URL in deploy output: {}", result.stdout)
        return None

    except (subprocess.TimeoutExpired, FileNotFoundError, subprocess.SubprocessError) as e:
        logger.warning("Failed to deploy snapshot function: {}", e)
        return None
