from typing import Final

from pydantic import Field
from pydantic import SecretStr

from imbue.imbue_common.primitives import PositiveInt
from imbue.mngr.config.data_types import PluginConfig

PLUGIN_NAME: Final[str] = "api_server"

DEFAULT_API_PORT: Final[int] = 8000


class ApiServerConfig(PluginConfig):
    """Configuration for the HTTP API server plugin."""

    port: PositiveInt = Field(
        default=PositiveInt(DEFAULT_API_PORT),
        description="Port for the API server",
    )
    api_token: SecretStr | None = Field(
        default=None,
        description="Bearer token for API authentication (auto-generated if not set)",
    )
    host: str = Field(
        default="0.0.0.0",
        description="Host to bind the API server to",
    )
