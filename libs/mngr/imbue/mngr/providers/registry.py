from typing import Any

import imbue.mngr.providers.local.backend as local_backend_module
import imbue.mngr.providers.modal.backend as modal_backend_module
import imbue.mngr.providers.ssh.backend as ssh_backend_module
from imbue.mngr.agents.agent_registry import load_agents_from_plugins
from imbue.mngr.config.data_types import MngrContext
from imbue.mngr.config.provider_registry import load_provider_configs_from_plugins
from imbue.mngr.interfaces.provider_backend import ProviderBackendInterface
from imbue.mngr.primitives import ProviderBackendName
from imbue.mngr.primitives import ProviderInstanceName
from imbue.mngr.providers.base_provider import BaseProviderInstance

# Cache for registered backends
_backend_registry: dict[ProviderBackendName, type[ProviderBackendInterface]] = {}
# Use a mutable container to track state without 'global' keyword
_registry_state: dict[str, bool] = {"backends_loaded": False}


class UnknownBackendError(Exception):
    """Raised when an unknown provider backend is requested."""

    def __init__(self, backend_name: str, available: list[str]) -> None:
        self.backend_name = backend_name
        self.available = available
        super().__init__(f"Unknown provider backend: {backend_name}. Available: {', '.join(available) or '(none)'}")


def load_all_registries(pm) -> None:
    """Load all registries from plugins.

    This is the main entry point for loading all pluggy-based registries.
    Call this once during application startup, before using any registry lookups.
    """
    load_backends_from_plugins(pm)
    load_agents_from_plugins(pm)
    load_provider_configs_from_plugins(pm)


def reset_backend_registry() -> None:
    """Reset the backend registry to its initial state.

    This is primarily used for test isolation to ensure a clean state between tests.
    """
    _backend_registry.clear()
    _registry_state["backends_loaded"] = False


def load_local_backend_only(pm) -> None:
    """Load only the local and SSH provider backends.

    This is used by tests to avoid depending on Modal credentials.
    Unlike load_backends_from_plugins, this only registers the local and SSH backends.
    """
    if _registry_state["backends_loaded"]:
        return

    pm.register(local_backend_module)
    pm.register(ssh_backend_module)
    backends = pm.hook.register_provider_backend()

    for backend_class in backends:
        if backend_class is not None:
            backend_name = backend_class.get_name()
            _backend_registry[backend_name] = backend_class

    _registry_state["backends_loaded"] = True


def load_backends_from_plugins(pm) -> None:
    """Load all provider backends from plugins."""
    if _registry_state["backends_loaded"]:
        return

    pm.register(local_backend_module)
    pm.register(modal_backend_module)
    pm.register(ssh_backend_module)
    backends = pm.hook.register_provider_backend()

    for backend_class in backends:
        if backend_class is not None:
            backend_name = backend_class.get_name()
            _backend_registry[backend_name] = backend_class

    _registry_state["backends_loaded"] = True


def get_backend(name: str | ProviderBackendName) -> type[ProviderBackendInterface]:
    """Get a provider backend class by name.

    Backends are loaded from plugins via the plugin manager.
    """
    key = ProviderBackendName(name) if isinstance(name, str) else name
    if key not in _backend_registry:
        available = sorted(str(k) for k in _backend_registry.keys())
        raise UnknownBackendError(str(key), available)
    return _backend_registry[key]


def list_backends() -> list[str]:
    """List all registered backend names."""
    return sorted(str(k) for k in _backend_registry.keys())


def build_provider_instance(
    instance_name: ProviderInstanceName,
    backend_name: ProviderBackendName,
    instance_configuration: dict[str, Any],
    mngr_ctx: MngrContext,
) -> BaseProviderInstance:
    """Build a provider instance using the registered backend."""
    backend_class = get_backend(backend_name)
    obj = backend_class.build_provider_instance(
        name=instance_name,
        instance_configuration=instance_configuration,
        mngr_ctx=mngr_ctx,
    )
    assert isinstance(obj, BaseProviderInstance)
    return obj
