from pathlib import Path
from typing import Any
from uuid import uuid4

from imbue.mngr import hookimpl
from imbue.mngr.config.data_types import MngrContext
from imbue.mngr.interfaces.provider_backend import ProviderBackendInterface
from imbue.mngr.interfaces.provider_instance import ProviderInstanceInterface
from imbue.mngr.primitives import ProviderBackendName
from imbue.mngr.primitives import ProviderInstanceName
from imbue.mngr.providers.docker.instance import DockerProviderInstance

DOCKER_BACKEND_NAME = ProviderBackendName("docker")
USER_ID_FILENAME = "user_id"


def _get_or_create_user_id(mngr_ctx: MngrContext) -> str:
    """Get or create a unique user ID for this mngr installation.

    The user ID is stored in a file in the mngr data directory. This ID is used
    to namespace Docker containers, ensuring that containers created by different
    mngr installations don't interfere with each other.

    We use only 8 hex characters to keep container names reasonably short.
    """
    data_dir = mngr_ctx.config.default_host_dir.expanduser()
    data_dir.mkdir(parents=True, exist_ok=True)
    user_id_file = data_dir / USER_ID_FILENAME

    if user_id_file.exists():
        return user_id_file.read_text().strip()

    # Generate a new user ID (8 hex chars for ~4 billion unique values)
    user_id = uuid4().hex[:8]
    user_id_file.write_text(user_id)
    return user_id


class DockerProviderBackend(ProviderBackendInterface):
    """Backend for creating Docker container provider instances.

    The Docker provider backend creates provider instances that manage Docker
    containers as hosts. Each container runs sshd and is accessed via SSH/pyinfra.
    """

    @staticmethod
    def get_name() -> ProviderBackendName:
        return DOCKER_BACKEND_NAME

    @staticmethod
    def get_description() -> str:
        return "Runs agents in local Docker containers with SSH access"

    @staticmethod
    def get_build_args_help() -> str:
        return """\
Supported build arguments for the docker provider:
  --cpu COUNT   Number of CPU cores (e.g., 1.0, 2.0). Default: no limit
  --memory GB   Memory limit in GB (e.g., 1.0, 2.0). Default: no limit
  --image NAME  Base Docker image to use. Default: debian:bookworm-slim
"""

    @staticmethod
    def get_start_args_help() -> str:
        return "No start arguments are supported for the docker provider."

    @staticmethod
    def build_provider_instance(
        name: ProviderInstanceName,
        instance_configuration: dict[str, Any],
        mngr_ctx: MngrContext,
    ) -> ProviderInstanceInterface:
        """Build a Docker provider instance.

        The instance_configuration may contain:
        - container_prefix: Prefix for container names (defaults to "mngr-{user_id}-{name}")
        - host_dir: Base directory for mngr data on the container (defaults to /mngr)
        - default_cpu: Default CPU limit (defaults to None/no limit)
        - default_memory: Default memory limit in GB (defaults to None/no limit)
        """
        prefix = mngr_ctx.config.prefix
        user_id = _get_or_create_user_id(mngr_ctx)
        default_container_prefix = f"{prefix}{user_id}-{name}"
        container_prefix = instance_configuration.get("container_prefix", default_container_prefix)
        host_dir = Path(instance_configuration.get("host_dir", "/mngr"))
        default_cpu = instance_configuration.get("default_cpu", None)
        default_memory = instance_configuration.get("default_memory", None)

        return DockerProviderInstance(
            name=name,
            host_dir=host_dir,
            mngr_ctx=mngr_ctx,
            container_prefix=container_prefix,
            default_cpu=default_cpu,
            default_memory=default_memory,
        )


@hookimpl
def register_provider_backend() -> type[ProviderBackendInterface]:
    """Register the Docker provider backend."""
    return DockerProviderBackend
