from collections.abc import Sequence

import click

from imbue.mng import hookimpl
from imbue.mng_schedule.cli import schedule


@hookimpl
def register_cli_commands() -> Sequence[click.Command] | None:
    """Register the schedule command with mng."""
    return [schedule]
