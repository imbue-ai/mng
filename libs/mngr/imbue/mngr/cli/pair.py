import sys
from pathlib import Path
from typing import assert_never

import click
from click_option_group import optgroup
from loguru import logger

from imbue.mngr.api.find import find_and_maybe_start_agent_by_name_or_id
from imbue.mngr.api.list import load_all_agents_grouped_by_host
from imbue.mngr.api.pair import pair_files
from imbue.mngr.cli.agent_utils import filter_agents_by_host
from imbue.mngr.cli.agent_utils import select_agent_interactively_with_host
from imbue.mngr.cli.common_opts import CommonCliOptions
from imbue.mngr.cli.common_opts import add_common_options
from imbue.mngr.cli.common_opts import setup_command_context
from imbue.mngr.cli.output_helpers import emit_event
from imbue.mngr.cli.output_helpers import emit_info
from imbue.mngr.config.data_types import OutputOptions
from imbue.mngr.errors import MngrError
from imbue.mngr.errors import UserInputError
from imbue.mngr.interfaces.agent import AgentInterface
from imbue.mngr.interfaces.host import OnlineHostInterface
from imbue.mngr.primitives import ConflictMode
from imbue.mngr.primitives import OutputFormat
from imbue.mngr.primitives import SyncDirection
from imbue.mngr.primitives import UncommittedChangesMode
from imbue.mngr.utils.git_utils import find_git_worktree_root


class PairCliOptions(CommonCliOptions):
    """Options passed from the CLI to the pair command."""

    source: str | None
    source_agent: str | None
    source_host: str | None
    source_path: str | None
    target: str | None
    target_path: str | None
    require_git: bool
    sync_direction: str
    conflict: str
    uncommitted_changes: str
    include: tuple[str, ...]
    exclude: tuple[str, ...]


def _emit_pair_started(
    source_path: Path,
    target_path: Path,
    output_opts: OutputOptions,
) -> None:
    """Emit a message when pairing starts."""
    data = {
        "source_path": str(source_path),
        "target_path": str(target_path),
        "event": "pair_started",
    }
    match output_opts.output_format:
        case OutputFormat.JSON:
            emit_event("pair_started", data, OutputFormat.JSON)
        case OutputFormat.JSONL:
            emit_event("pair_started", data, OutputFormat.JSONL)
        case OutputFormat.HUMAN:
            logger.info("Pairing {} <-> {}", source_path, target_path)
        case _ as unreachable:
            assert_never(unreachable)


def _emit_pair_stopped(output_opts: OutputOptions) -> None:
    """Emit a message when pairing stops."""
    data = {"event": "pair_stopped"}
    match output_opts.output_format:
        case OutputFormat.JSON:
            emit_event("pair_stopped", data, OutputFormat.JSON)
        case OutputFormat.JSONL:
            emit_event("pair_stopped", data, OutputFormat.JSONL)
        case OutputFormat.HUMAN:
            logger.info("Pairing stopped")
        case _ as unreachable:
            assert_never(unreachable)


@click.command()
@click.argument("source", default=None, required=False)
@optgroup.group("Source Selection")
@optgroup.option("--source", "source", help="Source specification: AGENT, AGENT:PATH, or PATH")
@optgroup.option("--source-agent", help="Source agent name or ID")
@optgroup.option("--source-host", help="Source host name or ID")
@optgroup.option("--source-path", help="Path within the agent's work directory")
@optgroup.group("Target")
@optgroup.option(
    "--target",
    "target",
    type=click.Path(),
    help="Local target directory [default: nearest git root or current directory]",
)
@optgroup.option("--target-path", help="Target path (if different from --target)")
@optgroup.group("Git Handling")
@optgroup.option(
    "--require-git/--no-require-git",
    default=True,
    help="Require that both source and target are git repositories [default: require git]",
)
@optgroup.option(
    "--uncommitted-changes",
    type=click.Choice(["stash", "clobber", "merge", "fail"], case_sensitive=False),
    default="fail",
    show_default=True,
    help="How to handle uncommitted changes during initial git sync. The initial sync aborts immediately if unresolved conflicts exist, regardless of this setting.",
)
@optgroup.group("Sync Behavior")
@optgroup.option(
    "--sync-direction",
    type=click.Choice(["both", "forward", "reverse"], case_sensitive=False),
    default="both",
    show_default=True,
    help="Sync direction: both (bidirectional), forward (source->target), reverse (target->source)",
)
@optgroup.option(
    "--conflict",
    type=click.Choice(["newer", "source", "target", "ask"], case_sensitive=False),
    default="newer",
    show_default=True,
    help="Conflict resolution mode (only matters for bidirectional sync). 'newer' prefers the file with the more recent modification time (uses unison's -prefer newer; note that clock skew between machines can cause incorrect results). 'source' and 'target' always prefer that side. 'ask' prompts interactively [future].",
)
@optgroup.group("File Filtering")
@optgroup.option(
    "--include",
    multiple=True,
    help="Include files matching glob pattern [repeatable]",
)
@optgroup.option(
    "--exclude",
    multiple=True,
    help="Exclude files matching glob pattern [repeatable]",
)
@add_common_options
@click.pass_context
def pair(ctx: click.Context, **kwargs) -> None:
    """Continuously sync files between an agent and local directory.

    This command establishes a bidirectional file sync between an agent's working
    directory and a local directory. Changes are watched and synced in real-time.

    If git repositories exist on both sides, the command first synchronizes git
    state (branches and commits) before starting the continuous file sync.

    Press Ctrl+C to stop the sync.

    During rapid concurrent edits, changes will be debounced to avoid partial
    writes [future].

    \b
    Examples:
      mngr pair my-agent
      mngr pair my-agent ./local-dir
      mngr pair --source-agent my-agent --target ./local-copy
      mngr pair my-agent --sync-direction=forward
      mngr pair my-agent --conflict=source
      mngr pair my-agent --source-host @local
    """
    mngr_ctx, output_opts, opts = setup_command_context(
        ctx=ctx,
        command_name="pair",
        command_class=PairCliOptions,
    )
    logger.debug("Running pair command")

    # Check for unsupported options
    if opts.conflict == "ask":
        raise NotImplementedError("--conflict=ask is not implemented yet")

    # Parse source specification
    agent_identifier: str | None = None
    source_subpath: str | None = opts.source_path

    if opts.source is not None:
        # Parse source string: AGENT, AGENT:PATH, or PATH
        if ":" in opts.source:
            # AGENT:PATH format
            agent_identifier, source_subpath = opts.source.split(":", 1)
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

    # Determine target path
    if opts.target is not None:
        target_path = Path(opts.target)
    elif opts.target_path is not None:
        target_path = Path(opts.target_path)
    else:
        # Default to nearest git root, or current directory
        git_root = find_git_worktree_root()
        target_path = git_root if git_root is not None else Path.cwd()

    # Find the agent
    agent: AgentInterface
    host: OnlineHostInterface

    if agent_identifier is not None:
        agents_by_host, _ = load_all_agents_grouped_by_host(mngr_ctx)
        if opts.source_host is not None:
            agents_by_host = filter_agents_by_host(agents_by_host, opts.source_host)
        agent, host = find_and_maybe_start_agent_by_name_or_id(
            agent_identifier, agents_by_host, mngr_ctx, "pair <agent-id>"
        )
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
        raise NotImplementedError("Pairing with remote agents is not implemented yet")

    # Determine source path (agent's work_dir, potentially with subpath)
    source_path = agent.work_dir
    if source_subpath is not None:
        parsed_subpath = Path(source_subpath)
        if parsed_subpath.is_absolute():
            source_path = parsed_subpath
        else:
            source_path = agent.work_dir / parsed_subpath

    emit_info(f"Pairing with agent: {agent.name}", output_opts.output_format)

    # Parse enum options
    sync_direction = SyncDirection(opts.sync_direction.upper())
    conflict_mode = ConflictMode(opts.conflict.upper())
    uncommitted_changes_mode = UncommittedChangesMode(opts.uncommitted_changes.upper())

    _emit_pair_started(source_path, target_path, output_opts)

    # Start the pair sync
    try:
        with pair_files(
            agent=agent,
            host=host,
            source_path=source_path,
            target_path=target_path,
            sync_direction=sync_direction,
            conflict_mode=conflict_mode,
            is_require_git=opts.require_git,
            uncommitted_changes=uncommitted_changes_mode,
            exclude_patterns=opts.exclude,
            include_patterns=opts.include,
        ) as syncer:
            emit_info("Sync started. Press Ctrl+C to stop.", output_opts.output_format)

            # Wait for the syncer to complete (usually via Ctrl+C)
            exit_code = syncer.wait()
            if exit_code != 0:
                raise MngrError(f"Unison exited with code {exit_code}")
    except KeyboardInterrupt:
        logger.debug("Received keyboard interrupt")
    finally:
        _emit_pair_stopped(output_opts)
