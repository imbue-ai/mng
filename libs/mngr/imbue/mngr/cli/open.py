import sys
from typing import Any

import click
from click_option_group import optgroup
from loguru import logger

from imbue.mngr.api.find import find_and_maybe_start_agent_by_name_or_id
from imbue.mngr.api.list import list_agents
from imbue.mngr.api.list import load_all_agents_grouped_by_host
from imbue.mngr.api.open import open_agent_url
from imbue.mngr.cli.common_opts import CommonCliOptions
from imbue.mngr.cli.common_opts import add_common_options
from imbue.mngr.cli.common_opts import setup_command_context
from imbue.mngr.cli.connect import select_agent_interactively
from imbue.mngr.cli.help_formatter import CommandHelpMetadata
from imbue.mngr.cli.help_formatter import add_pager_help_option
from imbue.mngr.cli.help_formatter import register_help_metadata
from imbue.mngr.errors import UserInputError
from imbue.mngr.interfaces.agent import AgentInterface


class OpenCliOptions(CommonCliOptions):
    """Options passed from the CLI to the open command.

    Inherits common options (output_format, quiet, verbose, etc.) from CommonCliOptions.
    """

    agent: str | None
    url_type: str | None
    start: bool
    wait: bool
    active: bool


@click.command(name="open")
@click.argument("agent", default=None, required=False)
@click.argument("url_type", default=None, required=False)
@optgroup.group("General")
@optgroup.option("--agent", "agent", help="The agent to open (by name or ID)")
@optgroup.option(
    "-t",
    "--type",
    "url_type",
    help="The type of URL to open (e.g., default, terminal, chat)",
)
@optgroup.option(
    "--start/--no-start",
    default=True,
    show_default=True,
    help="Automatically start the agent if stopped",
)
@optgroup.group("Options")
@optgroup.option(
    "--wait/--no-wait",
    default=False,
    show_default=True,
    help="Keep running after opening (press Ctrl+C to exit)",
)
@optgroup.option(
    "--active",
    is_flag=True,
    default=False,
    help="Continually update active timestamp while connected (prevents idle shutdown, only with --wait)",
)
@add_common_options
@click.pass_context
def open_command(ctx: click.Context, **kwargs: Any) -> None:
    """Open an agent's URL in a web browser.

    Opens the URL associated with an agent. Agents can have multiple URLs
    of different types (e.g., default, terminal, chat). Use --type to open
    a specific URL type. If no type is specified, the default URL is opened.

    Use `mngr connect` to attach to an agent via the terminal instead.

    If no agent is specified, shows an interactive selector to choose from
    available agents.
    """
    mngr_ctx, output_opts, opts = setup_command_context(
        ctx=ctx,
        command_name="open",
        command_class=OpenCliOptions,
    )

    # --active only makes sense with --wait
    if opts.active and not opts.wait:
        raise UserInputError("--active requires --wait")

    agents_by_host, _ = load_all_agents_grouped_by_host(mngr_ctx)

    agent: AgentInterface

    if opts.agent is not None:
        agent, _ = find_and_maybe_start_agent_by_name_or_id(
            opts.agent, agents_by_host, mngr_ctx, "open", is_start_desired=opts.start
        )
    elif not sys.stdin.isatty():
        # Default to most recently created agent when running non-interactively
        list_result = list_agents(mngr_ctx, is_streaming=False)
        if not list_result.agents:
            raise UserInputError("No agents found")

        sorted_agents = sorted(list_result.agents, key=lambda a: a.create_time, reverse=True)
        most_recent = sorted_agents[0]
        logger.info("No agent specified, opening most recently created: {}", most_recent.name)
        agent, _ = find_and_maybe_start_agent_by_name_or_id(
            str(most_recent.id), agents_by_host, mngr_ctx, "open", is_start_desired=opts.start
        )
    else:
        list_result = list_agents(mngr_ctx, is_streaming=False)
        if not list_result.agents:
            raise UserInputError("No agents found")

        selected = select_agent_interactively(list_result.agents)
        if selected is None:
            logger.info("No agent selected")
            return

        agent, _ = find_and_maybe_start_agent_by_name_or_id(
            str(selected.id), agents_by_host, mngr_ctx, "open", is_start_desired=opts.start
        )

    open_agent_url(
        agent=agent,
        is_wait=opts.wait,
        is_active=opts.active,
        url_type=opts.url_type,
    )


# Register help metadata for git-style help formatting
_OPEN_HELP_METADATA = CommandHelpMetadata(
    name="mngr-open",
    one_line_description="Open an agent's URL in a web browser",
    synopsis="mngr open [OPTIONS] [AGENT] [URL_TYPE]",
    description="""Open an agent's URL in a web browser.

Opens the URL associated with an agent. Agents can have multiple URLs of
different types (e.g., default, terminal, chat). Use --type to open a
specific URL type. If no type is specified, the default URL is opened.

Use `mngr connect` to attach to an agent via the terminal instead.

If no agent is specified, shows an interactive selector to choose from
available agents.

The agent and URL type can be specified as positional arguments for convenience.
The following are equivalent:
  mngr open my-agent terminal
  mngr open --agent my-agent --type terminal""",
    aliases=(),
    arguments_description="""- `AGENT`: The agent to open (by name or ID). If not specified, opens the most recently created agent
- `URL_TYPE`: The type of URL to open (e.g., `default`, `terminal`, `chat`)""",
    examples=(
        ("Open an agent's URL by name", "mngr open my-agent"),
        ("Open a specific URL type", "mngr open my-agent terminal"),
        ("Open without auto-starting if stopped", "mngr open my-agent --no-start"),
        ("Open and keep running", "mngr open my-agent --wait"),
        ("Open and keep agent active", "mngr open my-agent --wait --active"),
    ),
    see_also=(
        ("connect", "Connect to an agent via the terminal"),
        ("list", "List available agents"),
    ),
)

register_help_metadata("open", _OPEN_HELP_METADATA)

# Add pager-enabled help option to the open command
add_pager_help_option(open_command)
