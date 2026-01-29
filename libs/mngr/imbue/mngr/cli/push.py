"""CLI implementation for the push command."""

import sys
from pathlib import Path
from typing import assert_never

import click
from click_option_group import optgroup
from loguru import logger

from imbue.mngr.api.find import load_all_agents_grouped_by_host
from imbue.mngr.api.list import list_agents
from imbue.mngr.api.providers import get_provider_instance
from imbue.mngr.api.push import PushGitResult
from imbue.mngr.api.push import PushResult
from imbue.mngr.api.push import push_files
from imbue.mngr.api.push import push_git
from imbue.mngr.cli.common_opts import CommonCliOptions
from imbue.mngr.cli.common_opts import add_common_options
from imbue.mngr.cli.common_opts import setup_command_context
from imbue.mngr.cli.connect import select_agent_interactively
from imbue.mngr.cli.output_helpers import emit_event
from imbue.mngr.cli.output_helpers import emit_final_json
from imbue.mngr.cli.output_helpers import emit_info
from imbue.mngr.config.data_types import MngrContext
from imbue.mngr.config.data_types import OutputOptions
from imbue.mngr.errors import AgentNotFoundError
from imbue.mngr.errors import UserInputError
from imbue.mngr.interfaces.agent import AgentInterface
from imbue.mngr.interfaces.host import HostInterface
from imbue.mngr.primitives import AgentId
from imbue.mngr.primitives import AgentName
from imbue.mngr.primitives import AgentReference
from imbue.mngr.primitives import HostReference
from imbue.mngr.primitives import OutputFormat
from imbue.mngr.primitives import UncommittedChangesMode


class PushCliOptions(CommonCliOptions):
    """Options passed from the CLI to the push command.

    Inherits common options (output_format, quiet, verbose, etc.) from CommonCliOptions.
    """

    target: str | None
    target_agent: str | None
    target_host: str | None
    target_path: str | None
    source: str | None
    dry_run: bool
    stop: bool
    delete: bool
    sync_mode: str
    exclude: tuple[str, ...]
    uncommitted_changes: str
    source_branch: str | None
    mirror: bool


def _find_agent_by_name_or_id(
    agent_str: str,
    agents_by_host: dict[HostReference, list[AgentReference]],
    mngr_ctx: MngrContext,
) -> tuple[AgentInterface, HostInterface]:
    """Find an agent by name or ID.

    Returns tuple of (agent, host) or raises AgentNotFoundError.
    """
    # Try parsing as an AgentId first
    try:
        agent_id = AgentId(agent_str)
        # Search for the agent by ID
        for host_ref, agent_refs in agents_by_host.items():
            for agent_ref in agent_refs:
                if agent_ref.agent_id == agent_id:
                    provider = get_provider_instance(host_ref.provider_name, mngr_ctx)
                    host = provider.get_host(host_ref.host_id)
                    for agent in host.get_agents():
                        if agent.id == agent_id:
                            return agent, host
        raise AgentNotFoundError(agent_id)
    except ValueError:
        pass

    # Try matching by name
    agent_name = AgentName(agent_str)
    matching: list[tuple[AgentInterface, HostInterface]] = []

    for host_ref, agent_refs in agents_by_host.items():
        for agent_ref in agent_refs:
            if agent_ref.agent_name == agent_name:
                provider = get_provider_instance(host_ref.provider_name, mngr_ctx)
                host = provider.get_host(host_ref.host_id)
                for agent in host.get_agents():
                    if agent.name == agent_name:
                        matching.append((agent, host))

    if not matching:
        raise UserInputError(f"No agent found with name or ID: {agent_str}")

    if len(matching) > 1:
        raise UserInputError(
            f"Multiple agents found with name '{agent_str}'. Please use the agent ID instead, or specify the host."
        )

    return matching[0]


def _select_agent_for_push(mngr_ctx: MngrContext) -> tuple[AgentInterface, HostInterface] | None:
    """Show interactive UI to select an agent for pushing.

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
    return _find_agent_by_name_or_id(str(selected.id), agents_by_host, mngr_ctx)


def _output_files_result(result: PushResult, output_opts: OutputOptions) -> None:
    """Output the push files result in the appropriate format."""
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
            emit_event("push_complete", result_data, OutputFormat.JSONL)
        case OutputFormat.HUMAN:
            if result.is_dry_run:
                logger.info("Dry run complete: {} files would be transferred", result.files_transferred)
            else:
                logger.info(
                    "Push complete: {} files, {} bytes transferred",
                    result.files_transferred,
                    result.bytes_transferred,
                )
        case _ as unreachable:
            assert_never(unreachable)


def _output_git_result(result: PushGitResult, output_opts: OutputOptions) -> None:
    """Output the push git result in the appropriate format."""
    result_data = {
        "source_branch": result.source_branch,
        "target_branch": result.target_branch,
        "source_path": str(result.source_path),
        "destination_path": str(result.destination_path),
        "is_dry_run": result.is_dry_run,
        "commits_pushed": result.commits_pushed,
    }
    match output_opts.output_format:
        case OutputFormat.JSON:
            emit_final_json(result_data)
        case OutputFormat.JSONL:
            emit_event("push_git_complete", result_data, OutputFormat.JSONL)
        case OutputFormat.HUMAN:
            if result.is_dry_run:
                logger.info(
                    "Dry run complete: would push {} commits from {} into {}",
                    result.commits_pushed,
                    result.source_branch,
                    result.target_branch,
                )
            else:
                logger.info(
                    "Git push complete: pushed {} commits from {} into {}",
                    result.commits_pushed,
                    result.source_branch,
                    result.target_branch,
                )
        case _ as unreachable:
            assert_never(unreachable)


@click.command()
@click.argument("target", default=None, required=False)
@click.argument("source", default=None, required=False)
@optgroup.group("Target Selection")
@optgroup.option("--target", "target", help="Target specification: AGENT, AGENT:PATH, or PATH")
@optgroup.option("--target-agent", help="Target agent name or ID")
@optgroup.option("--target-host", help="Target host name or ID")
@optgroup.option("--target-path", help="Path within the agent's work directory")
@optgroup.group("Source")
@optgroup.option("--source", "source", type=click.Path(exists=True), help="Local source directory [default: .]")
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
    help="Stop the agent after pushing (for state consistency)",
)
@optgroup.option(
    "--delete/--no-delete",
    default=False,
    help="Delete files in destination that don't exist in source",
)
@optgroup.option(
    "--sync-mode",
    type=click.Choice(["files", "git", "full"], case_sensitive=False),
    default="files",
    show_default=True,
    help="What to sync: files (working directory via rsync), git (merge git branches), or full (everything)",
)
@optgroup.option(
    "--exclude",
    multiple=True,
    help="Patterns to exclude from sync [repeatable]",
)
@optgroup.option(
    "--source-branch",
    help="Branch to push from (git mode only) [default: current branch]",
)
@optgroup.option(
    "--mirror/--no-mirror",
    default=False,
    help="Use git push --mirror (dangerous - replaces all refs in agent repo)",
)
@optgroup.option(
    "--uncommitted-changes",
    type=click.Choice(["stash", "clobber", "merge", "fail"], case_sensitive=False),
    default="fail",
    show_default=True,
    help="How to handle uncommitted changes in the agent: stash (stash and leave stashed), clobber (overwrite), merge (stash, push, unstash), fail (error if changes exist)",
)
@add_common_options
@click.pass_context
def push(ctx: click.Context, **kwargs) -> None:
    """Push files or git commits from local machine to an agent.

    Syncs files or git state from a local directory to an agent's working directory.
    Default behavior uses rsync for efficient incremental file transfer.
    Use --sync-mode=git to merge git branches instead of syncing files.

    If no target is specified, shows an interactive selector to choose an agent.

    \b
    Examples:
      mngr push my-agent
      mngr push my-agent ./local-copy
      mngr push my-agent:src ./local-src
      mngr push --target-agent my-agent
      mngr push my-agent --sync-mode=git
      mngr push my-agent --sync-mode=git --source-branch=feature
    """
    mngr_ctx, output_opts, opts = setup_command_context(
        ctx=ctx,
        command_name="push",
        command_class=PushCliOptions,
    )
    logger.debug("Running push command")

    # Check for unsupported options
    if opts.sync_mode == "full":
        raise NotImplementedError("--sync-mode=full is not implemented yet")

    if opts.exclude:
        raise NotImplementedError("--exclude is not implemented yet")

    if opts.target_host is not None:
        raise NotImplementedError("--target-host is not implemented yet (only local agents are supported)")

    if opts.mirror:
        raise NotImplementedError("--mirror is not implemented yet")

    # Validate git-specific options
    if opts.source_branch is not None and opts.sync_mode != "git":
        raise UserInputError("--source-branch can only be used with --sync-mode=git")

    # Parse target specification
    agent_identifier: str | None = None
    target_path: str | None = opts.target_path

    if opts.target is not None:
        # Parse target string: AGENT, AGENT:PATH, or PATH
        if ":" in opts.target:
            # AGENT:PATH format
            agent_identifier, target_path = opts.target.split(":", 1)
        elif opts.target.startswith(("/", "./", "~/", "../")):
            # PATH format - not supported without agent
            raise UserInputError("Target must include an agent specification")
        else:
            # AGENT format
            agent_identifier = opts.target

    # Override with explicit options if provided
    if opts.target_agent is not None:
        if agent_identifier is not None and agent_identifier != opts.target_agent:
            raise UserInputError("Cannot specify both --target and --target-agent with different values")
        agent_identifier = opts.target_agent

    # Determine source
    source_path = Path(opts.source) if opts.source else Path.cwd()

    # Find the agent
    agent: AgentInterface
    host: HostInterface

    if agent_identifier is not None:
        agents_by_host = load_all_agents_grouped_by_host(mngr_ctx)
        agent, host = _find_agent_by_name_or_id(agent_identifier, agents_by_host, mngr_ctx)
    elif not sys.stdin.isatty():
        raise UserInputError("No agent specified and not running in interactive mode")
    else:
        # Interactive agent selection
        result = _select_agent_for_push(mngr_ctx)
        if result is None:
            logger.info("No agent selected")
            return
        agent, host = result

    # Only local agents are supported right now
    if not host.is_local:
        raise NotImplementedError("Pushing to remote agents is not implemented yet")

    emit_info(f"Pushing to agent: {agent.name}", output_opts.output_format)

    # Parse uncommitted changes mode
    uncommitted_changes_mode = UncommittedChangesMode(opts.uncommitted_changes.upper())

    if opts.sync_mode == "git":
        # Git mode: merge branches
        git_result = push_git(
            agent=agent,
            host=host,
            source=source_path,
            source_branch=opts.source_branch,
            target_branch=None,
            dry_run=opts.dry_run,
            mirror=opts.mirror,
            uncommitted_changes=uncommitted_changes_mode,
        )

        # Stop agent if requested
        if opts.stop:
            emit_info(f"Stopping agent: {agent.name}", output_opts.output_format)
            host.stop_agents([agent.id])
            emit_info("Agent stopped", output_opts.output_format)

        _output_git_result(git_result, output_opts)
    else:
        # Files mode: rsync
        # Parse target_path if provided
        parsed_target_path: Path | None = None
        if target_path is not None:
            # If target_path is relative, make it relative to agent's work_dir
            parsed_path = Path(target_path)
            if parsed_path.is_absolute():
                parsed_target_path = parsed_path
            else:
                parsed_target_path = agent.work_dir / parsed_path

        files_result = push_files(
            agent=agent,
            host=host,
            source=source_path,
            destination_path=parsed_target_path,
            dry_run=opts.dry_run,
            delete=opts.delete,
            uncommitted_changes=uncommitted_changes_mode,
        )

        # Stop agent if requested
        if opts.stop:
            emit_info(f"Stopping agent: {agent.name}", output_opts.output_format)
            host.stop_agents([agent.id])
            emit_info("Agent stopped", output_opts.output_format)

        _output_files_result(files_result, output_opts)
