# Entry point for running a changeling inside the cloned imbue repo on Modal.
#
# This script is invoked by cron_runner.py after the imbue monorepo (containing
# changeling/mngr tooling) has been cloned and dependencies installed via
# `uv sync --all-packages`. It uses the full imbue stack to deserialize the
# changeling config, write secrets, build the mngr create command, and execute it.
#
# The mngr create command is responsible for cloning and operating on the
# *target* repo (the user's project), which is distinct from the imbue repo.
#
# Usage:
#     uv run python -m imbue.changelings.deploy.remote_runner '<config_json>'

import sys

from imbue.changelings.data_types import ChangelingDefinition
from imbue.changelings.deploy.deploy import build_cron_mngr_command
from imbue.changelings.errors import ChangelingRunError
from imbue.changelings.mngr_commands import write_secrets_env_file
from imbue.concurrency_group.concurrency_group import ConcurrencyGroup


def _log_output(line: str, is_stdout: bool) -> None:
    """Forward subprocess output to stdout/stderr."""
    stream = sys.stdout if is_stdout else sys.stderr
    stream.write(line)
    stream.flush()


def run(config_json: str) -> None:
    """Deserialize the changeling config and run the mngr create command."""
    changeling = ChangelingDefinition.model_validate_json(config_json)

    if not changeling.is_enabled:
        print("Changeling is disabled, skipping")
        return

    env_file_path = write_secrets_env_file(changeling)
    try:
        cmd = build_cron_mngr_command(changeling, env_file_path)
        with ConcurrencyGroup(name=f"cron-{changeling.name}") as cg:
            result = cg.run_process_to_completion(
                cmd,
                is_checked_after=False,
                on_output=_log_output,
            )

        if result.returncode != 0:
            output = (result.stdout + "\n" + result.stderr).strip()
            raise ChangelingRunError(
                f"Changeling '{changeling.name}' failed with exit code {result.returncode}:\n{output}"
            )
    finally:
        env_file_path.unlink(missing_ok=True)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(
            "Usage: python -m imbue.changelings.deploy.remote_runner '<config_json>'",
            file=sys.stderr,
        )
        sys.exit(1)

    run(sys.argv[1])
