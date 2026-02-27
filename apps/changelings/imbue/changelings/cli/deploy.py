import shutil
import sys
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
from imbue.changelings.primitives import GitUrl
from imbue.changelings.primitives import RepoSubPath
from imbue.concurrency_group.concurrency_group import ConcurrencyGroup
from imbue.imbue_common.enums import UpperCaseStrEnum


class DeploymentProvider(UpperCaseStrEnum):
    """Where the changeling can be deployed."""

    LOCAL = auto()
    MODAL = auto()
    DOCKER = auto()


class SelfDeployChoice(UpperCaseStrEnum):
    """Whether the changeling can launch its own agents."""

    YES = auto()
    NOT_NOW = auto()


def _write_line(message: str) -> None:
    """Write a line to stdout."""
    sys.stdout.write(message + "\n")
    sys.stdout.flush()


def _prompt_agent_name(default_name: str) -> str:
    """Prompt the user for the agent name."""
    _write_line("")
    return click.prompt(
        "What would you like to name this agent?",
        default=default_name,
    )


def _prompt_provider() -> DeploymentProvider:
    """Prompt the user for where to deploy the agent."""
    _write_line("")
    _write_line("Where do you want to run this agent?")
    _write_line("  [1] local  - Run on this machine")
    _write_line("  [2] modal  - Run in the cloud (Modal)")
    _write_line("  [3] docker - Run in a Docker container")
    _write_line("")

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
    _write_line("")
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
) -> DeploymentResult:
    """Deploy the changeling and return the result.

    This creates the mng agent but does NOT start the forwarding server.
    Raises ChangelingError if deployment fails.
    """
    if provider != DeploymentProvider.LOCAL:
        raise ChangelingError(
            "Only local deployment is supported for now. Support for {} is coming soon.".format(provider.value.lower())
        )

    paths = ChangelingPaths(data_dir=get_default_data_dir())
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


def _print_result_and_start_server(result: DeploymentResult) -> None:
    """Print the deployment result and start the forwarding server (blocks until interrupted)."""
    _write_line("")
    _write_line("=" * 60)
    _write_line("Changeling deployed successfully")
    _write_line("=" * 60)
    _write_line("")
    _write_line("  Agent name: {}".format(result.agent_name))
    _write_line("  Agent ID:   {}".format(result.agent_id))
    if result.backend_url is not None:
        _write_line("  Backend:    {}".format(result.backend_url))
    _write_line("")
    _write_line("  Login URL (one-time use):")
    _write_line("  {}".format(result.login_url))
    _write_line("")
    _write_line("Starting the forwarding server...")
    _write_line("Press Ctrl+C to stop.")
    _write_line("=" * 60)
    _write_line("")

    paths = ChangelingPaths(data_dir=get_default_data_dir())
    start_forwarding_server(
        data_directory=paths.data_dir,
        host="127.0.0.1",
        port=DEFAULT_FORWARDING_SERVER_PORT,
    )


@click.command()
@click.argument("git_url")
@click.option(
    "--repo-sub-path",
    default=None,
    help="Subdirectory within the cloned repo containing the changeling.toml",
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
    repo_sub_path: str | None,
    name: str | None,
    provider: str | None,
    self_deploy: bool | None,
) -> None:
    """Deploy a new changeling from a git repository.

    GIT_URL is a git URL to clone (local path, file://, https://, or ssh).

    Example:

        changeling deploy ./my-repo --repo-sub-path examples/hello-world

        changeling deploy git@github.com:user/agents.git --repo-sub-path elena-code

        changeling deploy https://github.com/user/my-agent.git --name my-agent --provider local
    """
    url = GitUrl(git_url)
    sub_path = RepoSubPath(repo_sub_path) if repo_sub_path is not None else None

    _write_line("Cloning repository: {}".format(url))

    try:
        clone_result = clone_git_repo(url)
    except GitCloneError as e:
        raise click.ClickException(str(e)) from e

    clone_dir = clone_result.clone_dir
    deploy_succeeded = False
    try:
        zygote_dir = clone_dir / str(sub_path) if sub_path is not None else clone_dir

        if not zygote_dir.is_dir():
            raise click.ClickException("Subdirectory '{}' not found in cloned repository".format(sub_path))

        try:
            zygote_config = load_zygote_config(zygote_dir)
        except ChangelingError as e:
            raise click.ClickException(str(e)) from e

        _write_line("Deploying changeling from: {}".format(zygote_dir))
        if zygote_config.description:
            _write_line("  {}".format(zygote_config.description))

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
            )
        except ChangelingError as e:
            raise click.ClickException(str(e)) from e

        deploy_succeeded = True
    finally:
        if not deploy_succeeded:
            shutil.rmtree(str(clone_result.cleanup_dir), ignore_errors=True)

    _print_result_and_start_server(result)
