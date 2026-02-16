from pathlib import Path
from typing import Final

from imbue.mngr import hookimpl
from imbue.mngr.config.data_types import MngrContext
from imbue.mngr.config.data_types import ProviderInstanceConfig
from imbue.mngr.errors import MngrError
from imbue.mngr.interfaces.provider_backend import ProviderBackendInterface
from imbue.mngr.interfaces.provider_instance import ProviderInstanceInterface
from imbue.mngr.primitives import ProviderBackendName
from imbue.mngr.primitives import ProviderInstanceName
from imbue.mngr.providers.docker.config import DockerProviderConfig
from imbue.mngr.providers.docker.instance import DockerProviderInstance

DOCKER_BACKEND_NAME: Final[ProviderBackendName] = ProviderBackendName("docker")


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
        return "Runs agents in Docker containers with SSH access"

    @staticmethod
    def get_config_class() -> type[ProviderInstanceConfig]:
        return DockerProviderConfig

    @staticmethod
    def get_build_args_help() -> str:
        return "Build args are passed directly to 'docker build'. Run 'docker build --help' for details."

    @staticmethod
    def get_start_args_help() -> str:
        return "Start args are passed directly to 'docker run'. Run 'docker run --help' for details."

    @staticmethod
    def build_provider_instance(
        name: ProviderInstanceName,
        config: ProviderInstanceConfig,
        mngr_ctx: MngrContext,
    ) -> ProviderInstanceInterface:
        """Build a Docker provider instance."""
        if not isinstance(config, DockerProviderConfig):
            raise MngrError(f"Expected DockerProviderConfig, got {type(config).__name__}")
        host_dir = config.host_dir if config.host_dir is not None else Path("/mngr")
        return DockerProviderInstance(
            name=name,
            host_dir=host_dir,
            mngr_ctx=mngr_ctx,
            config=config,
        )


@hookimpl
def register_provider_backend() -> tuple[type[ProviderBackendInterface], type[ProviderInstanceConfig]]:
    """Register the Docker provider backend."""
    return (DockerProviderBackend, DockerProviderConfig)
