import secrets
import shutil
from enum import auto
from pathlib import Path
from typing import Final

import click
from loguru import logger

from imbue.changelings.config.data_types import ChangelingPaths
from imbue.changelings.config.data_types import DEFAULT_FORWARDING_SERVER_PORT
from imbue.changelings.config.data_types import get_default_data_dir
from imbue.changelings.core.zygote import ZYGOTE_CONFIG_FILENAME
from imbue.changelings.core.zygote import ZygoteConfig
from imbue.changelings.core.zygote import load_zygote_config
from imbue.changelings.deployment.local import DeploymentResult
from imbue.changelings.deployment.local import clone_git_repo
from imbue.changelings.deployment.local import commit_files_in_repo
from imbue.changelings.deployment.local import deploy_local
from imbue.changelings.deployment.local import init_empty_git_repo
from imbue.changelings.errors import ChangelingError
from imbue.changelings.errors import GitCloneError
from imbue.changelings.errors import GitCommitError
from imbue.changelings.errors import GitInitError
from imbue.changelings.primitives import GitBranch
from imbue.changelings.primitives import GitUrl
from imbue.concurrency_group.concurrency_group import ConcurrencyGroup
from imbue.imbue_common.enums import UpperCaseStrEnum

_TEMP_DIR_ID_BYTES: int = 8

_MNG_SETTINGS_REL_PATH: Final[str] = ".mng/settings.toml"


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


def _print_result(result: DeploymentResult) -> None:
    """Print the deployment result and instruct the user to start the forwarding server."""
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
    logger.info("Start the forwarding server to access your changeling:")
    logger.info("  changeling forward")
    logger.info("=" * 60)


def _parse_add_path(raw: str) -> tuple[Path, Path]:
    """Parse a SRC:DEST string into (source_path, dest_path).

    Raises click.BadParameter if the format is invalid or if SRC does not exist.
    """
    if ":" not in raw:
        raise click.BadParameter(
            "Invalid --add-path format '{}'. Expected SRC:DEST".format(raw),
            param_hint="--add-path",
        )

    src_str, dest_str = raw.split(":", 1)
    if not src_str or not dest_str:
        raise click.BadParameter(
            "Invalid --add-path format '{}'. Both SRC and DEST must be non-empty".format(raw),
            param_hint="--add-path",
        )

    src = Path(src_str).resolve()
    if not src.exists():
        raise click.BadParameter(
            "Source path '{}' does not exist".format(src),
            param_hint="--add-path",
        )

    dest = Path(dest_str)
    if dest.is_absolute():
        raise click.BadParameter(
            "DEST path '{}' must be relative (it is relative to the repo root)".format(dest_str),
            param_hint="--add-path",
        )

    return src, dest


def _copy_add_paths(add_paths: tuple[tuple[Path, Path], ...], repo_dir: Path) -> int:
    """Copy files/directories specified by --add-path into the repo.

    Returns the number of paths that were copied.
    """
    copied = 0
    for src, dest in add_paths:
        target = repo_dir / dest
        target.parent.mkdir(parents=True, exist_ok=True)

        if src.is_dir():
            shutil.copytree(str(src), str(target), dirs_exist_ok=True)
        else:
            shutil.copy2(str(src), str(target))

        logger.debug("Copied {} -> {}", src, target)
        copied += 1

    return copied


def _write_changeling_toml(repo_dir: Path, agent_type: str) -> None:
    """Write a changeling.toml file with the given agent type.

    Only writes the file if it does not already exist.
    """
    config_path = repo_dir / ZYGOTE_CONFIG_FILENAME
    if config_path.exists():
        logger.debug("Changeling config already exists at {}, skipping creation", config_path)
        return

    config_path.write_text('[changeling]\nname = "{}"\nagent_type = "{}"\n'.format(agent_type, agent_type))
    logger.debug("Created {}", config_path)


def _write_mng_settings_toml(repo_dir: Path, agent_type: str) -> None:
    """Write .mng/settings.toml with a create template for the agent type.

    Only writes the file if it does not already exist.
    """
    settings_path = repo_dir / _MNG_SETTINGS_REL_PATH
    if settings_path.exists():
        logger.debug("Settings file already exists at {}, skipping creation", settings_path)
        return

    settings_path.parent.mkdir(parents=True, exist_ok=True)
    settings_path.write_text('[create_templates.entrypoint]\nagent_type = "{}"\n'.format(agent_type))
    logger.debug("Created {}", settings_path)


@click.command()
@click.argument("git_url", required=False, default=None)
@click.option(
    "--agent-type",
    default=None,
    help="Agent type to deploy (e.g. 'elena-code'). Alternative to providing a git URL.",
)
@click.option(
    "--add-path",
    multiple=True,
    help="Copy SRC:DEST into the repo (repeatable). SRC is a local path, DEST is relative to repo root.",
)
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
@click.option(
    "--data-dir",
    type=click.Path(resolve_path=True),
    default=None,
    help="Data directory for changelings state (default: ~/.changelings)",
)
def deploy(
    git_url: str | None,
    agent_type: str | None,
    add_path: tuple[str, ...],
    branch: str | None,
    name: str | None,
    provider: str | None,
    self_deploy: bool | None,
    data_dir: str | None,
) -> None:
    """Deploy a new changeling from a git repository or agent type.

    GIT_URL is an optional git URL to clone (local path, file://, https://, or ssh).
    Alternatively, use --agent-type to create a changeling without a git repository.

    Either GIT_URL or --agent-type must be provided.

    Example:

        changeling deploy ./my-agent-repo

        changeling deploy --agent-type elena-code

        changeling deploy --agent-type elena-code --add-path ./config:config --name my-agent

        changeling deploy git@github.com:user/my-agent.git --add-path ./extra:extra
    """
    if git_url is None and agent_type is None:
        raise click.UsageError("Either GIT_URL or --agent-type must be provided.")

    # Parse --add-path args upfront so we fail early on bad input
    parsed_add_paths = tuple(_parse_add_path(raw) for raw in add_path)

    data_directory = Path(data_dir) if data_dir else get_default_data_dir()
    paths = ChangelingPaths(data_dir=data_directory)

    paths.data_dir.mkdir(parents=True, exist_ok=True)
    temp_dir = paths.data_dir / (".tmp-" + secrets.token_hex(_TEMP_DIR_ID_BYTES))

    try:
        _prepare_repo(
            temp_dir=temp_dir,
            git_url=git_url,
            agent_type=agent_type,
            branch=branch,
            add_paths=parsed_add_paths,
        )
    except (click.ClickException, click.BadParameter):
        raise
    except ChangelingError as e:
        shutil.rmtree(temp_dir, ignore_errors=True)
        raise click.ClickException(str(e)) from e

    try:
        zygote_config = load_zygote_config(temp_dir)
    except ChangelingError as e:
        shutil.rmtree(temp_dir, ignore_errors=True)
        raise click.ClickException(str(e)) from e

    logger.info("Deploying changeling from: {}", temp_dir)
    if zygote_config.description:
        logger.info("  {}", zygote_config.description)

    # Determine agent name: --name flag, then agent_type default, then prompt
    if name is not None:
        agent_name = name
    elif agent_type is not None and git_url is None:
        agent_name = _prompt_agent_name(default_name=agent_type)
    else:
        agent_name = _prompt_agent_name(default_name=str(zygote_config.name))

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

    # Move repo to its permanent location: ~/.changelings/<agent-name>/
    changeling_dir = paths.changeling_dir(agent_name)
    if changeling_dir.exists():
        shutil.rmtree(temp_dir, ignore_errors=True)
        raise click.ClickException(
            "A changeling directory already exists at '{}'. Remove it first or choose a different name.".format(
                changeling_dir
            )
        )

    try:
        temp_dir.rename(changeling_dir)
    except OSError:
        shutil.move(str(temp_dir), str(changeling_dir))

    zygote_dir = changeling_dir

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

    _print_result(result)


def _prepare_repo(
    temp_dir: Path,
    git_url: str | None,
    agent_type: str | None,
    branch: str | None,
    add_paths: tuple[tuple[Path, Path], ...],
) -> None:
    """Prepare the temporary repo directory by cloning or initializing.

    When git_url is provided, clones the repository. Otherwise, creates an
    empty git repo and generates changeling.toml and .mng/settings.toml.

    In both cases, copies any --add-path files into the repo and commits
    if new files were added.
    """
    if git_url is not None:
        url = GitUrl(git_url)
        git_branch = GitBranch(branch) if branch is not None else None

        logger.info("Cloning repository: {}", url)
        try:
            clone_git_repo(url, temp_dir, branch=git_branch)
        except GitCloneError as e:
            shutil.rmtree(temp_dir, ignore_errors=True)
            raise click.ClickException(str(e)) from e
    else:
        assert agent_type is not None
        logger.info("Creating changeling repo for agent type: {}", agent_type)

        try:
            init_empty_git_repo(temp_dir)
        except GitInitError as e:
            shutil.rmtree(temp_dir, ignore_errors=True)
            raise click.ClickException(str(e)) from e

    # Copy --add-path files into the repo first, so that user-provided
    # files take precedence over auto-generated configs
    files_added = _copy_add_paths(add_paths, temp_dir)

    # Generate config files (only if they don't already exist, so --add-path
    # versions are preserved)
    if agent_type is not None:
        _write_changeling_toml(temp_dir, agent_type)
        _write_mng_settings_toml(temp_dir, agent_type)

    # Commit any new files that were added to the repo
    if git_url is None or files_added > 0 or agent_type is not None:
        try:
            commit_files_in_repo(temp_dir, "Initial changeling setup")
        except GitCommitError as e:
            shutil.rmtree(temp_dir, ignore_errors=True)
            raise click.ClickException(str(e)) from e
