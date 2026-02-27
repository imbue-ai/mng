from pathlib import Path

import click
from loguru import logger

from imbue.mng_claude_http.primitives import HttpPort
from imbue.mng_claude_http.server import run_server


@click.group()
def main() -> None:
    """Claude Code HTTP interface."""


@main.command()
@click.option("--port", type=int, default=3457, help="Port to listen on (default: 3457)")
@click.option(
    "--work-dir", type=click.Path(exists=True, path_type=Path), default=None, help="Working directory for Claude Code"
)
def serve(port: int, work_dir: Path | None) -> None:
    """Start the web server."""
    http_port = HttpPort(port)
    logger.info("Starting Claude HTTP server on http://127.0.0.1:{}", http_port)
    run_server(http_port, work_dir)


if __name__ == "__main__":
    main()
