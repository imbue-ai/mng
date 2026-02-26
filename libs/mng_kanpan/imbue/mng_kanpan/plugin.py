from collections.abc import Sequence

import click

from imbue.mng import hookimpl
from imbue.mng_kanpan.cli import kanpan


@hookimpl
def register_cli_commands() -> Sequence[click.Command] | None:
    """Register the kanpan command with mng."""
    return [kanpan]
