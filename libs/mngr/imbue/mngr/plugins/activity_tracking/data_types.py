from typing import Final

from pydantic import Field

from imbue.imbue_common.primitives import PositiveInt
from imbue.mngr.config.data_types import PluginConfig

PLUGIN_NAME: Final[str] = "activity_tracking"

DEFAULT_DEBOUNCE_MS: Final[int] = 1000


class ActivityTrackingConfig(PluginConfig):
    """Configuration for the web activity tracking plugin."""

    debounce_ms: PositiveInt = Field(
        default=PositiveInt(DEFAULT_DEBOUNCE_MS),
        description="Minimum milliseconds between activity reports",
    )
