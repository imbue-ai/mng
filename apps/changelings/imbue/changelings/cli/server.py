import sys
from pathlib import Path

import click

from imbue.changelings.config.data_types import DEFAULT_FORWARDING_SERVER_HOST
from imbue.changelings.config.data_types import DEFAULT_FORWARDING_SERVER_PORT
from imbue.changelings.config.data_types import get_default_data_dir
from imbue.changelings.forwarding_server.runner import start_forwarding_server


def _write_line(message: str) -> None:
    """Write a line to stdout."""
    sys.stdout.write(message + "\n")
    sys.stdout.flush()


@click.command()
@click.option(
    "--host",
    default=DEFAULT_FORWARDING_SERVER_HOST,
    show_default=True,
    help="Host to bind the forwarding server to",
)
@click.option(
    "--port",
    default=DEFAULT_FORWARDING_SERVER_PORT,
    show_default=True,
    help="Port to bind the forwarding server to",
)
@click.option(
    "--data-dir",
    type=click.Path(resolve_path=True),
    default=None,
    help="Data directory for changelings state (default: ~/.changelings)",
)
def server(host: str, port: int, data_dir: str | None) -> None:
    """Start the local forwarding server.

    The forwarding server handles authentication and proxies web traffic
    to individual changeling web servers.
    """
    data_directory = Path(data_dir) if data_dir else get_default_data_dir()

    _write_line("Starting changelings forwarding server...")
    _write_line("  Listening on: http://{}:{}".format(host, port))
    _write_line("  Data directory: {}".format(data_directory))
    _write_line("")
    _write_line("Press Ctrl+C to stop.")
    _write_line("")

    start_forwarding_server(
        data_directory=data_directory,
        host=host,
        port=port,
    )
