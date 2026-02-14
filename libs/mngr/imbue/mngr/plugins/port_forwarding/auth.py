import secrets
from pathlib import Path
from typing import Final

from pydantic import SecretStr

from imbue.imbue_common.pure import pure

AUTH_TOKEN_BYTES: Final[int] = 32
AUTH_TOKEN_FILE_NAME: Final[str] = "auth_token"
AUTH_COOKIE_NAME: Final[str] = "mngr_auth"


def generate_auth_token() -> SecretStr:
    """Generate a cryptographically secure auth token."""
    return SecretStr(secrets.token_urlsafe(AUTH_TOKEN_BYTES))


def read_or_create_auth_token(config_dir: Path) -> SecretStr:
    """Read the auth token from disk, or create one if it doesn't exist."""
    token_path = config_dir / AUTH_TOKEN_FILE_NAME
    if token_path.exists():
        token_value = token_path.read_text().strip()
        if token_value:
            return SecretStr(token_value)

    token = generate_auth_token()
    config_dir.mkdir(parents=True, exist_ok=True)
    token_path.write_text(token.get_secret_value())
    token_path.chmod(0o600)
    return token


@pure
def generate_auth_page_html(
    auth_token: str,
    domain_suffix: str,
    vhost_port: int,
) -> str:
    """Generate an HTML page that sets the auth cookie when opened in a browser."""
    return f"""<!DOCTYPE html>
<html>
<head><title>mngr auth</title></head>
<body>
<script>
document.cookie = "{AUTH_COOKIE_NAME}={auth_token}; path=/; domain=.{domain_suffix}; max-age=31536000; SameSite=Lax";
document.body.innerHTML = "<h2>Authenticated</h2><p>The mngr authentication cookie has been set for *.{domain_suffix}:{vhost_port}.</p><p>You can close this page.</p>";
</script>
<noscript><p>JavaScript is required to set the authentication cookie.</p></noscript>
</body>
</html>"""
