import click
from loguru import logger

from imbue.changelings.cli.options import build_definition_from_cli
from imbue.changelings.cli.options import changeling_definition_options
from imbue.changelings.config import add_changeling
from imbue.changelings.config import upsert_changeling
from imbue.changelings.deploy.deploy import deploy_changeling
from imbue.changelings.deploy.deploy import list_mngr_profiles
from imbue.changelings.errors import ChangelingAlreadyExistsError
from imbue.changelings.errors import ChangelingDeployError


def _resolve_mngr_profile(explicit_profile: str | None) -> str:
    """Resolve the mngr profile to use for deployment.

    If an explicit profile is provided, returns it. Otherwise auto-detects
    from ~/.mngr/profiles/: if exactly one profile exists, uses it; if
    multiple exist, prompts the user to choose.
    """
    if explicit_profile is not None:
        return explicit_profile

    profiles = list_mngr_profiles()
    if len(profiles) == 0:
        logger.error("No mngr profiles found. Run 'mngr create' first to set up a profile.")
        raise SystemExit(1)
    elif len(profiles) == 1:
        profile_id = profiles[0]
        logger.info("Auto-selected mngr profile: {}", profile_id)
        return profile_id
    else:
        click.echo("Multiple mngr profiles found:")
        for i, p in enumerate(profiles, 1):
            click.echo(f"  {i}. {p}")
        choice = click.prompt(
            "Select a profile",
            type=click.IntRange(1, len(profiles)),
        )
        return profiles[choice - 1]


@click.command(name="add")
@click.argument("name")
@changeling_definition_options
@click.option(
    "--update",
    is_flag=True,
    default=False,
    help="Update the changeling if it already exists (idempotent create/update)",
)
@click.option(
    "--finish-initial-run",
    is_flag=True,
    default=False,
    help="Keep the verification agent running after deployment succeeds instead of destroying it",
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
    mngr_profile: str | None,
    update: bool,
    finish_initial_run: bool,
) -> None:
    """Register a new changeling and deploy it to Modal.

    A changeling is an autonomous agent that runs on a schedule to perform
    maintenance tasks on your codebase (fixing FIXMEs, improving tests, etc).

    This command saves the changeling definition to your local config and
    deploys a cron-scheduled Modal Function that will run the changeling
    on the specified schedule. After deployment, it invokes the function once
    to verify it works (creates an agent, then destroys it).

    Use --update to idempotently create or update a changeling.

    Examples:

      changeling add my-fairy --agent-type fixme-fairy --schedule "0 3 * * *"

      changeling add --update my-fairy --agent-type fixme-fairy --schedule "0 3 * * *"
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
        mngr_profile=mngr_profile,
        base=None,
    )

    # Save the definition to config first (so it persists even if deploy fails)
    if update:
        upsert_changeling(definition)
    else:
        try:
            add_changeling(definition)
        except ChangelingAlreadyExistsError:
            logger.error("Changeling '{}' already exists. Use --update to modify it.", name)
            raise SystemExit(1) from None

    if not definition.is_enabled:
        click.echo(f"Changeling '{name}' saved to config (disabled, not deployed to Modal)")
        return

    # Resolve the mngr profile (auto-detect or prompt) for deployment.
    # Re-save the definition with the resolved profile so it persists.
    resolved_profile = _resolve_mngr_profile(definition.mngr_profile)
    definition = definition.model_copy(update={"mngr_profile": resolved_profile})
    upsert_changeling(definition)

    try:
        app_name = deploy_changeling(definition, is_finish_initial_run=finish_initial_run)
    except ChangelingDeployError as e:
        logger.error("Failed to deploy changeling '{}': {}", name, e)
        raise SystemExit(1) from None

    click.echo(f"Changeling '{name}' deployed to Modal app '{app_name}'")
