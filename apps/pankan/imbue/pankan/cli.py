from typing import Any

import click

from imbue.mng.cli.common_opts import CommonCliOptions
from imbue.mng.cli.common_opts import add_common_options
from imbue.mng.cli.common_opts import setup_command_context
from imbue.mng.cli.help_formatter import CommandHelpMetadata
from imbue.mng.cli.help_formatter import add_pager_help_option
from imbue.pankan.tui import run_pankan


class PankanCliOptions(CommonCliOptions):
    """Options for the pankan command."""


@click.command()
@add_common_options
@click.pass_context
def pankan(ctx: click.Context, **kwargs: Any) -> None:
    mng_ctx, output_opts, opts = setup_command_context(
        ctx=ctx,
        command_name="pankan",
        command_class=PankanCliOptions,
    )
    run_pankan(mng_ctx)


CommandHelpMetadata(
    key="pankan",
    one_line_description="TUI board showing agents grouped by lifecycle state with PR status",
    synopsis="mng pankan [OPTIONS]",
    description="""Launches a terminal UI that displays all mng agents organized by their
lifecycle state (RUNNING, WAITING, STOPPED, DONE, REPLACED).

Each agent shows its name, current state, and associated GitHub PR information
including PR number, state (open/closed/merged), and CI check status.

The display auto-refreshes every 10 minutes. Press 'r' to refresh manually,
or 'q' to quit.

Requires the gh CLI to be installed and authenticated for GitHub PR information.""",
    examples=(("Launch the pankan board", "mng pankan"),),
    see_also=(("list", "List agents"),),
).register()

add_pager_help_option(pankan)
