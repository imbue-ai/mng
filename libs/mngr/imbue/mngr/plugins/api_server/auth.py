from pathlib import Path
from typing import Final

from pydantic import SecretStr

from imbue.mngr.plugins.api_server.data_types import generate_api_token

API_TOKEN_FILE_NAME: Final[str] = "api_token"


def read_or_create_api_token(config_dir: Path) -> SecretStr:
    """Read the API token from disk, or generate and persist a new one."""
    token_path = config_dir / API_TOKEN_FILE_NAME
    if token_path.exists():
        token_value = token_path.read_text().strip()
        if token_value:
            return SecretStr(token_value)

    # Generate a new token
    token_value = generate_api_token()
    config_dir.mkdir(parents=True, exist_ok=True)
    token_path.write_text(token_value)
    token_path.chmod(0o600)
    return SecretStr(token_value)
