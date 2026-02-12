from pydantic import Field
from pydantic import SecretStr

from imbue.mngr.config.data_types import ProviderInstanceConfig


class MngrRemoteProviderConfig(ProviderInstanceConfig):
    """Configuration for the mngr remote provider backend.

    Connects to a remote mngr API server (from the api_server plugin)
    to access agents and hosts managed by that instance.
    """

    url: str = Field(description="Base URL of the remote mngr API server (e.g. 'https://mngr.example.com')")
    token: SecretStr = Field(description="Bearer token for authenticating with the remote API server")
