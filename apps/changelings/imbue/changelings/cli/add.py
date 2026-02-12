from pathlib import Path

import click

from imbue.changelings.config import add_changeling
from imbue.changelings.config import get_default_config_path
from imbue.changelings.config import load_config
from imbue.changelings.config import save_config
from imbue.changelings.data_types import ChangelingDefinition
from imbue.changelings.errors import ChangelingAlreadyExistsError
from imbue.changelings.errors import ChangelingConfigError
from imbue.changelings.primitives import ChangelingName
from imbue.changelings.primitives import ChangelingTemplateName
from imbue.changelings.primitives import CronSchedule
from imbue.changelings.primitives import GitRepoUrl
from imbue.changelings.templates import is_known_template


@click.command(name="add")
@click.argument("name")
@click.option(
    "--template",
    required=True,
    help="Built-in template to use (e.g., fixme-fairy, test-troll, coverage-hunter)",
)
@click.option(
    "--repo",
    required=True,
    help="Git repository URL to operate on",
)
@click.option(
    "--schedule",
    required=True,
    help="Cron expression for when this changeling runs (e.g., '0 3 * * *' for 3am daily)",
)
@click.option(
    "--branch",
    default="main",
    help="Base branch to work from [default: main]",
)
@click.option(
    "--message",
    default=None,
    help="Custom initial message to send to the agent (overrides template default)",
)
@click.option(
    "--agent-type",
    default="claude",
    help="The mngr agent type to use [default: claude]",
)
@click.option(
    "--enabled/--disabled",
    default=True,
    help="Whether this changeling should be active immediately [default: enabled]",
)
@click.option(
    "--config-path",
    default=None,
    type=click.Path(),
    hidden=True,
    help="Path to config file (for testing)",
)
def add(
    name: str,
    template: str,
    repo: str,
    schedule: str,
    branch: str,
    message: str | None,
    agent_type: str,
    enabled: bool,
    config_path: str | None,
) -> None:
    """Register a new changeling.

    A changeling is an autonomous agent that runs on a schedule to perform
    maintenance tasks on your codebase (fixing FIXMEs, improving tests, etc).

    Examples:

      changeling add my-fairy --template fixme-fairy --repo git@github.com:org/repo.git --schedule "0 3 * * *"

      changeling add test-bot --template test-troll --repo git@github.com:org/repo.git --schedule "0 4 * * 1"
    """
    config_file = Path(config_path) if config_path else get_default_config_path()

    template_name = ChangelingTemplateName(template)
    if not is_known_template(template_name):
        click.echo(f"Warning: '{template}' is not a known built-in template.", err=True)

    definition = ChangelingDefinition(
        name=ChangelingName(name),
        template=template_name,
        schedule=CronSchedule(schedule),
        repo=GitRepoUrl(repo),
        branch=branch,
        message=message,
        agent_type=agent_type,
        is_enabled=enabled,
    )

    try:
        config = load_config(config_file)
        config = add_changeling(config, definition)
        save_config(config, config_file)
    except ChangelingAlreadyExistsError:
        raise click.ClickException(f"Changeling '{name}' already exists. Use 'changeling update' to modify it.")
    except ChangelingConfigError as e:
        raise click.ClickException(str(e))

    click.echo(f"Registered changeling '{name}' (template: {template}, schedule: {schedule})")
