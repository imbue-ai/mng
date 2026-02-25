from collections.abc import Sequence

import click

from imbue.mng import hookimpl
from imbue.pankan.cli import pankan


@hookimpl
def register_cli_commands() -> Sequence[click.Command] | None:
    """Register the pankan command with mng."""
    return [pankan]
