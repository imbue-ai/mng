import os
import shlex
import subprocess
import sys
import tempfile
from datetime import datetime
from datetime import timezone
from pathlib import Path

import click
from loguru import logger

from imbue.changelings.config import get_changeling
from imbue.changelings.data_types import ChangelingDefinition
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
    env_file_path = _write_secrets_env_file(changeling)
    try:
        cmd = build_mngr_create_command(changeling, is_modal=True, env_file_path=env_file_path)
        _execute_mngr_command(changeling, cmd)
    finally:
        env_file_path.unlink(missing_ok=True)


def _write_secrets_env_file(changeling: ChangelingDefinition) -> Path:
    """Write configured secrets from the local environment to a temporary env file.

    The caller is responsible for deleting the file when done.
    """
    fd, path_str = tempfile.mkstemp(prefix="changeling-env-", suffix=".env")
    env_file_path = Path(path_str)
    try:
        lines: list[str] = []
        for secret_name in changeling.secrets:
            value = os.environ.get(secret_name, "")
            if value:
                lines.append(f"{secret_name}={value}\n")
            else:
                logger.warning("Secret '{}' not found in environment, skipping", secret_name)
        os.write(fd, "".join(lines).encode())
    finally:
        os.close(fd)
    # Restrict permissions to owner-only
    env_file_path.chmod(0o600)
    return env_file_path


def build_mngr_create_command(
    changeling: ChangelingDefinition,
    is_modal: bool,
    env_file_path: Path | None,
) -> list[str]:
    """Build the mngr create command for a changeling.

    Constructs the full argument list for invoking mngr create based on
    the changeling definition. When is_modal is True, the command targets
    Modal as the host provider. Secrets are passed via env_file_path
    (a path to a file containing KEY=VALUE pairs).
    """
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d-%H-%M-%S")
    agent_name = f"{changeling.name}-{now_str}"
    branch_name = f"changelings/{changeling.name}-{now_str}"

    cmd = [
        sys.executable,
        "-m",
        "imbue.mngr.main",
        "create",
        agent_name,
        changeling.agent_type,
        "--no-connect",
        "--await-agent-stopped",
        "--no-ensure-clean",
        "--tag",
        "CREATOR=changeling",
        "--tag",
        f"CHANGELING={changeling.name}",
        "--base-branch",
        changeling.branch,
        "--new-branch",
        branch_name,
        "--message",
        changeling.initial_message,
    ]

    # When running on Modal, specify the provider and pass secrets via env file
    if is_modal:
        cmd.extend(["--in", "modal"])
        if env_file_path is not None:
            cmd.extend(["--host-env-file", str(env_file_path)])

    # Pass explicit environment variables
    for key, value in changeling.env_vars.items():
        cmd.extend(["--host-env", f"{key}={value}"])

    # Append any extra mngr args
    if changeling.extra_mngr_args:
        cmd.extend(shlex.split(changeling.extra_mngr_args))

    return cmd
