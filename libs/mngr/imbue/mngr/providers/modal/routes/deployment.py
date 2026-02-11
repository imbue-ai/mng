import os
from pathlib import Path

from modal import Function

from imbue.concurrency_group.concurrency_group import ConcurrencyGroup
from imbue.imbue_common.logging import log_span


def deploy_function(cg: ConcurrencyGroup, function: str, app_name: str, environment_name: str | None) -> str:
    """Deploys a Function to Modal with the given app name and returns the URL.
    Returns None if deployment fails.
    """
    script_path = Path(__file__).parent / f"{function}.py"

    with log_span("Deploying {} function for app: {}", function, app_name):
        result = cg.run_process_to_completion(
            [
                "uv",
                "run",
                "modal",
                "deploy",
                *(["--env", environment_name] if environment_name else []),
                str(script_path),
            ],
            timeout=180,
            is_checked_after=False,
            env={
                **os.environ,
                "MNGR_MODAL_APP_NAME": app_name,
            },
        )

        if result.returncode != 0:
            raise Exception("Failed to deploy {} function: {}", function, result.stderr)

        # get the URL out of the resulting Function object
        func = Function.from_name(name=function, app_name=app_name, environment_name=environment_name)
        web_url = func.get_web_url()
        if not web_url:
            raise Exception("Could not find function URL in deploy output: {}", result.stdout)

        return web_url
