import secrets
from enum import auto
from pathlib import Path

import click
from loguru import logger

from imbue.changelings.config.data_types import ChangelingPaths
from imbue.changelings.config.data_types import DEFAULT_FORWARDING_SERVER_PORT
from imbue.changelings.config.data_types import get_default_data_dir
from imbue.changelings.core.zygote import ZygoteConfig
from imbue.changelings.core.zygote import load_zygote_config
from imbue.changelings.deployment.local import DeploymentResult
from imbue.changelings.deployment.local import clone_git_repo
from imbue.changelings.deployment.local import deploy_local
from imbue.changelings.errors import ChangelingError
from imbue.changelings.errors import GitCloneError
from imbue.changelings.forwarding_server.runner import start_forwarding_server
from imbue.changelings.primitives import GitBranch
from imbue.changelings.primitives import GitUrl
from imbue.concurrency_group.concurrency_group import ConcurrencyGroup
from imbue.imbue_common.enums import UpperCaseStrEnum

_CLONE_ID_BYTES: int = 8


class DeploymentProvider(UpperCaseStrEnum):
    """Where the changeling can be deployed."""

    LOCAL = auto()
    MODAL = auto()
    DOCKER = auto()


class SelfDeployChoice(UpperCaseStrEnum):
    """Whether the changeling can launch its own agents."""

    YES = auto()
    NOT_NOW = auto()


def _prompt_agent_name(default_name: str) -> str:
    """Prompt the user for the agent name."""
    logger.info("")
    return click.prompt(
        "What would you like to name this agent?",
        default=default_name,
    )


def _prompt_provider() -> DeploymentProvider:
    """Prompt the user for where to deploy the agent."""
    logger.info("")
    logger.info("Where do you want to run this agent?")
    logger.info("  [1] local  - Run on this machine")
    logger.info("  [2] modal  - Run in the cloud (Modal)")
    logger.info("  [3] docker - Run in a Docker container")
    logger.info("")

    choice = click.prompt(
        "Selection",
        type=click.IntRange(1, 3),
        default=1,
    )

    match choice:
        case 1:
            return DeploymentProvider.LOCAL
        case 2:
            return DeploymentProvider.MODAL
        case 3:
            return DeploymentProvider.DOCKER
        case _:
            return DeploymentProvider.LOCAL


def _prompt_self_deploy() -> SelfDeployChoice:
    """Prompt the user about whether the agent can launch its own agents."""
    logger.info("")
    allow = click.confirm(
        "Allow this agent to launch its own agents?",
        default=False,
    )
    if allow:
        return SelfDeployChoice.YES
    else:
        return SelfDeployChoice.NOT_NOW


def _run_deployment(
    zygote_dir: Path,
    zygote_config: ZygoteConfig,
    agent_name: str,
    provider: DeploymentProvider,
    paths: ChangelingPaths,
) -> DeploymentResult:
    """Deploy the changeling and return the result.

    This creates the mng agent but does NOT start the forwarding server.
    Raises ChangelingError if deployment fails.
    """
    if provider != DeploymentProvider.LOCAL:
        raise ChangelingError(
            "Only local deployment is supported for now. Support for {} is coming soon.".format(provider.value.lower())
        )

    forwarding_port = DEFAULT_FORWARDING_SERVER_PORT

    cg = ConcurrencyGroup(name="changeling-deploy")
    deploy_error: ChangelingError | None = None
    with cg:
        try:
            result = deploy_local(
                zygote_dir=zygote_dir,
                zygote_config=zygote_config,
                agent_name=agent_name,
                paths=paths,
                forwarding_server_port=forwarding_port,
                concurrency_group=cg,
            )
        except ChangelingError as e:
            deploy_error = e

    if deploy_error is not None:
        raise deploy_error

    return result


def _print_result_and_start_server(result: DeploymentResult, paths: ChangelingPaths) -> None:
    """Print the deployment result and start the forwarding server (blocks until interrupted)."""
    logger.info("")
    logger.info("=" * 60)
    logger.info("Changeling deployed successfully")
    logger.info("=" * 60)
    logger.info("")
    logger.info("  Agent name: {}", result.agent_name)
    logger.info("  Agent ID:   {}", result.agent_id)
    if result.backend_url is not None:
        logger.info("  Backend:    {}", result.backend_url)
    logger.info("")
    logger.info("  Login URL (one-time use):")
    logger.info("  {}", result.login_url)
    logger.info("")
    logger.info("Starting the forwarding server...")
    logger.info("Press Ctrl+C to stop.")
    logger.info("=" * 60)
    logger.info("")

    start_forwarding_server(
        data_directory=paths.data_dir,
        host="127.0.0.1",
        port=DEFAULT_FORWARDING_SERVER_PORT,
    )


@click.command()
@click.argument("git_url")
@click.option(
    "--branch",
    default=None,
    help="Git branch to clone (defaults to the repository's default branch)",
)
@click.option(
    "--name",
    default=None,
    help="Name for the agent (skips the name prompt if provided)",
)
@click.option(
    "--provider",
    type=click.Choice(["local", "modal", "docker"], case_sensitive=False),
    default=None,
    help="Where to deploy the agent (skips the provider prompt if provided)",
)
@click.option(
    "--self-deploy/--no-self-deploy",
    default=None,
    help="Whether to allow the agent to launch its own agents (skips the prompt if provided)",
)
def deploy(
    git_url: str,
    branch: str | None,
    name: str | None,
    provider: str | None,
    self_deploy: bool | None,
) -> None:
    """Deploy a new changeling from a git repository.

    GIT_URL is a git URL to clone (local path, file://, https://, or ssh).
    The repository root must contain a changeling.toml file.

    Example:

        changeling deploy ./my-agent-repo

        changeling deploy git@github.com:user/my-agent.git --branch main

        changeling deploy https://github.com/user/my-agent.git --name my-agent --provider local
    """
    url = GitUrl(git_url)
    git_branch = GitBranch(branch) if branch is not None else None
    paths = ChangelingPaths(data_dir=get_default_data_dir())

    # Clone into a persistent directory under ~/.changelings/clones/
    clone_dir = paths.clones_dir / secrets.token_hex(_CLONE_ID_BYTES)
    clone_dir.parent.mkdir(parents=True, exist_ok=True)

    logger.info("Cloning repository: {}", url)

    try:
        clone_git_repo(url, clone_dir, branch=git_branch)
    except GitCloneError as e:
        raise click.ClickException(str(e)) from e

    zygote_dir = clone_dir

    try:
        zygote_config = load_zygote_config(zygote_dir)
    except ChangelingError as e:
        raise click.ClickException(str(e)) from e

    logger.info("Deploying changeling from: {}", zygote_dir)
    if zygote_config.description:
        logger.info("  {}", zygote_config.description)

    agent_name = name if name is not None else _prompt_agent_name(default_name=str(zygote_config.name))

    if provider is not None:
        provider_choice = DeploymentProvider(provider.upper())
    else:
        provider_choice = _prompt_provider()

    if self_deploy is not None:
        self_deploy_choice = SelfDeployChoice.YES if self_deploy else SelfDeployChoice.NOT_NOW
    else:
        self_deploy_choice = _prompt_self_deploy()

    if self_deploy_choice == SelfDeployChoice.YES:
        logger.debug("Self-deploy enabled (not yet implemented)")

    try:
        result = _run_deployment(
            zygote_dir=zygote_dir,
            zygote_config=zygote_config,
            agent_name=agent_name,
            provider=provider_choice,
            paths=paths,
        )
    except ChangelingError as e:
        raise click.ClickException(str(e)) from e

    _print_result_and_start_server(result, paths)
