import click
from loguru import logger

from imbue.changelings.config import add_changeling
from imbue.changelings.data_types import ChangelingDefinition
from imbue.changelings.data_types import DEFAULT_INITIAL_MESSAGE
from imbue.changelings.deploy.deploy import deploy_changeling
from imbue.changelings.errors import ChangelingAlreadyExistsError
from imbue.changelings.errors import ChangelingDeployError
from imbue.changelings.primitives import ChangelingName
from imbue.changelings.primitives import ChangelingTemplateName
from imbue.changelings.primitives import CronSchedule
from imbue.changelings.primitives import GitRepoUrl


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
def add(
    name: str,
    template: str,
    repo: str,
    schedule: str,
    branch: str,
    message: str | None,
    agent_type: str,
    enabled: bool,
) -> None:
    """Register a new changeling and deploy it to Modal.

    A changeling is an autonomous agent that runs on a schedule to perform
    maintenance tasks on your codebase (fixing FIXMEs, improving tests, etc).

    This command saves the changeling definition to your local config and
    deploys a cron-scheduled Modal Function that will run the changeling
    on the specified schedule.

    Examples:

      changeling add my-fairy --template fixme-fairy --repo git@github.com:org/repo.git --schedule "0 3 * * *"

      changeling add test-bot --template test-troll --repo git@github.com:org/repo.git --schedule "0 4 * * 1"
    """
    definition = ChangelingDefinition(
        name=ChangelingName(name),
        template=ChangelingTemplateName(template),
        repo=GitRepoUrl(repo),
        schedule=CronSchedule(schedule),
        branch=branch,
        initial_message=message or DEFAULT_INITIAL_MESSAGE,
        agent_type=agent_type,
        is_enabled=enabled,
    )

    try:
        add_changeling(definition)
    except ChangelingAlreadyExistsError:
        logger.error("Changeling '{}' already exists. Use 'changeling update' to modify it.", name)
        raise SystemExit(1) from None

    if not definition.is_enabled:
        click.echo(f"Changeling '{name}' added to config (disabled, not deployed to Modal)")
        return

    try:
        app_name = deploy_changeling(definition)
    except ChangelingDeployError as e:
        logger.error("Failed to deploy changeling '{}': {}", name, e)
        raise SystemExit(1) from None

    click.echo(f"Changeling '{name}' added and deployed to Modal app '{app_name}'")
