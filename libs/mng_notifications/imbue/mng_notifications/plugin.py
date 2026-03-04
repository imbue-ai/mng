from collections.abc import Sequence

import click

from imbue.mng import hookimpl
from imbue.mng_notifications.cli import watch


@hookimpl
def register_cli_commands() -> Sequence[click.Command] | None:
    """Register the watch command with mng."""
    return [watch]
