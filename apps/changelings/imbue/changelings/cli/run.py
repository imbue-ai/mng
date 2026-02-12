import shlex
import subprocess
import sys
from datetime import datetime
from datetime import timezone

import click
from loguru import logger

from imbue.changelings.config import get_changeling
from imbue.changelings.data_types import ChangelingDefinition
from imbue.changelings.primitives import ChangelingName
from imbue.changelings.templates import get_template


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
    if not local:
        raise NotImplementedError("Remote (Modal) execution is not yet implemented. Use --local for now.")

    changeling = get_changeling(ChangelingName(name))
    _run_local(changeling)


def _run_local(changeling: ChangelingDefinition) -> None:
    """Run a changeling locally by invoking mngr create."""
    cmd = build_mngr_create_command(changeling)
    logger.info("Running changeling '{}' locally", changeling.name)
    logger.debug("Command: {}", " ".join(cmd))

    result = subprocess.run(cmd)
    if result.returncode != 0:
        logger.error("Changeling '{}' exited with code {}", changeling.name, result.returncode)
        sys.exit(result.returncode)

    logger.info("Changeling '{}' completed successfully", changeling.name)


def build_mngr_create_command(changeling: ChangelingDefinition) -> list[str]:
    """Build the mngr create command for a changeling.

    Constructs the full argument list for invoking mngr create based on
    the changeling definition and its template defaults.
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
    ]

    # Determine the message to send: explicit message overrides template default
    message = _resolve_message(changeling)
    if message is not None:
        cmd.extend(["--message", message])

    # Pass environment variables
    for key, value in changeling.env_vars.items():
        cmd.extend(["--env", f"{key}={value}"])

    # Append any extra mngr args
    if changeling.extra_mngr_args:
        cmd.extend(shlex.split(changeling.extra_mngr_args))

    return cmd


def _resolve_message(changeling: ChangelingDefinition) -> str | None:
    """Resolve the message to send to the agent.

    Returns the changeling's explicit message if set, otherwise falls back
    to the template's default message.
    """
    if changeling.message is not None:
        return changeling.message

    template = get_template(changeling.template)
    if template is not None:
        return template.default_message

    return None
