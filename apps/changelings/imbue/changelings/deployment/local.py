import json
import secrets
import shutil
import subprocess
from pathlib import Path
from typing import Final

from loguru import logger
from pydantic import Field

from imbue.changelings.config.data_types import ChangelingPaths
from imbue.changelings.core.zygote import ZygoteConfig
from imbue.changelings.errors import AgentAlreadyExistsError
from imbue.changelings.errors import ChangelingError
from imbue.changelings.errors import GitCloneError
from imbue.changelings.errors import GitCommitError
from imbue.changelings.errors import GitInitError
from imbue.changelings.forwarding_server.auth import FileAuthStore
from imbue.changelings.primitives import GitBranch
from imbue.changelings.primitives import GitUrl
from imbue.changelings.primitives import OneTimeCode
from imbue.concurrency_group.concurrency_group import ConcurrencyGroup
from imbue.imbue_common.frozen_model import FrozenModel
from imbue.imbue_common.logging import log_span
from imbue.mng.primitives import AgentId

_MNG_BINARY: Final[str] = "mng"

_ONE_TIME_CODE_LENGTH: Final[int] = 32


class DeploymentResult(FrozenModel):
    """Result of a successful local changeling deployment."""

    agent_name: str = Field(description="The name of the deployed agent")
    agent_id: AgentId = Field(description="The mng agent ID (used for forwarding server routing)")
    backend_url: str | None = Field(
        description="The backend URL where the changeling serves, or None for agent-type-managed servers"
    )
    login_url: str = Field(description="One-time login URL for accessing the changeling")


class MngNotFoundError(ChangelingError):
    """Raised when the mng binary cannot be found on PATH."""

    ...


class MngCreateError(ChangelingError):
    """Raised when mng create fails."""

    ...


class AgentIdLookupError(ChangelingError):
    """Raised when the mng agent ID cannot be determined after creation."""

    ...


def clone_git_repo(git_url: GitUrl, clone_dir: Path, branch: GitBranch | None = None) -> None:
    """Clone a git repository into the specified directory.

    The clone_dir must not already exist -- git clone will create it.
    The caller is responsible for choosing a suitable location (e.g.
    under ~/.changelings/clones/).

    If branch is specified, only that branch is cloned (via git clone -b).

    Raises GitCloneError if the clone fails.
    """
    logger.debug("Cloning {} to {}", git_url, clone_dir)

    command = ["git", "clone"]
    if branch is not None:
        command.extend(["-b", str(branch)])
    command.extend([str(git_url), str(clone_dir)])

    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        raise GitCloneError(
            "git clone failed (exit code {}):\n{}".format(
                result.returncode,
                result.stderr.strip() if result.stderr.strip() else result.stdout.strip(),
            )
        )

    logger.debug("Cloned repository to {}", clone_dir)


def init_empty_git_repo(repo_dir: Path) -> None:
    """Initialize an empty git repository at the given path.

    Creates the directory if it does not exist. Raises GitInitError if git init fails.
    """
    repo_dir.mkdir(parents=True, exist_ok=True)
    logger.debug("Initializing empty git repo at {}", repo_dir)

    result = subprocess.run(
        ["git", "init"],
        cwd=repo_dir,
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        raise GitInitError(
            "git init failed (exit code {}):\n{}".format(
                result.returncode,
                result.stderr.strip() if result.stderr.strip() else result.stdout.strip(),
            )
        )

    logger.debug("Initialized empty git repo at {}", repo_dir)


def commit_files_in_repo(repo_dir: Path, message: str) -> bool:
    """Stage all files and commit in the given git repo.

    Uses a default author/committer identity so that commits succeed even
    in environments without a global git config (e.g. CI runners).

    Returns True if a commit was created, False if there was nothing to commit.
    Raises GitCommitError if the git operations fail unexpectedly.
    """
    add_result = subprocess.run(
        ["git", "add", "."],
        cwd=repo_dir,
        capture_output=True,
        text=True,
    )

    if add_result.returncode != 0:
        raise GitCommitError(
            "git add failed (exit code {}):\n{}".format(
                add_result.returncode,
                add_result.stderr.strip() if add_result.stderr.strip() else add_result.stdout.strip(),
            )
        )

    # Check if there is anything to commit
    status_result = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=repo_dir,
        capture_output=True,
        text=True,
    )

    if not status_result.stdout.strip():
        logger.debug("No changes to commit in {}", repo_dir)
        return False

    commit_result = subprocess.run(
        [
            "git",
            "-c",
            "user.name=changeling",
            "-c",
            "user.email=changeling@localhost",
            "commit",
            "-m",
            message,
        ],
        cwd=repo_dir,
        capture_output=True,
        text=True,
    )

    if commit_result.returncode != 0:
        raise GitCommitError(
            "git commit failed (exit code {}):\n{}".format(
                commit_result.returncode,
                commit_result.stderr.strip() if commit_result.stderr.strip() else commit_result.stdout.strip(),
            )
        )

    logger.debug("Committed files in {}: {}", repo_dir, message)
    return True


def deploy_local(
    zygote_dir: Path,
    zygote_config: ZygoteConfig,
    agent_name: str,
    paths: ChangelingPaths,
    forwarding_server_port: int,
    concurrency_group: ConcurrencyGroup,
) -> DeploymentResult:
    """Deploy a changeling locally by creating an mng agent.

    The zygote_dir is the changeling's own repo directory (e.g.
    ~/.changelings/<name>/). The agent is created via `mng create --in-place`
    so it runs directly in this directory.

    Changelings with an agent_type use the "entrypoint" create template
    (from .mng/settings.toml) to determine the agent type. Custom-command
    changelings pass their command and port directly.

    This function:
    1. Verifies mng is available and no agent with this name exists
    2. Creates an mng agent via `mng create --in-place -t entrypoint`
    3. Looks up the mng agent ID via `mng list`
    4. Generates a one-time auth code for the forwarding server
    5. Returns the deployment result with the login URL

    The agent itself is responsible for writing its server info to
    $MNG_AGENT_STATE_DIR/logs/servers.jsonl on startup, which the forwarding
    server reads to discover backends.
    """
    with log_span("Deploying changeling '{}' locally", agent_name):
        _verify_mng_available()

        _check_agent_not_exists(
            agent_name=agent_name,
            concurrency_group=concurrency_group,
        )

        if zygote_config.agent_type is not None:
            backend_url = None
        else:
            backend_url = "http://127.0.0.1:{}".format(zygote_config.port)

        _create_mng_agent(
            zygote_dir=zygote_dir,
            agent_name=agent_name,
            zygote_config=zygote_config,
            concurrency_group=concurrency_group,
        )

        agent_id = _get_agent_id(
            agent_name=agent_name,
            concurrency_group=concurrency_group,
        )

        login_url = _generate_auth_code(
            paths=paths,
            agent_id=agent_id,
            forwarding_server_port=forwarding_server_port,
        )

        return DeploymentResult(
            agent_name=agent_name,
            agent_id=agent_id,
            backend_url=backend_url,
            login_url=login_url,
        )


def _verify_mng_available() -> None:
    """Verify that the mng binary is available on PATH."""
    if shutil.which(_MNG_BINARY) is None:
        raise MngNotFoundError("The 'mng' command was not found on PATH. Install mng first: uv tool install mng")


def _check_agent_not_exists(
    agent_name: str,
    concurrency_group: ConcurrencyGroup,
) -> None:
    """Check that no agent with this name already exists.

    Raises AgentAlreadyExistsError if an agent with the given name is found.
    """
    result = concurrency_group.run_process_to_completion(
        command=[
            _MNG_BINARY,
            "list",
            "--include",
            'name == "{}"'.format(agent_name),
            "--json",
        ],
        is_checked_after=False,
    )

    if result.returncode != 0:
        logger.warning("Agent existence check failed (exit code {}), proceeding without check", result.returncode)
        return

    _raise_if_agent_exists(agent_name, result.stdout)


def _raise_if_agent_exists(agent_name: str, mng_list_output: str) -> None:
    """Parse mng list JSON output and raise if an agent with the given name exists.

    Silently returns if the output cannot be parsed as JSON (defensive -- the caller
    already verified the subprocess succeeded).
    """
    try:
        data = json.loads(mng_list_output)
    except json.JSONDecodeError:
        logger.warning("Failed to parse mng list output for existence check, proceeding without check")
        return

    agents = data.get("agents", [])
    if agents:
        raise AgentAlreadyExistsError(
            "An agent named '{}' already exists. "
            "Use 'changeling update' to update it, or 'changeling destroy' to remove it.".format(agent_name)
        )


def _create_mng_agent(
    zygote_dir: Path,
    agent_name: str,
    zygote_config: ZygoteConfig,
    concurrency_group: ConcurrencyGroup,
) -> None:
    """Create an mng agent from the changeling's own repo directory.

    Runs mng create --in-place from the zygote directory so the agent runs
    directly in the changeling's repo (e.g. ~/.changelings/<name>/).

    Changelings are expected to have a .mng/settings.toml file with an
    "entrypoint" create template that specifies the agent type. This template
    is applied via -t entrypoint.

    For custom-command changelings (no agent_type), the command and port from
    the changeling.toml config are passed directly via --agent-cmd and --env.
    """
    with log_span("Creating mng agent '{}'", agent_name):
        mng_command = [
            _MNG_BINARY,
            "create",
            "--name",
            agent_name,
            "--no-connect",
            "--in-place",
        ]

        if zygote_config.agent_type is not None:
            mng_command.extend(["-t", "entrypoint"])
        else:
            mng_command.extend(["--agent-cmd", str(zygote_config.command)])
            mng_command.extend(["--env", "PORT={}".format(zygote_config.port)])

        logger.debug("Running: {}", " ".join(mng_command))

        result = concurrency_group.run_process_to_completion(
            command=mng_command,
            cwd=zygote_dir,
            is_checked_after=False,
        )

        if result.returncode != 0:
            raise MngCreateError(
                "mng create failed (exit code {}):\n{}".format(
                    result.returncode,
                    result.stderr.strip() if result.stderr.strip() else result.stdout.strip(),
                )
            )

        logger.debug("mng create output: {}", result.stdout.strip())


def _get_agent_id(
    agent_name: str,
    concurrency_group: ConcurrencyGroup,
) -> AgentId:
    """Look up the mng agent ID by name using `mng list --json`."""
    with log_span("Looking up agent ID for '{}'", agent_name):
        result = concurrency_group.run_process_to_completion(
            command=[
                _MNG_BINARY,
                "list",
                "--include",
                'name == "{}"'.format(agent_name),
                "--json",
            ],
            is_checked_after=False,
        )

        if result.returncode != 0:
            raise AgentIdLookupError(
                "Failed to look up agent ID for '{}': {}".format(
                    agent_name,
                    result.stderr.strip() if result.stderr.strip() else result.stdout.strip(),
                )
            )

        try:
            data = json.loads(result.stdout)
        except json.JSONDecodeError as e:
            raise AgentIdLookupError("Failed to parse mng list output: {}".format(e)) from e

        agents = data.get("agents", [])
        if not agents:
            raise AgentIdLookupError("No agent found with name '{}'".format(agent_name))

        return AgentId(agents[0]["id"])


def _generate_auth_code(
    paths: ChangelingPaths,
    agent_id: AgentId,
    forwarding_server_port: int,
) -> str:
    """Generate a one-time auth code and return the login URL."""
    auth_store = FileAuthStore(data_directory=paths.auth_dir)
    code = OneTimeCode(secrets.token_urlsafe(_ONE_TIME_CODE_LENGTH))
    auth_store.add_one_time_code(agent_id=agent_id, code=code)

    return "http://127.0.0.1:{}/login?agent_id={}&one_time_code={}".format(
        forwarding_server_port,
        agent_id,
        code,
    )
