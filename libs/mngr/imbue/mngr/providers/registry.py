# NOTE: These top-level imports cause Modal to be loaded even when not needed,
# adding ~0.1s to every command. Profiling of `mngr list --provider local` shows:
#   - Total CLI time: ~0.9s
#   - With Modal disabled entirely (--disable-plugin modal): ~0.76s
#   - Python-level work (imports + list_agents): ~0.58s
#
# The Modal import happens here unconditionally, even when --provider filters to
# local-only. To fix: move these imports inside load_backends_from_plugins() and
# load_local_backend_only(), or only import backends that are actually enabled.
#
# Another candidate for lazy loading: celpy (~45ms) in api/list.py. It's only
# needed when CEL filters are used (--include/--exclude), but is currently
# imported at the top level via imbue.mngr.utils.cel_utils.
import imbue.mngr.providers.docker.backend as docker_backend_module
import imbue.mngr.providers.local.backend as local_backend_module
import imbue.mngr.providers.modal.backend as modal_backend_module
import imbue.mngr.providers.ssh.backend as ssh_backend_module
from imbue.mngr.agents.agent_registry import load_agents_from_plugins
from imbue.mngr.config.data_types import MngrContext
from imbue.mngr.config.data_types import ProviderInstanceConfig
from imbue.mngr.errors import ConfigStructureError
from imbue.mngr.errors import UnknownBackendError
from imbue.mngr.interfaces.provider_backend import ProviderBackendInterface
from imbue.mngr.primitives import ProviderBackendName
from imbue.mngr.primitives import ProviderInstanceName
from imbue.mngr.providers.base_provider import BaseProviderInstance
from imbue.mngr.providers.docker.config import DockerProviderConfig

# Cache for registered backends
_backend_registry: dict[ProviderBackendName, type[ProviderBackendInterface]] = {}
# Cache for registered config classes (may include configs for backends not currently loaded)
_config_registry: dict[ProviderBackendName, type[ProviderInstanceConfig]] = {}
# Use a mutable container to track state without 'global' keyword
_registry_state: dict[str, bool] = {"backends_loaded": False}


def load_all_registries(pm) -> None:
    """Load all registries from plugins.

    This is the main entry point for loading all pluggy-based registries.
    Call this once during application startup, before using any registry lookups.
    """
    load_backends_from_plugins(pm)
    load_agents_from_plugins(pm)


def reset_backend_registry() -> None:
    """Reset the backend registry to its initial state.

    This is primarily used for test isolation to ensure a clean state between tests.
    """
    _backend_registry.clear()
    _config_registry.clear()
    _registry_state["backends_loaded"] = False


def _load_backends(pm, *, include_modal: bool, include_docker: bool) -> None:
    """Load provider backends from the specified modules.

    The pm parameter is the pluggy plugin manager. If include_modal is True,
    the Modal backend is included (requires Modal credentials). If include_docker
    is True, the Docker backend is included (requires a Docker daemon).
    """
    if _registry_state["backends_loaded"]:
        return

    pm.register(local_backend_module)
    pm.register(ssh_backend_module)
    if include_docker:
        pm.register(docker_backend_module)
    if include_modal:
        pm.register(modal_backend_module)

    registrations = pm.hook.register_provider_backend()

    for registration in registrations:
        if registration is not None:
            backend_class, config_class = registration
            backend_name = backend_class.get_name()
            _backend_registry[backend_name] = backend_class
            _config_registry[backend_name] = config_class

    # Register docker config even when backend is not loaded, so config files
    # referencing the docker backend can still be parsed
    if not include_docker:
        _config_registry[ProviderBackendName("docker")] = DockerProviderConfig

    _registry_state["backends_loaded"] = True


def load_local_backend_only(pm) -> None:
    """Load only the local and SSH provider backends.

    This is used by tests to avoid depending on external services.
    Unlike load_backends_from_plugins, this only registers the local and SSH backends
    (not Modal or Docker which require external daemons/credentials).
    """
    _load_backends(pm, include_modal=False, include_docker=False)


def load_backends_from_plugins(pm) -> None:
    """Load all provider backends from plugins."""
    _load_backends(pm, include_modal=True, include_docker=True)


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
