from collections.abc import Sequence

import click

from imbue.mngr import hookimpl
from imbue.mngr.config.plugin_registry import register_plugin_config
from imbue.mngr.plugins.api_server.cli import serve_command
from imbue.mngr.plugins.api_server.cli import show_token_command
from imbue.mngr.plugins.api_server.data_types import PLUGIN_NAME
from imbue.mngr.plugins.api_server.data_types import ApiServerConfig

register_plugin_config(PLUGIN_NAME, ApiServerConfig)


@hookimpl
def register_cli_commands() -> Sequence[click.Command] | None:
    """Register the 'serve' and 'token' CLI commands."""
    return [serve_command, show_token_command]
