import subprocess
import sys

import click
from loguru import logger

from imbue.changelings.config import get_changeling
from imbue.changelings.data_types import ChangelingDefinition
from imbue.changelings.mngr_commands import build_mngr_create_command
from imbue.changelings.mngr_commands import write_secrets_env_file
from imbue.changelings.primitives import ChangelingName


@click.command(name="run")
@click.argument("name")
@click.option(
    "--local",
    is_flag=True,
    help="Run locally instead of on Modal (useful for testing)",
)
def run(name: str, local: bool) -> None:
    """Run a changeling immediately (for testing or one-off execution).

    This bypasses the cron schedule and runs the changeling right now.
    Useful for testing a new changeling before deploying it.

    Examples:

      changeling run my-fairy

      changeling run my-fairy --local
    """
    changeling = get_changeling(ChangelingName(name))

    if local:
        _run_changeling_locally(changeling)
    else:
        _run_changeling_on_modal(changeling)


def _execute_mngr_command(changeling: ChangelingDefinition, cmd: list[str]) -> None:
    """Execute an mngr create command and handle the result."""
    logger.debug("Command: {}", " ".join(cmd))

    result = subprocess.run(cmd)
    if result.returncode != 0:
        logger.error("Changeling '{}' exited with code {}", changeling.name, result.returncode)
        sys.exit(result.returncode)

    logger.info("Changeling '{}' completed successfully", changeling.name)


def _run_changeling_locally(changeling: ChangelingDefinition) -> None:
    """Run a changeling locally by invoking mngr create."""
    logger.info("Running changeling '{}' locally", changeling.name)
    cmd = build_mngr_create_command(changeling, is_modal=False, env_file_path=None)
    _execute_mngr_command(changeling, cmd)


def _run_changeling_on_modal(changeling: ChangelingDefinition) -> None:
    """Run a changeling on Modal, writing secrets to a temporary env file."""
    logger.info("Running changeling '{}' on Modal", changeling.name)
    env_file_path = write_secrets_env_file(changeling)
    try:
        cmd = build_mngr_create_command(changeling, is_modal=True, env_file_path=env_file_path)
        _execute_mngr_command(changeling, cmd)
    finally:
        env_file_path.unlink(missing_ok=True)
