import secrets
from pathlib import Path
from typing import Final

from pydantic import SecretStr

TOKEN_BYTES: Final[int] = 32


def generate_secure_token() -> str:
    """Generate a cryptographically secure URL-safe token."""
    return secrets.token_urlsafe(TOKEN_BYTES)


def read_or_create_token_file(config_dir: Path, filename: str) -> SecretStr:
    """Read a token from disk, or generate and persist a new one.

    Creates the config directory and sets file permissions to 0600.
    """
    token_path = config_dir / filename
    if token_path.exists():
        token_value = token_path.read_text().strip()
        if token_value:
            return SecretStr(token_value)

    token_value = generate_secure_token()
    config_dir.mkdir(parents=True, exist_ok=True)
    token_path.write_text(token_value)
    token_path.chmod(0o600)
    return SecretStr(token_value)
