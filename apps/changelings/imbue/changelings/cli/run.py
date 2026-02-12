import subprocess
import sys
from datetime import datetime
from datetime import timezone
from pathlib import Path

import click

from imbue.changelings.config import get_default_config_path
from imbue.changelings.config import load_config
from imbue.changelings.data_types import ChangelingDefinition
from imbue.changelings.errors import ChangelingConfigError
from imbue.changelings.primitives import ChangelingName
from imbue.changelings.templates import get_template_message
from imbue.imbue_common.pure import pure


@pure
def build_mngr_create_args(definition: ChangelingDefinition, timestamp: str) -> list[str]:
    """Build the argument list for `mngr create` from a changeling definition."""
    agent_name = f"changeling-{definition.name}-{timestamp}"
    branch_name = f"changeling/{definition.name}-{timestamp}"

    message = definition.message if definition.message is not None else get_template_message(definition.template)

    args = [
        "uv",
        "run",
        "mngr",
        "create",
        agent_name,
        definition.agent_type,
        "--worktree",
        "--base-branch",
        definition.branch,
        "--new-branch",
        branch_name,
        "--no-connect",
        "--await-agent-stopped",
        "--no-ensure-clean",
        "--message",
        message,
    ]

    if definition.extra_mngr_args:
        args.extend(definition.extra_mngr_args.split())

    for key, value in definition.env_vars.items():
        args.extend(["--env", f"{key}={value}"])

    return args


@click.command(name="run")
@click.argument("name")
@click.option(
    "--local",
    is_flag=True,
    help="Run locally instead of on Modal (useful for testing)",
)
@click.option(
    "--config-path",
    default=None,
    type=click.Path(),
    hidden=True,
    help="Path to config file (for testing)",
)
def run(name: str, local: bool, config_path: str | None) -> None:
    """Run a changeling immediately (for testing or one-off execution).

    This bypasses the cron schedule and runs the changeling right now.
    Useful for testing a new changeling before deploying it.

    Examples:

      changeling run my-fairy --local

      changeling run my-fairy
    """
    if not local:
        raise click.ClickException("Modal execution is not yet implemented. Use --local to run locally.")

    config_file = Path(config_path) if config_path else get_default_config_path()

    try:
        config = load_config(config_file)
    except ChangelingConfigError as e:
        raise click.ClickException(str(e))

    changeling_name = ChangelingName(name)
    if changeling_name not in config.changeling_by_name:
        raise click.ClickException(f"Changeling '{name}' not found.")

    definition = config.changeling_by_name[changeling_name]

    if not definition.is_enabled:
        click.echo(f"Warning: changeling '{name}' is disabled, but running it anyway.", err=True)

    timestamp = datetime.now(tz=timezone.utc).strftime("%Y%m%d-%H%M%S")
    args = build_mngr_create_args(definition, timestamp)

    click.echo(f"Running changeling '{name}' locally...")
    click.echo(f"Agent: changeling-{name}-{timestamp}")
    click.echo(f"Branch: changeling/{name}-{timestamp}")

    result = subprocess.run(args, check=False)

    if result.returncode != 0:
        click.echo(f"Changeling '{name}' failed with exit code {result.returncode}.", err=True)
        sys.exit(result.returncode)

    click.echo(f"Changeling '{name}' completed successfully.")
