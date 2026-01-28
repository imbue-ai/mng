import sys
from pathlib import Path
from typing import assert_never

import click
from click_option_group import optgroup
from loguru import logger

from imbue.mngr.api.find import find_agent_by_name_or_id
from imbue.mngr.api.find import load_all_agents_grouped_by_host
from imbue.mngr.api.list import list_agents
from imbue.mngr.api.pull import PullResult
from imbue.mngr.api.pull import pull_files
from imbue.mngr.cli.common_opts import CommonCliOptions
from imbue.mngr.cli.common_opts import add_common_options
from imbue.mngr.cli.common_opts import setup_command_context
from imbue.mngr.cli.connect import select_agent_interactively
from imbue.mngr.cli.help_formatter import CommandHelpMetadata
from imbue.mngr.cli.help_formatter import add_pager_help_option
from imbue.mngr.cli.help_formatter import register_help_metadata
from imbue.mngr.cli.output_helpers import emit_event
from imbue.mngr.cli.output_helpers import emit_final_json
from imbue.mngr.cli.output_helpers import emit_info
from imbue.mngr.config.data_types import MngrContext
from imbue.mngr.config.data_types import OutputOptions
from imbue.mngr.errors import UserInputError
from imbue.mngr.interfaces.agent import AgentInterface
from imbue.mngr.interfaces.host import HostInterface
from imbue.mngr.primitives import OutputFormat


class PullCliOptions(CommonCliOptions):
    """Options passed from the CLI to the pull command.

    Inherits common options (output_format, quiet, verbose, etc.) from CommonCliOptions.
    """

    source: str | None
    source_agent: str | None
    source_host: str | None
    source_path: str | None
    destination: str | None
    dry_run: bool
    stop: bool
    delete: bool
    sync_mode: str
    exclude: tuple[str, ...]


def _select_agent_for_pull(mngr_ctx: MngrContext) -> tuple[AgentInterface, HostInterface] | None:
    """Show interactive UI to select an agent for pulling.

    Returns tuple of (agent, host) or None if user quit without selecting.
    """
    list_result = list_agents(mngr_ctx)
    if not list_result.agents:
        raise UserInputError("No agents found")

    selected = select_agent_interactively(list_result.agents)
    if selected is None:
        return None

    # Find the actual agent and host from the selection
    agents_by_host = load_all_agents_grouped_by_host(mngr_ctx)
    return find_agent_by_name_or_id(str(selected.id), agents_by_host, mngr_ctx, "pull")


def _output_result(result: PullResult, output_opts: OutputOptions) -> None:
    """Output the pull result in the appropriate format."""
    result_data = {
        "files_transferred": result.files_transferred,
        "bytes_transferred": result.bytes_transferred,
        "source_path": str(result.source_path),
        "destination_path": str(result.destination_path),
        "is_dry_run": result.is_dry_run,
    }
    match output_opts.output_format:
        case OutputFormat.JSON:
            emit_final_json(result_data)
        case OutputFormat.JSONL:
            emit_event("pull_complete", result_data, OutputFormat.JSONL)
        case OutputFormat.HUMAN:
            if result.is_dry_run:
                logger.info("Dry run complete: {} files would be transferred", result.files_transferred)
            else:
                logger.info(
                    "Pull complete: {} files, {} bytes transferred",
                    result.files_transferred,
                    result.bytes_transferred,
                )
        case _ as unreachable:
            assert_never(unreachable)


@click.command()
@click.argument("source", default=None, required=False)
@click.argument("destination", default=None, required=False)
@optgroup.group("Source Selection")
@optgroup.option("--source", "source", help="Source specification: AGENT, AGENT:PATH, or PATH")
@optgroup.option("--source-agent", help="Source agent name or ID")
@optgroup.option("--source-host", help="Source host name or ID")
@optgroup.option("--source-path", help="Path within the agent's work directory")
@optgroup.group("Destination")
@optgroup.option("--destination", "destination", type=click.Path(), help="Local destination directory [default: .]")
@optgroup.group("Sync Options")
@optgroup.option(
    "--dry-run",
    is_flag=True,
    default=False,
    help="Show what would be transferred without actually transferring",
)
@optgroup.option(
    "--stop",
    is_flag=True,
    default=False,
    help="Stop the agent after pulling (for state consistency)",
)
@optgroup.option(
    "--delete/--no-delete",
    default=False,
    help="Delete files in destination that don't exist in source",
)
@optgroup.option(
    "--sync-mode",
    type=click.Choice(["files", "state", "full"], case_sensitive=False),
    default="files",
    show_default=True,
    help="What to sync: files (working directory only), state (agent state), or full (everything)",
)
@optgroup.option(
    "--exclude",
    multiple=True,
    help="Patterns to exclude from sync [repeatable]",
)
@add_common_options
@click.pass_context
def pull(ctx: click.Context, **kwargs) -> None:
    """Pull files from an agent to local machine.

    Syncs files from an agent's working directory to a local directory.
    Default behavior uses rsync for efficient incremental file transfer.

    If no source is specified, shows an interactive selector to choose an agent.

    \b
    Examples:
      mngr pull my-agent
      mngr pull my-agent ./local-copy
      mngr pull my-agent:src ./local-src
      mngr pull --source-agent my-agent
    """
    mngr_ctx, output_opts, opts = setup_command_context(
        ctx=ctx,
        command_name="pull",
        command_class=PullCliOptions,
    )
    logger.debug("Running pull command")

    # Check for unsupported options
    if opts.sync_mode != "files":
        raise NotImplementedError(f"--sync-mode={opts.sync_mode} is not implemented yet (only 'files' is supported)")

    if opts.exclude:
        raise NotImplementedError("--exclude is not implemented yet")

    if opts.source_host is not None:
        raise NotImplementedError("--source-host is not implemented yet (only local agents are supported)")

    # Parse source specification
    agent_identifier: str | None = None
    source_path: str | None = opts.source_path

    if opts.source is not None:
        # Parse source string: AGENT, AGENT:PATH, or PATH
        if ":" in opts.source:
            # AGENT:PATH format
            agent_identifier, source_path = opts.source.split(":", 1)
        elif opts.source.startswith(("/", "./", "~/", "../")):
            # PATH format - not supported without agent
            raise UserInputError("Source must include an agent specification")
        else:
            # AGENT format
            agent_identifier = opts.source

    # Override with explicit options if provided
    if opts.source_agent is not None:
        if agent_identifier is not None and agent_identifier != opts.source_agent:
            raise UserInputError("Cannot specify both --source and --source-agent with different values")
        agent_identifier = opts.source_agent

    # Determine destination
    destination_path = Path(opts.destination) if opts.destination else Path.cwd()

    # Find the agent
    agent: AgentInterface
    host: HostInterface

    if agent_identifier is not None:
        agents_by_host = load_all_agents_grouped_by_host(mngr_ctx)
        agent, host = find_agent_by_name_or_id(agent_identifier, agents_by_host, mngr_ctx, "pull <agent-id> <path>")
    elif not sys.stdin.isatty():
        raise UserInputError("No agent specified and not running in interactive mode")
    else:
        # Interactive agent selection
        result = _select_agent_for_pull(mngr_ctx)
        if result is None:
            logger.info("No agent selected")
            return
        agent, host = result

    # Only local agents are supported right now
    if not host.is_local:
        raise NotImplementedError("Pulling from remote agents is not implemented yet")

    emit_info(f"Pulling from agent: {agent.name}", output_opts.output_format)

    # Parse source_path if provided
    parsed_source_path: Path | None = None
    if source_path is not None:
        # If source_path is relative, make it relative to agent's work_dir
        parsed_path = Path(source_path)
        if parsed_path.is_absolute():
            parsed_source_path = parsed_path
        else:
            parsed_source_path = agent.work_dir / parsed_path

    # Perform the pull
    pull_result = pull_files(
        agent=agent,
        host=host,
        destination=destination_path,
        source_path=parsed_source_path,
        dry_run=opts.dry_run,
        delete=opts.delete,
    )

    # Stop agent if requested
    if opts.stop:
        emit_info(f"Stopping agent: {agent.name}", output_opts.output_format)
        host.stop_agents([agent.id])
        emit_info("Agent stopped", output_opts.output_format)

    _output_result(pull_result, output_opts)


# Register help metadata for git-style help formatting
_PULL_HELP_METADATA = CommandHelpMetadata(
    name="mngr-pull",
    one_line_description="Pull files from an agent to local machine",
    synopsis="mngr pull [SOURCE] [DESTINATION] [--source-agent <AGENT>] [--dry-run] [--stop]",
    description="""Pull files from an agent to local machine.

Syncs files from an agent's working directory to a local directory.
Default behavior uses rsync for efficient incremental file transfer.

If no source is specified, shows an interactive selector to choose an agent.

Note: Only file sync (--sync-mode=files) is currently implemented. Git sync
and agent-to-agent sync are planned for future releases. See
specs/commands/pull.md for the full planned feature set.""",
    examples=(
        ("Pull from agent to current directory", "mngr pull my-agent"),
        ("Pull to specific local directory", "mngr pull my-agent ./local-copy"),
        ("Pull specific subdirectory", "mngr pull my-agent:src ./local-src"),
        ("Preview what would be transferred", "mngr pull my-agent --dry-run"),
    ),
    see_also=(
        ("create", "Create a new agent"),
        ("list", "List agents to find one to pull from"),
        ("connect", "Connect to an agent interactively"),
    ),
)

register_help_metadata("pull", _PULL_HELP_METADATA)

# Add pager-enabled help option to the pull command
add_pager_help_option(pull)
