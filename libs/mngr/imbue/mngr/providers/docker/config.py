"""Configuration for the Docker provider backend."""

from pathlib import Path

from pydantic import Field

from imbue.mngr.config.data_types import ProviderInstanceConfig
from imbue.mngr.primitives import ActivitySource
from imbue.mngr.primitives import IdleMode
from imbue.mngr.primitives import ProviderBackendName


class DockerProviderConfig(ProviderInstanceConfig):
    """Configuration for the docker provider backend."""

    backend: ProviderBackendName = Field(
        default=ProviderBackendName("docker"),
        description="Provider backend (always 'docker' for this type)",
    )
    host: str = Field(
        default="",
        description=(
            "Docker host URL (e.g., 'ssh://user@server', 'tcp://host:2376'). "
            "Empty string means local Docker daemon."
        ),
    )
    host_dir: Path | None = Field(
        default=None,
        description="Base directory for mngr data inside containers (defaults to /mngr)",
    )
    default_image: str | None = Field(
        default=None,
        description="Default base image. None uses debian:bookworm-slim.",
    )
    default_cpu: float = Field(
        default=1.0,
        description="Default CPU cores (maps to Docker --cpus)",
    )
    default_memory: float = Field(
        default=1.0,
        description="Default memory in GB (maps to Docker --memory)",
    )
    default_gpu: str | None = Field(
        default=None,
        description="Default GPU configuration. None means no GPU.",
    )
    default_idle_timeout: int = Field(
        default=800,
        description="Default host idle timeout in seconds",
    )
    default_idle_mode: IdleMode = Field(
        default=IdleMode.IO,
        description="Default idle mode for hosts",
    )
    default_activity_sources: tuple[ActivitySource, ...] = Field(
        default_factory=lambda: tuple(ActivitySource),
        description="Default activity sources that count toward keeping host active",
    )
    network: str | None = Field(
        default=None,
        description="Docker network to attach containers to. None uses the default bridge.",
    )
    extra_hosts: dict[str, str] = Field(
        default_factory=dict,
        description="Extra /etc/hosts entries (maps to Docker --add-host)",
    )
