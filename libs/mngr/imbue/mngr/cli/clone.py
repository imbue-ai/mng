from collections.abc import Sequence

import click

from imbue.mngr.cli.create import create as create_cmd
from imbue.mngr.cli.help_formatter import CommandHelpMetadata
from imbue.mngr.cli.help_formatter import add_pager_help_option
from imbue.mngr.cli.help_formatter import register_help_metadata


@click.command(
    context_settings={"ignore_unknown_options": True},
)
@click.argument("args", nargs=-1, type=click.UNPROCESSED)
@click.pass_context
def clone(ctx: click.Context, args: tuple[str, ...]) -> None:
    """Create a new agent by cloning an existing one.

    \b
    This is a convenience wrapper around `mngr create --from-agent <source>`.
    All create options are supported.
    """
    if len(args) == 0:
        raise click.UsageError("Missing required argument: SOURCE_AGENT", ctx=ctx)

    source_agent = args[0]
    remaining = list(args[1:])

    # Reject --from-agent / --source-agent in remaining args since the source
    # is provided positionally
    _reject_source_agent_options(remaining, ctx)

    # Build the args list for the create command
    create_args = ["--from-agent", source_agent] + remaining

    # Delegate to the create command
    create_ctx = create_cmd.make_context("clone", create_args, parent=ctx)
    with create_ctx:
        create_cmd.invoke(create_ctx)


def _reject_source_agent_options(args: Sequence[str], ctx: click.Context) -> None:
    """Raise an error if --from-agent or --source-agent appears in args."""
    for arg in args:
        if arg == "--":
            break
        # Check exact match and --opt=value forms
        if arg in ("--from-agent", "--source-agent") or arg.startswith(("--from-agent=", "--source-agent=")):
            raise click.UsageError(
                f"Cannot use {arg.split('=')[0]} with clone. "
                "The source agent is specified as the first positional argument.",
                ctx=ctx,
            )


_CLONE_HELP_METADATA = CommandHelpMetadata(
    name="mngr-clone",
    one_line_description="Create a new agent by cloning an existing one",
    synopsis="mngr clone <SOURCE_AGENT> [<AGENT_NAME>] [create-options...]",
    description="""Create a new agent by cloning an existing one.

This is a convenience wrapper around `mngr create --from-agent <source>`.
The first argument is the source agent to clone from. An optional second
positional argument sets the new agent's name. All remaining arguments are
passed through to the create command.""",
    examples=(
        ("Clone an agent with auto-generated name", "mngr clone my-agent"),
        ("Clone with a specific name", "mngr clone my-agent new-agent"),
        ("Clone into a Docker container", "mngr clone my-agent --in docker"),
        ("Clone and pass args to the agent", "mngr clone my-agent -- --model opus"),
    ),
    see_also=(
        ("create", "Create an agent (full option set)"),
        ("list", "List existing agents"),
    ),
)

register_help_metadata("clone", _CLONE_HELP_METADATA)
add_pager_help_option(clone)
