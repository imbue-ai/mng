import sys

import click
from loguru import logger

from imbue.concurrency_group.concurrency_group import ConcurrencyGroup
from imbue.imbue_common.pure import pure
from imbue.mngr.api.list import list_agents
from imbue.mngr.cli.clone import args_before_dd_count
from imbue.mngr.cli.clone import has_name_in_remaining_args
from imbue.mngr.cli.clone import parse_source_and_invoke_create
from imbue.mngr.cli.connect import connect as connect_cmd
from imbue.mngr.cli.destroy import destroy as destroy_cmd
from imbue.mngr.cli.help_formatter import CommandHelpMetadata
from imbue.mngr.cli.help_formatter import add_pager_help_option
from imbue.mngr.cli.help_formatter import register_help_metadata
from imbue.mngr.config.loader import load_config
from imbue.mngr.errors import UserInputError
from imbue.mngr.primitives import AgentId


@pure
def _user_specified_no_connect(args: tuple[str, ...]) -> bool:
    """Check if the user explicitly passed --no-connect in their args."""
    return "--no-connect" in args


@pure
def _user_specified_quiet(args: tuple[str, ...]) -> bool:
    """Check if the user explicitly passed --quiet or -q in their args."""
    return "--quiet" in args or "-q" in args


def _resolve_source_agent_id(ctx: click.Context, source_agent: str) -> AgentId:
    """Resolve the source agent name or ID to a unique AgentId.

    Loads config and lists all agents to find a match by name or ID.
    This ensures destroy targets only the specific source agent, avoiding
    collisions when the cloned agent shares the same name.
    """
    pm = ctx.obj
    with ConcurrencyGroup(name="mngr-migrate-resolve") as cg:
        mngr_ctx = load_config(pm, cg)
        result = list_agents(mngr_ctx, is_streaming=False)

    for agent_info in result.agents:
        if str(agent_info.name) == source_agent or str(agent_info.id) == source_agent:
            return agent_info.id

    raise UserInputError(f"Source agent '{source_agent}' not found")


@pure
def _build_destroy_args(source_agent_id: AgentId) -> list[str]:
    """Build the argument list for destroying the source agent during migrate.

    Uses the agent ID (not name) to avoid destroying a newly cloned agent
    that shares the same name. Always passes --quiet and --no-gc to suppress
    alarming destroy output during migrate.
    """
    return [str(source_agent_id), "--force", "--quiet", "--no-gc"]


@pure
def _determine_new_agent_name(
    source_agent: str,
    remaining: list[str],
    original_argv: list[str],
) -> str:
    """Determine the new agent's name from the args.

    Uses the same logic as _build_create_args: if a name is present in
    remaining args (positional or --name), the create command will use it.
    Otherwise, the source agent name is forwarded.
    """
    before_dd_count = args_before_dd_count(remaining, original_argv)
    has_name = has_name_in_remaining_args(remaining, before_dd_count)

    if not has_name:
        return source_agent

    check = remaining if before_dd_count is None else remaining[:before_dd_count]

    # Check for --name or -n flag
    for i, arg in enumerate(check):
        if arg in ("--name", "-n") and i + 1 < len(check):
            return check[i + 1]
        if arg.startswith("--name="):
            return arg.split("=", 1)[1]
        if arg.startswith("-n="):
            return arg.split("=", 1)[1]

    # First positional arg (not starting with -)
    if check and not check[0].startswith("-"):
        return check[0]

    return source_agent


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

    When connecting (the default), the source agent is destroyed as soon as
    the clone is ready, before attaching to the new agent's session.
    """
    if len(args) == 0:
        raise click.UsageError("Missing required argument: SOURCE_AGENT", ctx=ctx)

    source_agent = args[0]
    remaining = list(args[1:])
    original_argv = sys.argv

    # Determine if the user wants to connect (the default).
    # If they do, we inject --no-connect so that create returns after the
    # agent is ready, then we destroy the source, then connect manually.
    wants_connect = not _user_specified_no_connect(args)
    is_quiet = _user_specified_quiet(args)

    # Resolve the source agent's unique ID before cloning, so that
    # destroy targets only this specific agent (not a newly cloned agent
    # that may share the same name).
    source_agent_id = _resolve_source_agent_id(ctx, source_agent)

    if wants_connect:
        create_args = args + ("--no-connect", "--await-ready")
    else:
        create_args = args

    parse_source_and_invoke_create(ctx, create_args, command_name="migrate")

    # Destroy the source agent by ID with --force.
    # Always pass --quiet and --no-gc to suppress alarming destroy output
    # during migrate (users see migrate-appropriate messages instead).
    if not is_quiet:
        logger.info("Cleaning up source agent...")

    destroy_args = _build_destroy_args(source_agent_id)
    try:
        destroy_ctx = destroy_cmd.make_context("migrate-destroy", destroy_args, parent=ctx)
        with destroy_ctx:
            destroy_cmd.invoke(destroy_ctx)
    except (click.Abort, click.ClickException):
        logger.error(
            "Clone succeeded but destroy of '{}' failed. "
            "Please manually destroy the source agent:\n"
            "  mngr destroy --force {}",
            source_agent,
            source_agent,
        )
        raise

    # Connect to the new agent if the user wanted to connect
    if wants_connect:
        new_agent_name = _determine_new_agent_name(source_agent, remaining, original_argv)
        connect_ctx = connect_cmd.make_context("migrate-connect", [new_agent_name], parent=ctx)
        with connect_ctx:
            connect_cmd.invoke(connect_ctx)


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
