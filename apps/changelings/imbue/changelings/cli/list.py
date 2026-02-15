from typing import Any

import click

from imbue.changelings.cli.common_opts import add_common_options
from imbue.changelings.cli.common_opts import setup_command_context


@click.command(name="list")
@click.option(
    "--all",
    "show_all",
    is_flag=True,
    help="Show disabled changelings as well",
)
@add_common_options
@click.pass_context
def list_command(ctx: click.Context, show_all: bool, **_common: Any) -> None:
    """List all registered changelings.

    Shows each changeling's name, agent type, schedule, target repo, and status.

    Examples:

      changeling list

      changeling list --all

      changeling list --format json
    """
    setup_command_context(ctx, "list")
    raise NotImplementedError("changeling list is not yet implemented")
