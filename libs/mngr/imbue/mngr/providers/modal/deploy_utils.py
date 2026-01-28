"""Utilities for deploying Modal functions."""

import os
import subprocess
from pathlib import Path

from loguru import logger


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

        # Parse the URL from the deploy output
        # Example formats:
        #   "Created web function snapshot_and_shutdown => https://..."
        lines = result.stdout.split("\n")
        for i, line in enumerate(lines):
            if "snapshot_and_shutdown" in line:
                # Check if URL is on this line
                if "https://" in line:
                    url_start = line.find("https://")
                    url = line[url_start:].split()[0].rstrip(")")
                    logger.info("Deployed snapshot_and_shutdown function: {}", url)
                    return url
                # Check if URL is on the next line
                if i + 1 < len(lines):
                    next_line = lines[i + 1]
                    if "https://" in next_line:
                        url_start = next_line.find("https://")
                        url = next_line[url_start:].split()[0].rstrip(")")
                        logger.info("Deployed snapshot_and_shutdown function: {}", url)
                        return url

        logger.warning("Could not find function URL in deploy output: {}", result.stdout)
        return None

    except (subprocess.TimeoutExpired, FileNotFoundError, subprocess.SubprocessError) as e:
        logger.warning("Failed to deploy snapshot function: {}", e)
        return None
