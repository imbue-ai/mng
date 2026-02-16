from typing import Any

import click

from imbue.changelings.cli.common_opts import add_common_options
from imbue.changelings.cli.common_opts import setup_command_context


@click.command(name="update")
@click.argument("name", required=False)
@click.option(
    "--dry-run",
    is_flag=True,
    help="Show what would be deployed without actually deploying",
)
@add_common_options
@click.pass_context
def update(ctx: click.Context, name: str | None, dry_run: bool, **_common: Any) -> None:
    """Just an alias for `changeling add --update`"""
    setup_command_context(ctx, "update")
    raise NotImplementedError("changeling update is not yet implemented")
