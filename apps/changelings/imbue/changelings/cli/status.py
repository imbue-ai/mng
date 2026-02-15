from typing import Any

import click

from imbue.changelings.cli.common_opts import add_common_options
from imbue.changelings.cli.common_opts import setup_command_context


@click.command(name="status")
@click.argument("name", required=False)
@click.option(
    "--all",
    "show_all",
    is_flag=True,
    help="Show status for all deployed changelings",
)
@add_common_options
@click.pass_context
def status(ctx: click.Context, name: str | None, show_all: bool, **_common: Any) -> None:
    """Check the deployment status and recent run history of changeling(s).

    Shows whether the changeling is deployed, when it last ran, and the
    outcome of recent runs (success, failure, PR created, etc).

    Examples:

      changeling status my-fairy

      changeling status --all
    """
    setup_command_context(ctx, "status")
    raise NotImplementedError("changeling status is not yet implemented")
