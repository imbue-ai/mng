from typing import Any

import click

from imbue.changelings.cli.common_opts import add_common_options
from imbue.changelings.cli.common_opts import setup_command_context


@click.command(name="remove")
@click.argument("name")
@click.option(
    "--force",
    is_flag=True,
    help="Skip confirmation and also undeploy from Modal if deployed",
)
@add_common_options
@click.pass_context
def remove(ctx: click.Context, name: str, force: bool, **_common: Any) -> None:
    """Remove a registered changeling.

    This removes the changeling from the local configuration. If the changeling
    is currently deployed to Modal, use --force to also undeploy it.

    Examples:

      changeling remove my-fairy

      changeling remove my-fairy --force
    """
    setup_command_context(ctx, "remove")
    raise NotImplementedError("changeling remove is not yet implemented")
