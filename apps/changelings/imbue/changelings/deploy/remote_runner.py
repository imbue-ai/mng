# Entry point for running a changeling inside the cloned imbue repo on Modal.
#
# This script is invoked by cron_runner.py after the imbue monorepo (containing
# changeling/mngr tooling) has been cloned and dependencies installed via
# `uv sync --all-packages`. It uses the full imbue stack to deserialize the
# changeling config, write secrets, build the mngr create command, and execute it.
#
# There are two repos involved:
#
#   1. The *imbue repo* (tooling) -- already cloned by cron_runner.py. Provides
#      the changeling and mngr packages. This script runs from inside it.
#
#   2. The *target repo* (user's project) -- what the changeling operates on.
#      If changeling.repo is set, this script clones it and runs mngr from
#      there. If not set, mngr runs from the imbue repo cwd (development mode
#      where imbue IS the target).
#
# Usage:
#     uv run python -m imbue.changelings.deploy.remote_runner '<config_json>'

import sys
from pathlib import Path

from loguru import logger

from imbue.changelings.data_types import ChangelingDefinition
from imbue.changelings.deploy.deploy import build_cron_mngr_command
from imbue.changelings.errors import ChangelingRunError
from imbue.changelings.mngr_commands import write_secrets_env_file
from imbue.concurrency_group.concurrency_group import ConcurrencyGroup

_TARGET_REPO_DIR = Path("/workspace/target")


def _log_output(line: str, is_stdout: bool) -> None:
    """Forward subprocess output to stdout/stderr."""
    stream = sys.stdout if is_stdout else sys.stderr
    stream.write(line)
    stream.flush()


def _clone_target_repo(repo_url: str, branch: str) -> Path:
    """Clone the target repo and checkout the specified branch."""
    logger.info("Cloning target repo from {} (branch: {})...", repo_url, branch)
    with ConcurrencyGroup(name="clone-target-repo") as cg:
        result = cg.run_process_to_completion(
            ["git", "clone", "--branch", branch, repo_url, str(_TARGET_REPO_DIR)],
            is_checked_after=False,
            on_output=_log_output,
        )
    if result.returncode != 0:
        output = (result.stdout + "\n" + result.stderr).strip()
        raise ChangelingRunError(f"Failed to clone target repo '{repo_url}':\n{output}")
    return _TARGET_REPO_DIR


def run(config_json: str) -> None:
    """Deserialize the changeling config and run the mngr create command.

    If the changeling has a target repo URL (changeling.repo), clones it and
    runs mngr from that directory. Otherwise, runs mngr from the current
    directory (the imbue repo clone -- development mode).
    """
    changeling = ChangelingDefinition.model_validate_json(config_json)

    if not changeling.is_enabled:
        print("Changeling is disabled, skipping")
        return

    # Determine where to run mngr from. If a target repo is specified, clone
    # it and run mngr from there. Otherwise, use the cwd (imbue repo clone).
    if changeling.repo is not None:
        target_cwd = _clone_target_repo(str(changeling.repo), changeling.branch)
    else:
        target_cwd = None

    env_file_path = write_secrets_env_file(changeling)
    try:
        cmd = build_cron_mngr_command(changeling, env_file_path)
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
