from pathlib import Path

from imbue.mngr.config.data_types import MngrContext
from imbue.mngr.config.data_types import ProviderInstanceConfig
from imbue.mngr.errors import ConfigStructureError
from imbue.mngr.interfaces.provider_backend import ProviderBackendInterface
from imbue.mngr.interfaces.provider_instance import ProviderInstanceInterface
from imbue.mngr.primitives import ProviderBackendName
from imbue.mngr.primitives import ProviderInstanceName
from imbue.mngr.providers.mngr_remote.config import MngrRemoteProviderConfig
from imbue.mngr.providers.mngr_remote.instance import MngrRemoteProviderInstance

MNGR_REMOTE_BACKEND_NAME = ProviderBackendName("mngr")


class MngrRemoteProviderBackend(ProviderBackendInterface):
    """Backend for connecting to a remote mngr API server as a provider.

    This allows one mngr instance to list and interact with agents managed
    by another mngr instance, without needing direct SSH access or cloud credentials.
    """

    @staticmethod
    def get_name() -> ProviderBackendName:
        return MNGR_REMOTE_BACKEND_NAME

    @staticmethod
    def get_description() -> str:
        return "Connects to a remote mngr API server to access agents managed by another mngr instance"

    @staticmethod
    def get_config_class() -> type[ProviderInstanceConfig]:
        return MngrRemoteProviderConfig

    @staticmethod
    def get_build_args_help() -> str:
        return "The mngr remote provider does not support creating hosts. Use the remote instance directly."

    @staticmethod
    def get_start_args_help() -> str:
        return "The mngr remote provider does not support starting hosts. Use the remote instance directly."

    @staticmethod
    def build_provider_instance(
        name: ProviderInstanceName,
        config: ProviderInstanceConfig,
        mngr_ctx: MngrContext,
    ) -> ProviderInstanceInterface:
        if not isinstance(config, MngrRemoteProviderConfig):
            raise ConfigStructureError(f"Expected MngrRemoteProviderConfig, got {type(config).__name__}")

        return MngrRemoteProviderInstance(
            name=name,
            host_dir=Path("/tmp/mngr-remote"),
            mngr_ctx=mngr_ctx,
            remote_url=config.url,
            remote_token=config.token,
        )
