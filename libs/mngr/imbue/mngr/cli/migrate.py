import click

from imbue.mngr.cli.clone import reject_source_agent_options
from imbue.mngr.cli.create import create as create_cmd
from imbue.mngr.cli.destroy import destroy as destroy_cmd
from imbue.mngr.cli.help_formatter import CommandHelpMetadata
from imbue.mngr.cli.help_formatter import add_pager_help_option
from imbue.mngr.cli.help_formatter import register_help_metadata


@click.command(
    context_settings={"ignore_unknown_options": True},
)
@click.argument("args", nargs=-1, type=click.UNPROCESSED)
@click.pass_context
def migrate(ctx: click.Context, args: tuple[str, ...]) -> None:
    """Move an agent to a different host by cloning it and destroying the original.

    \b
    This is equivalent to running `mngr clone` followed by `mngr destroy --force`.
    All create options are supported. The source agent is force-destroyed after
    a successful clone (including running agents).
    """
    if len(args) == 0:
        raise click.UsageError("Missing required argument: SOURCE_AGENT", ctx=ctx)

    source_agent = args[0]
    remaining = list(args[1:])

    # Reject --from-agent / --source-agent in remaining args since the source
    # is provided positionally
    reject_source_agent_options(remaining, ctx)

    # Step 1: Clone via the create command
    create_args = ["--from-agent", source_agent] + remaining

    create_ctx = create_cmd.make_context("migrate", create_args, parent=ctx)
    with create_ctx:
        create_cmd.invoke(create_ctx)

    # Step 2: Destroy the source agent with --force
    destroy_args = [source_agent, "--force"]

    destroy_ctx = destroy_cmd.make_context("migrate-destroy", destroy_args, parent=ctx)
    with destroy_ctx:
        destroy_cmd.invoke(destroy_ctx)


_MIGRATE_HELP_METADATA = CommandHelpMetadata(
    name="mngr-migrate",
    one_line_description="Move an agent to a different host",
    synopsis="mngr migrate <SOURCE_AGENT> [<AGENT_NAME>] [create-options...]",
    description="""Move an agent to a different host by cloning it and destroying the original.

This is equivalent to running `mngr clone <source>` followed by
`mngr destroy --force <source>`. The first argument is the source agent to
migrate. An optional second positional argument sets the new agent's name.
All remaining arguments are passed through to the create command.

The source agent is always force-destroyed after a successful clone. If the
clone step fails, the source agent is left untouched. If the destroy step
fails after a successful clone, the error is reported and the user can
manually clean up.""",
    examples=(
        ("Migrate an agent to a Docker container", "mngr migrate my-agent --in docker"),
        ("Migrate with a new name", "mngr migrate my-agent new-agent --in modal"),
        ("Migrate and pass args to the agent", "mngr migrate my-agent -- --model opus"),
    ),
    see_also=(
        ("clone", "Clone an agent (without destroying the original)"),
        ("create", "Create an agent (full option set)"),
        ("destroy", "Destroy an agent"),
    ),
)

register_help_metadata("migrate", _MIGRATE_HELP_METADATA)
add_pager_help_option(migrate)
