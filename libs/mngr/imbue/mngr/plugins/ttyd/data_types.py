import secrets
from typing import Final

from pydantic import Field

from imbue.imbue_common.primitives import PositiveInt
from imbue.mngr.config.data_types import PluginConfig

PLUGIN_NAME: Final[str] = "ttyd"

DEFAULT_TTYD_BASE_PORT: Final[int] = 7681

TTYD_TOKEN_BYTES: Final[int] = 32


class TtydConfig(PluginConfig):
    """Configuration for the ttyd web terminal plugin."""

    base_port: PositiveInt = Field(
        default=PositiveInt(DEFAULT_TTYD_BASE_PORT),
        description="Base port for ttyd instances (each agent gets base_port + offset)",
    )


def generate_ttyd_token() -> str:
    """Generate a cryptographically secure token for ttyd access."""
    return secrets.token_urlsafe(TTYD_TOKEN_BYTES)
