from pydantic import Field
from pydantic import SecretStr

from imbue.mng.config.data_types import ProviderInstanceConfig


class MngRemoteProviderConfig(ProviderInstanceConfig):
    """Configuration for the mng remote provider backend.

    Connects to a remote mng API server (from the api_server plugin)
    to access agents and hosts managed by that instance.
    """

    url: str = Field(description="Base URL of the remote mng API server (e.g. 'https://mng.example.com')")
    token: SecretStr = Field(description="Bearer token for authenticating with the remote API server")
