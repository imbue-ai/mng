import click
from click_option_group import optgroup
from loguru import logger

from imbue.mng.cli.common_opts import CommonCliOptions
from imbue.mng.cli.common_opts import add_common_options
from imbue.mng.cli.common_opts import setup_command_context
from imbue.mng.cli.help_formatter import CommandHelpMetadata
from imbue.mng.cli.help_formatter import add_pager_help_option
from imbue.mng.cli.output_helpers import write_human_line
from imbue.mng_notifications.watcher import watch_for_waiting_agents


class WatchCliOptions(CommonCliOptions):
    """Options for the watch command."""

    interval: float
    include: tuple[str, ...]
    exclude: tuple[str, ...]


@click.command()
@optgroup.group("Watch Options")
@optgroup.option(
    "--interval",
    "-i",
    type=float,
    default=5.0,
    show_default=True,
    help="Polling interval in seconds",
)
@optgroup.group("Filtering")
@optgroup.option(
    "--include",
    multiple=True,
    help="CEL expression to include agents [repeatable]",
)
@optgroup.option(
    "--exclude",
    multiple=True,
    help="CEL expression to exclude agents [repeatable]",
)
@add_common_options
@click.pass_context
def watch(ctx: click.Context, **kwargs: object) -> None:
    mng_ctx, output_opts, opts = setup_command_context(
        ctx=ctx,
        command_name="watch",
        command_class=WatchCliOptions,
    )

    write_human_line("Watching for agents transitioning to WAITING... (Ctrl+C to stop)")

    try:
        watch_for_waiting_agents(
            mng_ctx=mng_ctx,
            interval_seconds=opts.interval,
            include_filters=opts.include,
            exclude_filters=opts.exclude,
        )
    except KeyboardInterrupt:
        logger.debug("Received keyboard interrupt")

    write_human_line("Stopped watching")


CommandHelpMetadata(
    key="watch",
    one_line_description="Watch agents and notify when they transition to WAITING",
    synopsis="mng watch [--interval <SECONDS>] [--include <EXPR>] [--exclude <EXPR>]",
    description="""Polls all agents at a regular interval and sends a desktop notification
when any agent transitions from RUNNING to WAITING state.

On macOS, notifications are sent via the Notification Center (using osascript).
On Linux, notifications are sent via notify-send (requires libnotify).

Press Ctrl+C to stop watching.""",
    examples=(
        ("Watch all agents", "mng watch"),
        ("Watch with 10s interval", "mng watch --interval 10"),
        ("Watch only claude agents", "mng watch --include 'type == \"claude\"'"),
    ),
    see_also=(("list", "List agents to see their current state"),),
).register()

add_pager_help_option(watch)
