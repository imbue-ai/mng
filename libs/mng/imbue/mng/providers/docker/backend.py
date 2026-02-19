from pathlib import Path
from typing import Final

from imbue.mng import hookimpl
from imbue.mng.config.data_types import MngContext
from imbue.mng.config.data_types import ProviderInstanceConfig
from imbue.mng.errors import MngError
from imbue.mng.interfaces.provider_backend import ProviderBackendInterface
from imbue.mng.interfaces.provider_instance import ProviderInstanceInterface
from imbue.mng.primitives import ProviderBackendName
from imbue.mng.primitives import ProviderInstanceName
from imbue.mng.providers.docker.config import DockerProviderConfig
from imbue.mng.providers.docker.instance import DockerProviderInstance

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
        mng_ctx: MngContext,
    ) -> ProviderInstanceInterface:
        """Build a Docker provider instance."""
        if not isinstance(config, DockerProviderConfig):
            raise MngError(f"Expected DockerProviderConfig, got {type(config).__name__}")
        host_dir = config.host_dir if config.host_dir is not None else Path("/mng")
        return DockerProviderInstance(
            name=name,
            host_dir=host_dir,
            mng_ctx=mng_ctx,
            config=config,
        )


@hookimpl
def register_provider_backend() -> tuple[type[ProviderBackendInterface], type[ProviderInstanceConfig]]:
    """Register the Docker provider backend."""
    return (DockerProviderBackend, DockerProviderConfig)
