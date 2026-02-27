import os
from pathlib import Path
from typing import Final

from pydantic import Field

from imbue.imbue_common.frozen_model import FrozenModel

DEFAULT_DATA_DIR_NAME: Final[str] = ".changelings"

DEFAULT_MNG_HOST_DIR_NAME: Final[str] = ".mng"

DEFAULT_FORWARDING_SERVER_HOST: Final[str] = "127.0.0.1"

DEFAULT_FORWARDING_SERVER_PORT: Final[int] = 8420


class ChangelingPaths(FrozenModel):
    """Resolved filesystem paths for changelings data storage."""

    data_dir: Path = Field(description="Root directory for changelings data (e.g. ~/.changelings)")

    @property
    def auth_dir(self) -> Path:
        """Directory for authentication data (signing key, one-time codes)."""
        return self.data_dir / "auth"


def get_default_data_dir() -> Path:
    """Return the default data directory for changelings (~/.changelings)."""
    return Path.home() / DEFAULT_DATA_DIR_NAME


def get_default_mng_host_dir() -> Path:
    """Return the mng host directory, respecting the MNG_HOST_DIR environment variable.

    Falls back to ~/.mng if MNG_HOST_DIR is not set, matching mng's own default.
    """
    env_value = os.environ.get("MNG_HOST_DIR")
    if env_value:
        return Path(env_value)
    return Path.home() / DEFAULT_MNG_HOST_DIR_NAME
