from pathlib import Path
from typing import Final

from pydantic import SecretStr

from imbue.mngr.plugins.port_forwarding.auth import read_or_create_token

API_TOKEN_FILE_NAME: Final[str] = "api_token"


def read_or_create_api_token(config_dir: Path) -> SecretStr:
    """Read the API token from disk, or generate and persist a new one."""
    return read_or_create_token(config_dir, API_TOKEN_FILE_NAME)
