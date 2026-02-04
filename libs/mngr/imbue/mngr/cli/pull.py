import sys
from pathlib import Path
from typing import assert_never

import click
from click_option_group import optgroup
from loguru import logger

from imbue.mngr.api.find import load_all_agents_grouped_by_host
from imbue.mngr.api.pull import pull_files
from imbue.mngr.api.pull import pull_git
from imbue.mngr.api.sync import SyncFilesResult
from imbue.mngr.api.sync import SyncGitResult
from imbue.mngr.cli.agent_utils import find_agent_by_name_or_id
from imbue.mngr.cli.agent_utils import select_agent_interactively_with_host
from imbue.mngr.cli.common_opts import CommonCliOptions
from imbue.mngr.cli.common_opts import add_common_options
from imbue.mngr.cli.common_opts import setup_command_context
from imbue.mngr.cli.output_helpers import emit_event
from imbue.mngr.cli.output_helpers import emit_final_json
from imbue.mngr.cli.output_helpers import emit_info
from imbue.mngr.config.data_types import OutputOptions
from imbue.mngr.errors import UserInputError
from imbue.mngr.interfaces.agent import AgentInterface
from imbue.mngr.interfaces.host import HostInterface
from imbue.mngr.primitives import OutputFormat
from imbue.mngr.primitives import UncommittedChangesMode


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
    uncommitted_changes: str
    target_branch: str | None


def _output_files_result(result: SyncFilesResult, output_opts: OutputOptions) -> None:
    """Output the pull files result in the appropriate format."""
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


def _output_git_result(result: SyncGitResult, output_opts: OutputOptions) -> None:
    """Output the pull git result in the appropriate format."""
    result_data = {
        "source_branch": result.source_branch,
        "target_branch": result.target_branch,
        "source_path": str(result.source_path),
        "destination_path": str(result.destination_path),
        "is_dry_run": result.is_dry_run,
        "commits_transferred": result.commits_transferred,
    }
    match output_opts.output_format:
        case OutputFormat.JSON:
            emit_final_json(result_data)
        case OutputFormat.JSONL:
            emit_event("pull_git_complete", result_data, OutputFormat.JSONL)
        case OutputFormat.HUMAN:
            if result.is_dry_run:
                logger.info(
                    "Dry run complete: would merge {} commits from {} into {}",
                    result.commits_transferred,
                    result.source_branch,
                    result.target_branch,
                )
            else:
                logger.info(
                    "Git pull complete: merged {} commits from {} into {}",
                    result.commits_transferred,
                    result.source_branch,
                    result.target_branch,
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
    "--target-branch",
    help="Branch to merge into (git mode only) [default: current branch]",
)
@optgroup.option(
    "--uncommitted-changes",
    type=click.Choice(["stash", "clobber", "merge", "fail"], case_sensitive=False),
    default="fail",
    show_default=True,
    help="How to handle uncommitted changes in the destination: stash (stash and leave stashed), clobber (overwrite), merge (stash, pull, unstash), fail (error if changes exist)",
)
@add_common_options
@click.pass_context
def pull(ctx: click.Context, **kwargs) -> None:
    """Pull files or git commits from an agent to local machine.

    Syncs files or git state from an agent's working directory to a local directory.
    Default behavior uses rsync for efficient incremental file transfer.
    Use --sync-mode=git to merge git branches instead of syncing files.

    If no source is specified, shows an interactive selector to choose an agent.

    \b
    Examples:
      mngr pull my-agent
      mngr pull my-agent ./local-copy
      mngr pull my-agent:src ./local-src
      mngr pull --source-agent my-agent
      mngr pull my-agent --sync-mode=git
      mngr pull my-agent --sync-mode=git --target-branch=main
    """
    mngr_ctx, output_opts, opts = setup_command_context(
        ctx=ctx,
        command_name="pull",
        command_class=PullCliOptions,
    )
    logger.debug("Running pull command")

    # Check for unsupported options
    if opts.sync_mode == "full":
        raise NotImplementedError("--sync-mode=full is not implemented yet")

    if opts.exclude:
        raise NotImplementedError("--exclude is not implemented yet")

    if opts.source_host is not None:
        raise NotImplementedError("--source-host is not implemented yet (only local agents are supported)")

    # Validate git-specific options
    if opts.target_branch is not None and opts.sync_mode != "git":
        raise UserInputError("--target-branch can only be used with --sync-mode=git")

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
        agent, host = find_agent_by_name_or_id(agent_identifier, agents_by_host, mngr_ctx)
    elif not sys.stdin.isatty():
        raise UserInputError("No agent specified and not running in interactive mode")
    else:
        # Interactive agent selection
        result = select_agent_interactively_with_host(mngr_ctx)
        if result is None:
            logger.info("No agent selected")
            return
        agent, host = result

    # Only local agents are supported right now
    if not host.is_local:
        raise NotImplementedError("Pulling from remote agents is not implemented yet")

    emit_info(f"Pulling from agent: {agent.name}", output_opts.output_format)

    # Parse uncommitted changes mode
    uncommitted_changes_mode = UncommittedChangesMode(opts.uncommitted_changes.upper())

    if opts.sync_mode == "git":
        # Git mode: merge branches
        # source_branch=None means use agent's current branch
        git_result = pull_git(
            agent=agent,
            host=host,
            destination=destination_path,
            source_branch=None,
            target_branch=opts.target_branch,
            dry_run=opts.dry_run,
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
        # Parse source_path if provided
        parsed_source_path: Path | None = None
        if source_path is not None:
            # If source_path is relative, make it relative to agent's work_dir
            parsed_path = Path(source_path)
            if parsed_path.is_absolute():
                parsed_source_path = parsed_path
            else:
                parsed_source_path = agent.work_dir / parsed_path

        files_result = pull_files(
            agent=agent,
            host=host,
            destination=destination_path,
            source_path=parsed_source_path,
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
