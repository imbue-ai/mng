from pydantic import Field

from imbue.mngr.config.data_types import ProviderInstanceConfig
from imbue.mngr.primitives import ProviderBackendName


class DockerProviderConfig(ProviderInstanceConfig):
    """Configuration for the docker provider backend."""

    backend: ProviderBackendName = Field(
        default=ProviderBackendName("docker"),
        description="Provider backend (always 'docker' for this type)",
    )
    host: str = Field(
        default="",
        description="SSH URL for remote Docker host (e.g., 'ssh://user@server'). Empty string means local Docker.",
    )
