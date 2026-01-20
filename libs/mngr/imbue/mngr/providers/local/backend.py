import os
from typing import Any

from imbue.mngr import hookimpl
from imbue.mngr.config.data_types import MngrContext
from imbue.mngr.interfaces.provider_backend import ProviderBackendInterface
from imbue.mngr.interfaces.provider_instance import ProviderInstanceInterface
from imbue.mngr.primitives import ProviderBackendName
from imbue.mngr.primitives import ProviderInstanceName
from imbue.mngr.providers.local.instance import LocalProviderInstance

LOCAL_BACKEND_NAME = ProviderBackendName("local")


class LocalProviderBackend(ProviderBackendInterface):
    """Backend for creating local provider instances.

    The local provider backend creates provider instances that manage the local
    computer as a host. Multiple instances can be created with different names
    and host_dir settings.
    """

    @staticmethod
    def get_name() -> ProviderBackendName:
        return LOCAL_BACKEND_NAME

    @staticmethod
    def get_description() -> str:
        return "Runs agents directly on your local machine with no isolation"

    @staticmethod
    def get_build_args_help() -> str:
        return "No build arguments are supported for the local provider."

    @staticmethod
    def get_start_args_help() -> str:
        return "No start arguments are supported for the local provider."

    @staticmethod
    def build_provider_instance(
        name: ProviderInstanceName,
        instance_configuration: dict[str, Any],
        mngr_ctx: MngrContext,
    ) -> ProviderInstanceInterface:
        """Build a local provider instance.

        The instance_configuration may contain:
        - host_dir: Base directory for mngr data (defaults to mngr_ctx.config.default_host_dir)
        """
        host_dir = instance_configuration.get("host_dir", mngr_ctx.config.default_host_dir)
        # Expand ~ to the actual home directory
        host_dir = os.path.expanduser(host_dir)
        return LocalProviderInstance(
            name=name,
            host_dir=host_dir,
            mngr_ctx=mngr_ctx,
        )


@hookimpl
def register_provider_backend() -> type[ProviderBackendInterface]:
    """Register the local provider backend."""
    return LocalProviderBackend
