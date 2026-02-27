import json
import secrets
import shutil
import tempfile
from pathlib import Path
from typing import Final

from loguru import logger
from pydantic import Field

from imbue.changelings.config.data_types import ChangelingPaths
from imbue.changelings.core.zygote import ZygoteConfig
from imbue.changelings.errors import ChangelingError
from imbue.changelings.forwarding_server.auth import FileAuthStore
from imbue.changelings.forwarding_server.backend_resolver import register_backend
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
    backend_url: str = Field(description="The backend URL where the changeling serves")
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


def deploy_local(
    zygote_dir: Path,
    zygote_config: ZygoteConfig,
    agent_name: str,
    paths: ChangelingPaths,
    forwarding_server_port: int,
    concurrency_group: ConcurrencyGroup,
) -> DeploymentResult:
    """Deploy a changeling locally by creating an mng agent and registering it.

    This function:
    1. Stages zygote files to a temp dir (to avoid git root detection)
    2. Creates an mng agent via `mng create --copy`
    3. Looks up the mng agent ID via `mng list`
    4. Registers the backend URL in the backends.json file
    5. Generates a one-time auth code for the forwarding server
    6. Returns the deployment result with the login URL
    """
    with log_span("Deploying changeling '{}' locally", agent_name):
        _verify_mng_available()

        backend_url = "http://127.0.0.1:{}".format(zygote_config.port)

        _create_mng_agent(
            zygote_dir=zygote_dir,
            agent_name=agent_name,
            command=str(zygote_config.command),
            port=zygote_config.port,
            concurrency_group=concurrency_group,
        )

        agent_id = _get_agent_id(
            agent_name=agent_name,
            concurrency_group=concurrency_group,
        )

        register_backend(
            backends_path=paths.backends_path,
            agent_id=agent_id,
            backend_url=backend_url,
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


def _create_mng_agent(
    zygote_dir: Path,
    agent_name: str,
    command: str,
    port: int,
    concurrency_group: ConcurrencyGroup,
) -> None:
    """Create an mng agent with a copy of the zygote directory as its work_dir.

    Copies the zygote to a temporary directory first so that mng does not detect
    a parent git repository and use the git root as the source.
    """
    with log_span("Creating mng agent '{}'", agent_name):
        staging_dir = Path(tempfile.mkdtemp(prefix="changeling-deploy-"))
        try:
            staged_zygote = staging_dir / "zygote"
            shutil.copytree(str(zygote_dir), str(staged_zygote))

            mng_command = [
                _MNG_BINARY,
                "create",
                "--name",
                agent_name,
                "--agent-cmd",
                command,
                "--no-connect",
                "--copy",
                "--env",
                "PORT={}".format(port),
            ]

            logger.debug("Running: {}", " ".join(mng_command))

            result = concurrency_group.run_process_to_completion(
                command=mng_command,
                cwd=staged_zygote,
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
        finally:
            shutil.rmtree(str(staging_dir), ignore_errors=True)


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
