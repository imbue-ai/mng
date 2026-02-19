import importlib
from typing import Final

import pluggy

from imbue.imbue_common.pure import pure
from imbue.mng.config.data_types import MngContext
from imbue.mng.config.data_types import ProviderInstanceConfig
from imbue.mng.errors import ConfigStructureError
from imbue.mng.errors import UnknownBackendError
from imbue.mng.interfaces.provider_backend import ProviderBackendInterface
from imbue.mng.primitives import ProviderBackendName
from imbue.mng.primitives import ProviderInstanceName
from imbue.mng.providers.base_provider import BaseProviderInstance

# Cache for registered backends
backend_registry: dict[ProviderBackendName, type[ProviderBackendInterface]] = {}
# Cache for registered config classes (may include configs for backends not currently loaded)
config_registry: dict[ProviderBackendName, type[ProviderInstanceConfig]] = {}
# Tracks whether config classes have been registered (prevents re-registration).
_config_classes_registered: dict[str, bool] = {"value": False}
# Tracks whether backends have been explicitly loaded (prevents re-loading in tests
# where the fixture controls which backends are available).
_backends_loaded: dict[str, bool] = {"value": False}

# Maps backend names to their module paths for on-demand loading
BACKEND_MODULES: Final[dict[str, str]] = {
    "local": "imbue.mng.providers.local.backend",
    "ssh": "imbue.mng.providers.ssh.backend",
    "docker": "imbue.mng.providers.docker.backend",
    "modal": "imbue.mng.providers.modal.backend",
}


def register_config_classes() -> None:
    """Register provider config classes without loading backend modules.

    Config classes are lightweight pydantic models needed for config parsing.
    Backend implementations are loaded on-demand by get_backend().
    """
    if _config_classes_registered["value"]:
        return
    _config_classes_registered["value"] = True
    from imbue.mng.providers.docker.config import DockerProviderConfig
    from imbue.mng.providers.local.config import LocalProviderConfig
    from imbue.mng.providers.modal.config import ModalProviderConfig
    from imbue.mng.providers.ssh.config import SSHProviderConfig

    config_registry[ProviderBackendName("docker")] = DockerProviderConfig
    config_registry[ProviderBackendName("local")] = LocalProviderConfig
    config_registry[ProviderBackendName("modal")] = ModalProviderConfig
    config_registry[ProviderBackendName("ssh")] = SSHProviderConfig


def _load_single_backend(pm: pluggy.PluginManager, name: str) -> None:
    """Load a single backend module and register it via the plugin manager."""
    key = ProviderBackendName(name)
    if key in backend_registry:
        return
    # Skip blocked (disabled) plugins entirely to avoid the import cost
    if pm.is_blocked(name):
        return
    module_path = BACKEND_MODULES.get(name)
    if module_path is None:
        return
    module = importlib.import_module(module_path)
    if not pm.is_registered(module):
        pm.register(module, name=name)
    # Call hook and register only newly-discovered backends
    for registration in pm.hook.register_provider_backend():
        if registration is not None:
            backend_class, config_class = registration
            backend_name = backend_class.get_name()
            if backend_name not in backend_registry:
                backend_registry[backend_name] = backend_class
                config_registry[backend_name] = config_class


def load_all_backends(pm: pluggy.PluginManager) -> None:
    """Load all backend implementations.

    Used by --help (to show provider args) and tests that need all backends.
    """
    register_config_classes()
    for name in BACKEND_MODULES:
        _load_single_backend(pm, name)
    _backends_loaded["value"] = True


def load_non_disabled_backends(pm: pluggy.PluginManager, disabled_plugins: frozenset[str]) -> None:
    """Load all backend implementations except those in disabled_plugins.

    Called during command setup after config is loaded, so we know which
    plugins are disabled. Skipping disabled backends avoids their import cost
    (e.g., Modal adds ~150ms).

    No-op if backends have already been explicitly loaded (e.g., by a test
    fixture via load_local_backend_only).
    """
    if _backends_loaded["value"]:
        return
    _backends_loaded["value"] = True
    for name in BACKEND_MODULES:
        if name not in disabled_plugins:
            _load_single_backend(pm, name)


def load_local_backend_only(pm: pluggy.PluginManager) -> None:
    """Load only the local and SSH provider backends.

    This is used by tests to avoid depending on external services.
    Unlike load_all_backends, this only registers the local and SSH backends
    (not Modal or Docker which require external daemons/credentials).
    """
    register_config_classes()
    _load_single_backend(pm, "local")
    _load_single_backend(pm, "ssh")
    _backends_loaded["value"] = True


def reset_backend_registry() -> None:
    """Reset the backend registry to its initial state.

    This is primarily used for test isolation to ensure a clean state between tests.
    """
    backend_registry.clear()
    config_registry.clear()
    _config_classes_registered["value"] = False
    _backends_loaded["value"] = False


def get_backend(name: str | ProviderBackendName, pm: pluggy.PluginManager) -> type[ProviderBackendInterface]:
    """Get a provider backend class by name, loading it on-demand if needed.

    Backends are loaded from plugins via the plugin manager on first access.
    """
    key = ProviderBackendName(name) if isinstance(name, str) else name
    if key not in backend_registry:
        _load_single_backend(pm, str(key))
    if key not in backend_registry:
        available = sorted(str(k) for k in config_registry.keys())
        raise UnknownBackendError(
            f"Unknown provider backend: {key}. Registered backends: {', '.join(available) or '(none)'}"
        )
    return backend_registry[key]


def get_config_class(name: str | ProviderBackendName) -> type[ProviderInstanceConfig]:
    """Get the config class for a provider backend.

    This returns the typed config class that should be used when parsing
    configuration for the given backend.
    """
    key = ProviderBackendName(name) if isinstance(name, str) else name
    if key not in config_registry:
        registered = ", ".join(sorted(str(k) for k in config_registry.keys()))
        raise UnknownBackendError(f"Unknown provider backend: {key}. Registered backends: {registered or '(none)'}")
    return config_registry[key]


def list_backends() -> list[str]:
    """List all loaded backend names.

    Returns names from backend_registry (only backends whose implementations
    have actually been loaded). Used by get_all_provider_instances to enumerate
    backends that can be instantiated.
    """
    return sorted(str(k) for k in backend_registry.keys())


def build_provider_instance(
    instance_name: ProviderInstanceName,
    backend_name: ProviderBackendName,
    config: ProviderInstanceConfig,
    mng_ctx: MngContext,
) -> BaseProviderInstance:
    """Build a provider instance using the registered backend."""
    backend_class = get_backend(backend_name, mng_ctx.pm)
    obj = backend_class.build_provider_instance(
        name=instance_name,
        config=config,
        mng_ctx=mng_ctx,
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
    for backend_name in sorted(backend_registry.keys()):
        backend_class = backend_registry[backend_name]
        build_help = backend_class.get_build_args_help().strip()
        start_help = backend_class.get_start_args_help().strip()
        lines.append(f"Provider: {backend_name}")
        lines.append(_indent_text(build_help, "  "))
        if start_help != build_help:
            lines.append(_indent_text(start_help, "  "))
        lines.append("")
    return (("Provider Build/Start Arguments", "\n".join(lines)),)
