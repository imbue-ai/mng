import click
from loguru import logger

from imbue.changelings.cli.options import build_definition_from_cli
from imbue.changelings.cli.options import changeling_definition_options
from imbue.changelings.config import get_changeling
from imbue.changelings.data_types import ChangelingDefinition
from imbue.changelings.errors import ChangelingNotFoundError
from imbue.changelings.errors import ChangelingRunError
from imbue.changelings.mngr_commands import build_mngr_create_command
from imbue.changelings.mngr_commands import write_secrets_env_file
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
def run(
    name: str,
    local: bool,
    schedule: str | None,
    repo: str | None,
    branch: str | None,
    message: str | None,
    agent_type: str | None,
    secrets: tuple[str, ...],
    env_vars: tuple[str, ...],
    extra_mngr_args: str | None,
    mngr_options: tuple[str, ...],
    enabled: bool | None,
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
        extra_mngr_args=extra_mngr_args,
        mngr_options=mngr_options,
        enabled=enabled,
        base=base,
    )

    if local:
        _run_changeling_locally(changeling)
    else:
        _run_changeling_on_modal(changeling)


def _execute_mngr_command(changeling: ChangelingDefinition, cmd: list[str]) -> None:
    """Execute an mngr create command via ConcurrencyGroup and handle the result."""
    logger.debug("Command: {}", " ".join(cmd))

    with ConcurrencyGroup(name=f"changeling-{changeling.name}") as cg:
        result = cg.run_process_to_completion(cmd, is_checked_after=False)

    if result.returncode != 0:
        raise ChangelingRunError(f"Changeling '{changeling.name}' exited with code {result.returncode}")

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
