from pydantic import Field

from imbue.mngr import hookimpl
from imbue.mngr.config.data_types import ProviderInstanceConfig
from imbue.mngr.errors import UnknownBackendError
from imbue.mngr.primitives import ProviderBackendName

# =============================================================================
# Provider Config Registry
# =============================================================================

_provider_config_registry: dict[ProviderBackendName, type[ProviderInstanceConfig]] = {}
# Use a mutable container to track state without 'global' keyword
_registry_state: dict[str, bool] = {"provider_configs_loaded": False}


def load_provider_configs_from_plugins(pm) -> None:
    """Load provider config classes from plugins via the register_provider_config hook."""
    if _registry_state["provider_configs_loaded"]:
        return

    # Register built-in provider config classes (each has a hookimpl static method)
    pm.register(LocalProviderConfig)
    pm.register(DockerProviderConfig)
    pm.register(ModalProviderConfig)

    # Call the hook to get all provider config registrations
    # Each implementation returns a single tuple
    all_registrations = pm.hook.register_provider_config()

    for registration in all_registrations:
        if registration is not None:
            backend_name, config_class = registration
            _register_provider_config_internal(backend_name, config_class)

    _registry_state["provider_configs_loaded"] = True


def _register_provider_config_internal(
    backend: str,
    config_class: type[ProviderInstanceConfig],
) -> None:
    """Internal function to register a provider config class."""
    _provider_config_registry[ProviderBackendName(backend)] = config_class


def get_provider_config_class(backend: str) -> type[ProviderInstanceConfig]:
    """Get the config class for a backend."""
    key = ProviderBackendName(backend)
    if key not in _provider_config_registry:
        registered = ", ".join(sorted(str(k) for k in _provider_config_registry.keys()))
        raise UnknownBackendError(
            f"Unknown provider backend: {backend}. Registered backends: {registered or '(none)'}"
        )
    return _provider_config_registry[key]


# =============================================================================
# Built-in Provider Config Classes
# =============================================================================


class LocalProviderConfig(ProviderInstanceConfig):
    """Config for the local provider backend."""

    backend: ProviderBackendName = Field(
        default=ProviderBackendName("local"),
        description="Provider backend (always 'local' for this type)",
    )

    @staticmethod
    @hookimpl
    def register_provider_config() -> tuple[str, type[ProviderInstanceConfig]]:
        """Register the local provider config."""
        return ("local", LocalProviderConfig)


class DockerProviderConfig(ProviderInstanceConfig):
    """Config for the docker provider backend."""

    backend: ProviderBackendName = Field(
        default=ProviderBackendName("docker"),
        description="Provider backend (always 'docker' for this type)",
    )
    host: str = Field(
        default="",
        description="SSH URL for remote Docker host (e.g., 'ssh://user@server'). Empty string means local Docker.",
    )

    @staticmethod
    @hookimpl
    def register_provider_config() -> tuple[str, type[ProviderInstanceConfig]]:
        """Register the docker provider config."""
        return ("docker", DockerProviderConfig)


class ModalProviderConfig(ProviderInstanceConfig):
    """Config for the modal provider backend."""

    backend: ProviderBackendName = Field(
        default=ProviderBackendName("modal"),
        description="Provider backend (always 'modal' for this type)",
    )
    environment: str = Field(
        default="main",
        description="Modal environment name",
    )

    @staticmethod
    @hookimpl
    def register_provider_config() -> tuple[str, type[ProviderInstanceConfig]]:
        """Register the modal provider config."""
        return ("modal", ModalProviderConfig)
