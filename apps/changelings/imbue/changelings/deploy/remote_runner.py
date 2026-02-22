# Entry point for running a changeling inside the cloned imbue repo on Modal.
#
# This script is invoked by cron_runner.py after the imbue monorepo (containing
# changeling/mng tooling) has been cloned and dependencies installed via
# `uv sync --all-packages`. It uses the full imbue stack to deserialize the
# changeling config, write secrets, build the mng create command, and execute it.
#
# There are two repos involved:
#
#   1. The *imbue repo* (tooling) -- already cloned by cron_runner.py. Provides
#      the changeling and mng packages. This script runs from inside it.
#
#   2. The *target repo* (user's project) -- what the changeling operates on.
#      If a target_repo_path is provided (by cron_runner.py), mng runs from
#      that directory. If not provided, mng runs from the imbue repo cwd
#      (development mode where imbue IS the target).
#
# Usage:
#     uv run python -m imbue.changelings.deploy.remote_runner '<config_json>' [target_repo_path]

import sys
from pathlib import Path

from imbue.changelings.data_types import ChangelingDefinition
from imbue.changelings.deploy.deploy import build_cron_mng_command
from imbue.changelings.errors import ChangelingRunError
from imbue.changelings.mng_commands import secrets_env_file
from imbue.concurrency_group.concurrency_group import ConcurrencyGroup


def _log_output(line: str, is_stdout: bool) -> None:
    """Forward subprocess output to stdout/stderr."""
    stream = sys.stdout if is_stdout else sys.stderr
    stream.write(line)
    stream.flush()


def run(config_json: str, target_repo_path: str | None) -> None:
    """Deserialize the changeling config and run the mng create command.

    If target_repo_path is provided (already cloned by cron_runner.py onto
    the persistent volume), mng runs from that directory. Otherwise, mng
    runs from the current directory (the imbue repo clone -- development mode).
    """
    changeling = ChangelingDefinition.model_validate_json(config_json)

    if not changeling.is_enabled:
        print("Changeling is disabled, skipping")
        return

    target_cwd = Path(target_repo_path) if target_repo_path is not None else None

    with secrets_env_file(changeling) as env_file_path:
        cmd = build_cron_mng_command(changeling, env_file_path)
        with ConcurrencyGroup(name=f"cron-{changeling.name}") as cg:
            result = cg.run_process_to_completion(
                cmd,
                is_checked_after=False,
                cwd=target_cwd,
                on_output=_log_output,
            )

        if result.returncode != 0:
            output = (result.stdout + "\n" + result.stderr).strip()
            raise ChangelingRunError(
                f"Changeling '{changeling.name}' failed with exit code {result.returncode}:\n{output}"
            )


if __name__ == "__main__":
    if len(sys.argv) < 2 or len(sys.argv) > 3:
        print(
            "Usage: python -m imbue.changelings.deploy.remote_runner '<config_json>' [target_repo_path]",
            file=sys.stderr,
        )
        sys.exit(1)

    _config_json = sys.argv[1]
    _target_path = sys.argv[2] if len(sys.argv) == 3 else None
    run(_config_json, _target_path)
