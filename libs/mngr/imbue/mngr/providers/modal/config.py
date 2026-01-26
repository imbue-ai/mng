from pathlib import Path

from pydantic import Field

from imbue.mngr.config.data_types import ProviderInstanceConfig
from imbue.mngr.primitives import ProviderBackendName


class ModalProviderConfig(ProviderInstanceConfig):
    """Configuration for the modal provider backend."""

    backend: ProviderBackendName = Field(
        default=ProviderBackendName("modal"),
        description="Provider backend (always 'modal' for this type)",
    )
    environment: str = Field(
        default="main",
        description="Modal environment name",
    )
    app_name: str | None = Field(
        default=None,
        description="Modal app name (defaults to 'mngr-{user_id}-{name}')",
    )
    host_dir: Path | None = Field(
        default=None,
        description="Base directory for mngr data on the sandbox (defaults to /mngr)",
    )
    default_timeout: int = Field(
        default=900,
        description="Default sandbox timeout in seconds",
    )
    default_cpu: float = Field(
        default=1.0,
        description="Default CPU cores",
    )
    default_memory: float = Field(
        default=1.0,
        description="Default memory in GB",
    )
    is_persistent: bool = Field(
        default=True,
        description=(
            "Configuration marker for Modal app persistence. When True (default), indicates "
            "the app is intended for production use. When False (set in tests), indicates "
            "the app is for testing and should be cleaned up. This field enables tests to "
            "signal their intent for easier identification and cleanup of test resources."
        ),
    )
