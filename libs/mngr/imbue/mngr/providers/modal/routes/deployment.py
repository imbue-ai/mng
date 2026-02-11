import os
from pathlib import Path

from modal import Function

from imbue.concurrency_group.concurrency_group import ConcurrencyGroup
from imbue.concurrency_group.errors import ProcessError
from imbue.imbue_common.logging import log_span
from imbue.mngr.errors import MngrError


def deploy_function(function: str, app_name: str, environment_name: str | None, cg: ConcurrencyGroup) -> str:
    """Deploy a Function to Modal with the given app name and return the URL.

    Raises MngrError if deployment fails.
    """
    script_path = Path(__file__).parent / f"{function}.py"

    with log_span("Deploying {} function for app: {}", function, app_name):
        try:
            cg.run_process_to_completion(
                [
                    "uv",
                    "run",
                    "modal",
                    "deploy",
                    *(["--env", environment_name] if environment_name else []),
                    str(script_path),
                ],
                timeout=180,
                env={
                    **os.environ,
                    "MNGR_MODAL_APP_NAME": app_name,
                },
            )
        except ProcessError as e:
            output = (e.stdout + "\n" + e.stderr).strip()
            raise MngrError(f"Failed to deploy {function} function: {output}") from e

        # get the URL out of the resulting Function object
        func = Function.from_name(name=function, app_name=app_name, environment_name=environment_name)
        web_url = func.get_web_url()
        if not web_url:
            raise MngrError(f"Could not find function URL in deploy output for {function}")

        return web_url
