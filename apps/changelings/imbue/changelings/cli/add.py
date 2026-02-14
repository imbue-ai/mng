import click
from loguru import logger

from imbue.changelings.cli.options import build_definition_from_cli
from imbue.changelings.cli.options import changeling_definition_options
from imbue.changelings.config import add_changeling
from imbue.changelings.deploy.deploy import deploy_changeling
from imbue.changelings.errors import ChangelingAlreadyExistsError
from imbue.changelings.errors import ChangelingDeployError


@click.command(name="add")
@click.argument("name")
@changeling_definition_options
@click.option(
    "--finish-initial-run",
    is_flag=True,
    default=False,
    help="Wait for the verification agent to complete its initial run before returning (uses mngr stop instead of mngr destroy)",
)
def add(
    name: str,
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
    finish_initial_run: bool,
) -> None:
    """Register a new changeling and deploy it to Modal.

    A changeling is an autonomous agent that runs on a schedule to perform
    maintenance tasks on your codebase (fixing FIXMEs, improving tests, etc).

    This command saves the changeling definition to your local config and
    deploys a cron-scheduled Modal Function that will run the changeling
    on the specified schedule. After deployment, it invokes the function once
    to verify it works (creates an agent, then destroys it).

    Examples:

      changeling add my-fairy --agent-type fixme-fairy --repo git@github.com:org/repo.git --schedule "0 3 * * *"

      changeling add test-bot --agent-type test-troll --repo git@github.com:org/repo.git --schedule "0 4 * * 1"
    """
    definition = build_definition_from_cli(
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
        base=None,
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
        app_name = deploy_changeling(definition, is_finish_initial_run=finish_initial_run)
    except ChangelingDeployError as e:
        logger.error("Failed to deploy changeling '{}': {}", name, e)
        raise SystemExit(1) from None

    click.echo(f"Changeling '{name}' added and deployed to Modal app '{app_name}'")
