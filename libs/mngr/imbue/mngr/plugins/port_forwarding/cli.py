import sys
import tempfile
import webbrowser
from pathlib import Path

import click
from loguru import logger

from imbue.mngr.plugins.port_forwarding.auth import generate_auth_page_html
from imbue.mngr.plugins.port_forwarding.auth import read_or_create_auth_token
from imbue.mngr.plugins.port_forwarding.data_types import DEFAULT_DOMAIN_SUFFIX
from imbue.mngr.plugins.port_forwarding.data_types import DEFAULT_VHOST_HTTP_PORT


@click.command(name="auth")
@click.option(
    "--show-token",
    is_flag=True,
    default=False,
    help="Print the auth token to stdout instead of opening a browser",
)
@click.option(
    "--config-dir",
    type=click.Path(path_type=Path),
    default=Path("~/.config/mngr"),
    help="Path to the mngr config directory",
)
def auth_command(show_token: bool, config_dir: Path) -> None:
    """Set up authentication for accessing forwarded services.

    Opens a browser page that sets the mngr authentication cookie for
    *.mngr.localhost, allowing you to access forwarded agent services.

    Use --show-token to print the token for programmatic access via the
    X-Mngr-Auth header.
    """
    expanded_config_dir = config_dir.expanduser()
    token = read_or_create_auth_token(expanded_config_dir)

    if show_token:
        # Write directly to stdout for programmatic consumption (e.g. piping)
        sys.stdout.write(token.get_secret_value() + "\n")
        return

    # Generate the auth page and open it in the browser
    html_content = generate_auth_page_html(
        auth_token=token.get_secret_value(),
        domain_suffix=DEFAULT_DOMAIN_SUFFIX,
        vhost_port=DEFAULT_VHOST_HTTP_PORT,
    )

    with tempfile.NamedTemporaryFile(suffix=".html", delete=False, mode="w") as temp_file:
        temp_file.write(html_content)
        temp_path = temp_file.name

    logger.info("Opening auth page in browser")
    webbrowser.open(f"file://{temp_path}")
    logger.info("Auth cookie set for *.{}:{}", DEFAULT_DOMAIN_SUFFIX, DEFAULT_VHOST_HTTP_PORT)
