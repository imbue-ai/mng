import pluggy

from imbue.imbue_common.pure import pure
from imbue.mngr.config.data_types import MngrContext
from imbue.mngr.config.data_types import ProviderInstanceConfig
from imbue.mngr.errors import ConfigStructureError
from imbue.mngr.errors import UnknownBackendError
from imbue.mngr.interfaces.provider_backend import ProviderBackendInterface
from imbue.mngr.primitives import ProviderBackendName
from imbue.mngr.primitives import ProviderInstanceName
from imbue.mngr.providers.base_provider import BaseProviderInstance

# Cache for registered backends
_backend_registry: dict[ProviderBackendName, type[ProviderBackendInterface]] = {}
# Cache for registered config classes (may include configs for backends not currently loaded)
_config_registry: dict[ProviderBackendName, type[ProviderInstanceConfig]] = {}
# Use a mutable container to track state without 'global' keyword.
# This dict is shared with registry_loader.py (which imports it) so both
# modules see the same state.
_registry_state: dict[str, bool] = {"backends_loaded": False}


def load_all_registries(pm: pluggy.PluginManager) -> None:
    """Load all registries from plugins.

    This is the main entry point for loading all pluggy-based registries.
    Call this once during application startup, before using any registry lookups.

    This is a thin facade that defers to registry_loader to avoid importing
    heavyweight backend modules (Modal, Docker, etc.) at CLI startup time.
    """
    from imbue.mngr.providers.registry_loader import load_all_registries as _load

    _load(pm)


def load_local_backend_only(pm: pluggy.PluginManager) -> None:
    """Load only the local and SSH provider backends.

    This is used by tests to avoid depending on external services.
    Unlike load_backends_from_plugins, this only registers the local and SSH backends
    (not Modal or Docker which require external daemons/credentials).
    """
    from imbue.mngr.providers.registry_loader import load_local_backend_only as _load

    _load(pm)


def reset_backend_registry() -> None:
    """Reset the backend registry to its initial state.

    This is primarily used for test isolation to ensure a clean state between tests.
    """
    _backend_registry.clear()
    _config_registry.clear()
    _registry_state["backends_loaded"] = False


def get_backend(name: str | ProviderBackendName) -> type[ProviderBackendInterface]:
    """Get a provider backend class by name.

    Backends are loaded from plugins via the plugin manager.
    """
    key = ProviderBackendName(name) if isinstance(name, str) else name
    if key not in _backend_registry:
        available = sorted(str(k) for k in _backend_registry.keys())
        raise UnknownBackendError(
            f"Unknown provider backend: {key}. Registered backends: {', '.join(available) or '(none)'}"
        )
    return _backend_registry[key]


def get_config_class(name: str | ProviderBackendName) -> type[ProviderInstanceConfig]:
    """Get the config class for a provider backend.

    This returns the typed config class that should be used when parsing
    configuration for the given backend.
    """
    key = ProviderBackendName(name) if isinstance(name, str) else name
    if key not in _config_registry:
        registered = ", ".join(sorted(str(k) for k in _config_registry.keys()))
        raise UnknownBackendError(f"Unknown provider backend: {key}. Registered backends: {registered or '(none)'}")
    return _config_registry[key]


def list_backends() -> list[str]:
    """List all registered backend names."""
    return sorted(str(k) for k in _backend_registry.keys())


def build_provider_instance(
    instance_name: ProviderInstanceName,
    backend_name: ProviderBackendName,
    config: ProviderInstanceConfig,
    mngr_ctx: MngrContext,
) -> BaseProviderInstance:
    """Build a provider instance using the registered backend."""
    backend_class = get_backend(backend_name)
    obj = backend_class.build_provider_instance(
        name=instance_name,
        config=config,
        mngr_ctx=mngr_ctx,
    )
    if not isinstance(obj, BaseProviderInstance):
        raise ConfigStructureError(
            f"Backend {backend_name} returned {type(obj).__name__}, expected BaseProviderInstance subclass"
        )
    return obj


@pure
def _indent_text(text: str, indent: str) -> str:
    """Indent each line of text with the given prefix."""
    return "\n".join(indent + line if line.strip() else "" for line in text.split("\n"))


def get_all_provider_args_help_sections() -> tuple[tuple[str, str], ...]:
    """Generate help sections for build/start args from all registered backends.

    Returns a tuple of (title, content) pairs suitable for use as additional
    sections in CommandHelpMetadata.
    """
    lines: list[str] = []
    for backend_name in sorted(_backend_registry.keys()):
        backend_class = _backend_registry[backend_name]
        build_help = backend_class.get_build_args_help().strip()
        start_help = backend_class.get_start_args_help().strip()
        lines.append(f"Provider: {backend_name}")
        lines.append(_indent_text(build_help, "  "))
        if start_help != build_help:
            lines.append(_indent_text(start_help, "  "))
        lines.append("")
    return (("Provider Build/Start Arguments", "\n".join(lines)),)
