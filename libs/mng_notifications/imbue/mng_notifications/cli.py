import click
from click_option_group import optgroup
from loguru import logger

from imbue.mng.cli.common_opts import CommonCliOptions
from imbue.mng.cli.common_opts import add_common_options
from imbue.mng.cli.common_opts import setup_command_context
from imbue.mng.cli.help_formatter import CommandHelpMetadata
from imbue.mng.cli.help_formatter import add_pager_help_option
from imbue.mng.cli.output_helpers import write_human_line
from imbue.mng.config.data_types import MngContext
from imbue.mng.primitives import PluginName
from imbue.mng_notifications.config import NotificationsPluginConfig
from imbue.mng_notifications.notifier import get_notifier
from imbue.mng_notifications.watcher import watch_for_waiting_agents


class WatchCliOptions(CommonCliOptions):
    """Options for the watch command."""

    interval: float
    include: tuple[str, ...]
    exclude: tuple[str, ...]


def _get_plugin_config(mng_ctx: MngContext) -> NotificationsPluginConfig:
    """Get the notifications plugin config, falling back to defaults."""
    config = mng_ctx.config.plugins.get(PluginName("notifications"))
    if config is not None and isinstance(config, NotificationsPluginConfig):
        return config
    return NotificationsPluginConfig()


@click.command()
@optgroup.group("Watch Options")
@optgroup.option(
    "--interval",
    "-i",
    type=float,
    default=30.0,
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

    plugin_config = _get_plugin_config(mng_ctx)

    if plugin_config.notification_only:
        write_human_line("Notification-only mode (no click-to-connect)")
    elif plugin_config.terminal_app is not None:
        write_human_line("Click-to-connect enabled (terminal: {})", plugin_config.terminal_app)
    elif plugin_config.custom_terminal_command is not None:
        write_human_line("Click-to-connect enabled (custom command)")
    else:
        write_human_line("No terminal configured -- notifications will not have click-to-connect.")
        write_human_line(
            "Set plugins.notifications.terminal_app, custom_terminal_command, or notification_only in settings.toml."
        )

    notifier = get_notifier()
    if notifier is None:
        return

    write_human_line("Watching for agents transitioning to WAITING... (Ctrl+C to stop)")

    try:
        watch_for_waiting_agents(
            mng_ctx=mng_ctx,
            interval_seconds=opts.interval,
            include_filters=opts.include,
            exclude_filters=opts.exclude,
            plugin_config=plugin_config,
            notifier=notifier,
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

On macOS, notifications are sent via terminal-notifier (install with:
brew install terminal-notifier). On Linux, via notify-send (libnotify).

To enable click-to-connect (opens a terminal tab running mng connect),
configure the plugin in settings.toml:

    [plugins.notifications]
    terminal_app = "iTerm"

Or use a custom command (MNG_AGENT_NAME_FOR_NOTIFICATIONS_PLUGIN is set in the environment):

    [plugins.notifications]
    custom_terminal_command = "my-terminal -e mng connect $MNG_AGENT_NAME_FOR_NOTIFICATIONS_PLUGIN"

Press Ctrl+C to stop watching.""",
    examples=(
        ("Watch all agents", "mng watch"),
        ("Watch with 10s interval", "mng watch --interval 10"),
        ("Watch only claude agents", "mng watch --include 'type == \"claude\"'"),
    ),
    see_also=(("list", "List agents to see their current state"),),
).register()

add_pager_help_option(watch)
