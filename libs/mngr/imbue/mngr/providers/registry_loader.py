"""Heavy backend loading logic, separated from registry.py for fast tab completion.

registry.py is imported at CLI startup (via main.py). By keeping the heavyweight
backend module imports here instead, tab-completion (which never executes commands)
avoids paying the ~370ms cost of importing Modal, Docker, SSH, and local backends.

The loading functions in this module are called lazily -- either from
setup_command_context() (normal command execution) or from the facade functions
in registry.py (for callers that don't know about this split).
"""

import pluggy

import imbue.mngr.providers.docker.backend as docker_backend_module
import imbue.mngr.providers.local.backend as local_backend_module
import imbue.mngr.providers.modal.backend as modal_backend_module
import imbue.mngr.providers.ssh.backend as ssh_backend_module
from imbue.mngr.agents.agent_registry import load_agents_from_plugins
from imbue.mngr.primitives import ProviderBackendName
from imbue.mngr.providers.docker.config import DockerProviderConfig
from imbue.mngr.providers.registry import backend_registry
from imbue.mngr.providers.registry import config_registry
from imbue.mngr.providers.registry import registry_state


def _load_backends(pm: pluggy.PluginManager, *, include_modal: bool, include_docker: bool) -> None:
    """Load provider backends from the specified modules.

    The pm parameter is the pluggy plugin manager. If include_modal is True,
    the Modal backend is included (requires Modal credentials). If include_docker
    is True, the Docker backend is included (requires a Docker daemon).
    """
    if registry_state["backends_loaded"]:
        return

    pm.register(local_backend_module, name="local")
    pm.register(ssh_backend_module, name="ssh")
    if include_docker:
        pm.register(docker_backend_module, name="docker")
    if include_modal:
        pm.register(modal_backend_module, name="modal")

    registrations = pm.hook.register_provider_backend()

    for registration in registrations:
        if registration is not None:
            backend_class, config_class = registration
            backend_name = backend_class.get_name()
            backend_registry[backend_name] = backend_class
            config_registry[backend_name] = config_class

    # Register docker config even when backend is not loaded, so config files
    # referencing the docker backend can still be parsed
    if not include_docker:
        config_registry[ProviderBackendName("docker")] = DockerProviderConfig

    registry_state["backends_loaded"] = True


def load_local_backend_only(pm: pluggy.PluginManager) -> None:
    """Load only the local and SSH provider backends.

    This is used by tests to avoid depending on external services.
    Unlike load_backends_from_plugins, this only registers the local and SSH backends
    (not Modal or Docker which require external daemons/credentials).
    """
    _load_backends(pm, include_modal=False, include_docker=False)


def load_backends_from_plugins(pm: pluggy.PluginManager) -> None:
    """Load all provider backends from plugins."""
    _load_backends(pm, include_modal=True, include_docker=True)


def load_all_registries(pm: pluggy.PluginManager) -> None:
    """Load all registries from plugins.

    This is the main entry point for loading all pluggy-based registries.
    Call this once during application startup, before using any registry lookups.
    """
    load_backends_from_plugins(pm)
    load_agents_from_plugins(pm)
