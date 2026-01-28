import os
import subprocess
from pathlib import Path

from loguru import logger
from modal import Function


def deploy_function(function: str, app_name: str, environment_name: str | None) -> str | None:
    """Deploys a Function to Modal with the given app name and returns the URL.
    Returns None if deployment fails.
    """
    script_path = Path(__file__).parent / f"{function}.py"

    logger.debug("Deploying {} function for app: {}", function, app_name)
    try:
        result = subprocess.run(
            [
                "uv",
                "run",
                "modal",
                "deploy",
                *(["--env", environment_name] if environment_name else []),
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
            logger.warning("Failed to deploy {} function: {}", function, result.stderr)
            return None

        # get the URL out of the resulting Function object
        func = Function.from_name(name=function, app_name=app_name, environment_name=environment_name)
        web_url = func.get_web_url()
        if web_url:
            return web_url

        logger.warning("Could not find function URL in deploy output: {}", result.stdout)
        return None

    except (subprocess.TimeoutExpired, FileNotFoundError, subprocess.SubprocessError) as e:
        logger.warning("Failed to deploy {} function: {}", function, e)
        return None
