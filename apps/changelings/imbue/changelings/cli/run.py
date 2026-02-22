import sys
from typing import Any

import click
from loguru import logger

from imbue.changelings.cli.common_opts import add_common_options
from imbue.changelings.cli.common_opts import setup_command_context
from imbue.changelings.cli.options import build_definition_from_cli
from imbue.changelings.cli.options import changeling_definition_options
from imbue.changelings.config import get_changeling
from imbue.changelings.data_types import ChangelingDefinition
from imbue.changelings.errors import ChangelingNotFoundError
from imbue.changelings.errors import ChangelingRunError
from imbue.changelings.mng_commands import build_mng_create_command
from imbue.changelings.mng_commands import secrets_env_file
from imbue.changelings.primitives import ChangelingName
from imbue.concurrency_group.concurrency_group import ConcurrencyGroup


@click.command(name="run")
@click.argument("name")
@changeling_definition_options
@click.option(
    "--local",
    is_flag=True,
    help="Run locally instead of on Modal (useful for testing)",
)
@add_common_options
@click.pass_context
def run(
    ctx: click.Context,
    name: str,
    local: bool,
    schedule: str | None,
    repo: str | None,
    branch: str | None,
    message: str | None,
    agent_type: str | None,
    secrets: tuple[str, ...],
    env_vars: tuple[str, ...],
    extra_mng_args: str | None,
    mng_options: tuple[str, ...],
    enabled: bool | None,
    mng_profile: str | None,
    **_common: Any,
) -> None:
    """Run a changeling immediately (for testing or one-off execution).

    This bypasses the cron schedule and runs the changeling right now.
    If the changeling exists in config, its settings are used as defaults
    and any CLI options override them. If it does not exist in config,
    a definition is created from the CLI options.

    Examples:

      changeling run my-fairy --local

      changeling run my-test --local --agent-type code-guardian --message "Review the code"
    """
    setup_command_context(ctx, "run")

    # Try to load from config as a base; if not found, build from scratch
    try:
        base = get_changeling(ChangelingName(name))
    except ChangelingNotFoundError:
        base = None

    changeling = build_definition_from_cli(
        name=name,
        schedule=schedule,
        repo=repo,
        branch=branch,
        message=message,
        agent_type=agent_type,
        secrets=secrets,
        env_vars=env_vars,
        extra_mng_args=extra_mng_args,
        mng_options=mng_options,
        enabled=enabled,
        mng_profile=mng_profile,
        base=base,
    )

    if local:
        _run_changeling_locally(changeling)
    else:
        _run_changeling_on_modal(changeling)


def _forward_output(line: str, is_stdout: bool) -> None:
    """Forward subprocess output to the parent's stdout/stderr in real time."""
    stream = sys.stdout if is_stdout else sys.stderr
    stream.write(line)
    stream.flush()


def _execute_mng_command(changeling: ChangelingDefinition, cmd: list[str]) -> None:
    """Execute an mng create command and handle the result."""
    logger.debug("Command: {}", " ".join(cmd))

    with ConcurrencyGroup(name=f"changeling-{changeling.name}") as cg:
        result = cg.run_process_to_completion(
            cmd,
            is_checked_after=False,
            on_output=_forward_output,
        )

    if result.returncode != 0:
        output = (result.stdout + "\n" + result.stderr).strip()
        raise ChangelingRunError(f"Changeling '{changeling.name}' exited with code {result.returncode}:\n{output}")

    logger.info("Changeling '{}' completed successfully", changeling.name)


def _run_changeling_locally(changeling: ChangelingDefinition) -> None:
    """Run a changeling locally by invoking mng create."""
    logger.info("Running changeling '{}' locally", changeling.name)
    cmd = build_mng_create_command(changeling, is_modal=False, env_file_path=None)
    _execute_mng_command(changeling, cmd)


def _run_changeling_on_modal(changeling: ChangelingDefinition) -> None:
    """Run a changeling on Modal, writing secrets to a temporary env file."""
    logger.info("Running changeling '{}' on Modal", changeling.name)
    with secrets_env_file(changeling) as env_file_path:
        cmd = build_mng_create_command(changeling, is_modal=True, env_file_path=env_file_path)
        _execute_mng_command(changeling, cmd)
