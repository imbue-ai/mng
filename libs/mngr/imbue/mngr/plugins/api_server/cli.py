from pathlib import Path

import click
import uvicorn
from loguru import logger

from imbue.concurrency_group.concurrency_group import ConcurrencyGroup
from imbue.mngr.config.loader import load_config
from imbue.mngr.plugins.api_server.app import app
from imbue.mngr.plugins.api_server.app import configure_app
from imbue.mngr.plugins.api_server.auth import read_or_create_api_token


@click.command(name="serve")
@click.option(
    "--port",
    type=int,
    default=8000,
    help="Port to bind the API server to",
)
@click.option(
    "--host",
    type=str,
    default="0.0.0.0",
    help="Host to bind the API server to",
)
@click.option(
    "--config-dir",
    type=click.Path(path_type=Path),
    default=Path("~/.config/mngr"),
    help="Path to the mngr config directory",
)
@click.pass_context
def serve_command(ctx: click.Context, port: int, host: str, config_dir: Path) -> None:
    """Start the mngr HTTP API server locally.

    This runs the API server on the specified host and port,
    making the mngr API accessible over HTTP for mobile/remote access.
    """
    expanded_config_dir = config_dir.expanduser()
    api_token = read_or_create_api_token(expanded_config_dir)

    # ctx.obj is the PluginManager (set by the CLI entry point).
    # We need to build a full MngrContext from it via load_config.
    pm = ctx.obj
    cg = ConcurrencyGroup(name="mngr-serve")
    cg.__enter__()
    ctx.call_on_close(lambda: cg.__exit__(None, None, None))
    mngr_ctx = load_config(pm, cg)

    configure_app(mngr_ctx=mngr_ctx, api_token=api_token)

    logger.info("Starting mngr API server on {}:{}", host, port)
    logger.info("Web UI: http://{}:{}", host, port)

    uvicorn.run(app, host=host, port=port, log_level="warning")


@click.command(name="token")
@click.option(
    "--config-dir",
    type=click.Path(path_type=Path),
    default=Path("~/.config/mngr"),
    help="Path to the mngr config directory",
)
def show_token_command(config_dir: Path) -> None:
    """Print the API server authentication token."""
    expanded_config_dir = config_dir.expanduser()
    token = read_or_create_api_token(expanded_config_dir)
    click.echo(token.get_secret_value())
