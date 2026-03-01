from pathlib import Path
from typing import Final

from imbue.mng.config.data_types import MngContext
from imbue.mng.config.data_types import ProviderInstanceConfig
from imbue.mng.errors import ConfigStructureError
from imbue.mng.interfaces.provider_backend import ProviderBackendInterface
from imbue.mng.interfaces.provider_instance import ProviderInstanceInterface
from imbue.mng.primitives import ProviderBackendName
from imbue.mng.primitives import ProviderInstanceName
from imbue.mng.providers.mng_remote.config import MngRemoteProviderConfig
from imbue.mng.providers.mng_remote.instance import MngRemoteProviderInstance

MNG_REMOTE_BACKEND_NAME: Final[ProviderBackendName] = ProviderBackendName("remote")


class MngRemoteProviderBackend(ProviderBackendInterface):
    """Backend for connecting to a remote mng API server as a provider.

    This allows one mng instance to list and interact with agents managed
    by another mng instance, without needing direct SSH access or cloud credentials.
    """

    @staticmethod
    def get_name() -> ProviderBackendName:
        return MNG_REMOTE_BACKEND_NAME

    @staticmethod
    def get_description() -> str:
        return "Connects to a remote mng API server to access agents managed by another mng instance"

    @staticmethod
    def get_config_class() -> type[ProviderInstanceConfig]:
        return MngRemoteProviderConfig

    @staticmethod
    def get_build_args_help() -> str:
        return "The mng remote provider does not support creating hosts. Use the remote instance directly."

    @staticmethod
    def get_start_args_help() -> str:
        return "The mng remote provider does not support starting hosts. Use the remote instance directly."

    @staticmethod
    def build_provider_instance(
        name: ProviderInstanceName,
        config: ProviderInstanceConfig,
        mng_ctx: MngContext,
    ) -> ProviderInstanceInterface:
        if not isinstance(config, MngRemoteProviderConfig):
            raise ConfigStructureError(f"Expected MngRemoteProviderConfig, got {type(config).__name__}")

        return MngRemoteProviderInstance(
            name=name,
            host_dir=Path("/tmp/mng-remote"),
            mng_ctx=mng_ctx,
            remote_url=config.url,
            remote_token=config.token,
        )
