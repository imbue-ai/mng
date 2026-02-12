from typing import Any
from typing import assert_never

import click
from click_option_group import optgroup
from loguru import logger

from imbue.mngr.api.list import list_agents
from imbue.mngr.api.list import load_all_agents_grouped_by_host
from imbue.mngr.api.providers import get_provider_instance
from imbue.mngr.cli.common_opts import CommonCliOptions
from imbue.mngr.cli.common_opts import add_common_options
from imbue.mngr.cli.common_opts import setup_command_context
from imbue.mngr.cli.help_formatter import CommandHelpMetadata
from imbue.mngr.cli.help_formatter import add_pager_help_option
from imbue.mngr.cli.help_formatter import register_help_metadata
from imbue.mngr.cli.output_helpers import emit_event
from imbue.mngr.cli.output_helpers import emit_final_json
from imbue.mngr.config.data_types import MngrContext
from imbue.mngr.config.data_types import OutputOptions
from imbue.mngr.errors import UserInputError
from imbue.mngr.interfaces.agent import AgentInterface
from imbue.mngr.interfaces.host import OnlineHostInterface
from imbue.mngr.primitives import AgentId
from imbue.mngr.primitives import AgentName
from imbue.mngr.primitives import OutputFormat


class RenameCliOptions(CommonCliOptions):
    """Options passed from the CLI to the rename command."""

    current: str
    new_name: str
    dry_run: bool
    # Planned features (not yet implemented)
    host: bool


def _find_agent_without_starting(
    mngr_ctx: MngrContext,
    agent_identifier: str,
) -> tuple[AgentInterface, OnlineHostInterface]:
    """Find an agent by name or ID without attempting to start it.

    Unlike find_agent_for_command, this does not call ensure_agent_started,
    so it works for both running and stopped agents.
    """
    agents_by_host, _ = load_all_agents_grouped_by_host(mngr_ctx)

    # Try parsing as an AgentId first
    try:
        agent_id = AgentId(agent_identifier)
    except ValueError:
        agent_id = None

    matching: list[tuple[AgentInterface, OnlineHostInterface]] = []

    for host_ref, agent_refs in agents_by_host.items():
        for agent_ref in agent_refs:
            is_match = (agent_id is not None and agent_ref.agent_id == agent_id) or (
                agent_id is None and agent_ref.agent_name == AgentName(agent_identifier)
            )
            if is_match:
                provider = get_provider_instance(host_ref.provider_name, mngr_ctx)
                host = provider.get_host(host_ref.host_id)
                if not isinstance(host, OnlineHostInterface):
                    raise UserInputError(
                        f"Host '{host_ref.host_id}' is offline. Cannot rename agents on offline hosts."
                    )
                for agent in host.get_agents():
                    if agent.id == agent_ref.agent_id:
                        matching.append((agent, host))
                        break

    if not matching:
        raise UserInputError(f"No agent found with name or ID: {agent_identifier}")

    if len(matching) > 1:
        agent_list = "\n".join([f"  - {agent.id} (on {host.get_name()})" for agent, host in matching])
        raise UserInputError(
            f"Multiple agents found with name '{agent_identifier}':\n{agent_list}\n\n"
            f"Please use the agent ID instead:\n"
            f"  mngr rename <agent-id> <new-name>"
        )

    return matching[0]


def _output(message: str, output_opts: OutputOptions) -> None:
    """Output a message according to the format."""
    if output_opts.output_format == OutputFormat.HUMAN:
        logger.info(message)


def _output_result(
    old_name: str,
    new_name: str,
    agent_id: str,
    output_opts: OutputOptions,
) -> None:
    """Output the final result."""
    result_data = {
        "old_name": old_name,
        "new_name": new_name,
        "agent_id": agent_id,
    }
    match output_opts.output_format:
        case OutputFormat.JSON:
            emit_final_json(result_data)
        case OutputFormat.JSONL:
            emit_event("rename_result", result_data, OutputFormat.JSONL)
        case OutputFormat.HUMAN:
            logger.info("Renamed agent: {} -> {}", old_name, new_name)
        case _ as unreachable:
            assert_never(unreachable)


@click.command(name="rename")
@click.argument("current")
@click.argument("new_name", metavar="NEW-NAME")
@optgroup.group("Behavior")
@optgroup.option(
    "--dry-run",
    is_flag=True,
    help="Show what would be renamed without actually renaming",
)
@optgroup.option(
    "--host",
    is_flag=True,
    help="Rename a host instead of an agent [future]",
)
@add_common_options
@click.pass_context
def rename(ctx: click.Context, **kwargs: Any) -> None:
    """Rename an agent or host.

    Renames the agent's data.json and tmux session (if running).
    Git branch names are not renamed.

    If a previous rename was interrupted, re-running the command
    will attempt to finish it.

    \b
    Alias: mv

    \b
    Examples:

      mngr rename my-agent new-name

      mngr rename my-agent new-name --dry-run
    """
    mngr_ctx, output_opts, opts = setup_command_context(
        ctx=ctx,
        command_name="rename",
        command_class=RenameCliOptions,
    )
    logger.debug("Started rename command")

    # Check for unsupported [future] options
    if opts.host:
        raise NotImplementedError("--host is not implemented yet. Currently only agent renaming is supported.")

    # Validate new name
    try:
        new_agent_name = AgentName(opts.new_name)
    except ValueError as e:
        raise UserInputError(f"Invalid new name: {e}") from None

    # Resolve the agent (without starting it)
    agent, host = _find_agent_without_starting(mngr_ctx, opts.current)

    old_name = str(agent.name)

    # Check if the name is actually changing
    if agent.name == new_agent_name:
        _output(f"Agent already named: {new_agent_name}", output_opts)
        return

    # Check for name conflicts
    existing_agents = list_agents(mngr_ctx, is_streaming=False)
    for existing_agent in existing_agents.agents:
        if existing_agent.name == new_agent_name and existing_agent.id != agent.id:
            raise UserInputError(f"An agent named '{new_agent_name}' already exists (ID: {existing_agent.id})")

    # Handle dry-run mode
    if opts.dry_run:
        _output(f"Would rename agent: {old_name} -> {new_agent_name}", output_opts)
        return

    # Perform the rename
    updated_agent = host.rename_agent(agent, new_agent_name)

    # Warn that the git branch was not renamed (only in human output mode)
    if output_opts.output_format == OutputFormat.HUMAN:
        logger.warning("Note: the git branch name was not changed. You may want to rename it manually.")

    # Output the result
    _output_result(
        old_name=old_name,
        new_name=str(updated_agent.name),
        agent_id=str(updated_agent.id),
        output_opts=output_opts,
    )


# Register help metadata for git-style help formatting
_RENAME_HELP_METADATA = CommandHelpMetadata(
    name="mngr-rename",
    one_line_description="Rename an agent or host",
    synopsis="mngr [rename|mv] <CURRENT> <NEW-NAME> [--dry-run] [--host]",
    arguments_description="- `CURRENT`: Current name or ID of the agent to rename\n- `NEW-NAME`: New name for the agent",
    description="""Rename an agent or host.

Updates the agent's name in its data.json and renames the tmux session
if the agent is currently running. Git branch names are not renamed.

If a previous rename was interrupted (e.g., the tmux session was renamed
but data.json was not updated), re-running the command will attempt
to complete it.""",
    aliases=("mv",),
    examples=(
        ("Rename an agent", "mngr rename my-agent new-name"),
        ("Preview what would be renamed", "mngr rename my-agent new-name --dry-run"),
        ("Use the alias", "mngr mv my-agent new-name"),
    ),
    see_also=(
        ("list", "List existing agents"),
        ("create", "Create a new agent"),
        ("destroy", "Destroy an agent"),
    ),
)

register_help_metadata("rename", _RENAME_HELP_METADATA)
# Also register under alias for consistent help output
for alias in _RENAME_HELP_METADATA.aliases:
    register_help_metadata(alias, _RENAME_HELP_METADATA)

# Add pager-enabled help option to the rename command
add_pager_help_option(rename)
