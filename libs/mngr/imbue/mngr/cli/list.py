import re
import shutil
import sys
from collections.abc import Sequence
from enum import Enum
from threading import Lock
from typing import Any
from typing import Final

import click
from click_option_group import optgroup
from loguru import logger
from pydantic import BaseModel
from pydantic import PrivateAttr
from tabulate import tabulate

from imbue.imbue_common.mutable_model import MutableModel
from imbue.imbue_common.pure import pure
from imbue.mngr.api.list import AgentInfo
from imbue.mngr.api.list import ErrorInfo
from imbue.mngr.api.list import list_agents as api_list_agents
from imbue.mngr.cli.common_opts import CommonCliOptions
from imbue.mngr.cli.common_opts import add_common_options
from imbue.mngr.cli.common_opts import setup_command_context
from imbue.mngr.cli.help_formatter import CommandHelpMetadata
from imbue.mngr.cli.help_formatter import add_pager_help_option
from imbue.mngr.cli.help_formatter import register_help_metadata
from imbue.mngr.cli.output_helpers import AbortError
from imbue.mngr.cli.output_helpers import emit_final_json
from imbue.mngr.cli.watch_mode import run_watch_loop
from imbue.mngr.config.data_types import MngrContext
from imbue.mngr.config.data_types import OutputOptions
from imbue.mngr.primitives import AgentLifecycleState
from imbue.mngr.primitives import ErrorBehavior
from imbue.mngr.primitives import OutputFormat

_DEFAULT_HUMAN_DISPLAY_FIELDS: Final[tuple[str, ...]] = ("name", "host", "provider", "host.state", "state", "status")


@pure
def _should_use_streaming_mode(
    output_format: OutputFormat,
    is_watch: bool,
    is_sort_explicit: bool,
    limit: int | None,
) -> bool:
    """Determine whether to use streaming mode for list output."""
    return output_format == OutputFormat.HUMAN and not is_watch and not is_sort_explicit and limit is None


class ListCliOptions(CommonCliOptions):
    """Options passed from the CLI to the list command.

    This captures all the click parameters so we can pass them as a single object
    to helper functions instead of passing dozens of individual parameters.

    Inherits common options (output_format, quiet, verbose, etc.) from CommonCliOptions.

    Note that this class VERY INTENTIONALLY DOES NOT use Field() decorators with descriptions, defaults, etc.
    For that information, see the click.option() and click.argument() decorators on the list() function itself.
    """

    include: tuple[str, ...]
    exclude: tuple[str, ...]
    running: bool
    stopped: bool
    local: bool
    remote: bool
    provider: tuple[str, ...]
    stdin: bool
    format_template: str | None
    fields: str | None
    sort: str
    sort_order: str
    limit: int | None
    watch: int | None
    on_error: str


@click.command(name="list")
@optgroup.group("Filtering")
@optgroup.option(
    "--include",
    multiple=True,
    help="Include agents matching CEL expression (repeatable)",
)
@optgroup.option(
    "--exclude",
    multiple=True,
    help="Exclude agents matching CEL expression (repeatable)",
)
@optgroup.option(
    "--running",
    is_flag=True,
    help="Show only running agents (alias for --include 'state == \"RUNNING\"')",
)
@optgroup.option(
    "--stopped",
    is_flag=True,
    help="Show only stopped agents (alias for --include 'state == \"STOPPED\"')",
)
@optgroup.option(
    "--local",
    is_flag=True,
    help="Show only local agents (alias for --include 'host.provider == \"local\"')",
)
@optgroup.option(
    "--remote",
    is_flag=True,
    help="Show only remote agents (alias for --exclude 'host.provider == \"local\"')",
)
@optgroup.option(
    "--provider",
    multiple=True,
    help="Show only agents using specified provider (repeatable)",
)
@optgroup.option(
    "--stdin",
    is_flag=True,
    help="Read agent and host IDs or names from stdin (one per line)",
)
@optgroup.group("Output Format")
@optgroup.option(
    "--format-template",
    "format_template",
    help="Output format as a string template (mutually exclusive with --format) [future]",
)
@optgroup.option(
    "--fields",
    help="Which fields to include (comma-separated)",
)
@optgroup.option(
    "--sort",
    default="create_time",
    help="Sort by field (supports nested fields like host.name); enables sorted (non-streaming) output [default: create_time]",
)
@optgroup.option(
    "--sort-order",
    type=click.Choice(["asc", "desc"], case_sensitive=False),
    default="asc",
    help="Sort order [default: asc]",
)
@optgroup.option(
    "--limit",
    type=int,
    help="Limit number of results (applied after fetching from all providers)",
)
@optgroup.group("Watch Mode")
@optgroup.option(
    "-w",
    "--watch",
    type=int,
    help="Continuously watch and update status at specified interval (seconds)",
)
@optgroup.group("Error Handling")
@optgroup.option(
    "--on-error",
    type=click.Choice(["abort", "continue"], case_sensitive=False),
    default="abort",
    help="What to do when errors occur: abort (stop immediately) or continue (keep going)",
)
@add_common_options
@click.pass_context
def list_command(ctx: click.Context, **kwargs) -> None:
    """List all agents managed by mngr.

    Displays agents with their status, host information, and other metadata.
    Supports filtering, sorting, and multiple output formats.

    Examples:

      mngr list

      mngr list --running

      mngr list --provider docker

      mngr list --format json
    """
    try:
        _list_impl(ctx, **kwargs)
    except AbortError as e:
        logger.error("Aborted: {}", e.message)
        ctx.exit(1)


def _list_impl(ctx: click.Context, **kwargs) -> None:
    """Implementation of list command (extracted for exception handling)."""
    mngr_ctx, output_opts, opts = setup_command_context(
        ctx=ctx,
        command_name="list",
        command_class=ListCliOptions,
    )
    logger.debug("Started list command")

    # --format-template FORMAT: Output format as a string template, mutually exclusive with --format
    # Template can reference any field from the Available Fields list (see CommandHelpMetadata)
    if opts.format_template:
        raise NotImplementedError("Custom format templates not implemented yet")

    # Parse fields if provided
    fields = None
    if opts.fields:
        fields = [f.strip() for f in opts.fields.split(",") if f.strip()]

    # Build list of include filters
    include_filters = list(opts.include)

    # Handle stdin input by converting to CEL filters
    if opts.stdin:
        stdin_refs = [line.strip() for line in sys.stdin if line.strip()]
        if stdin_refs:
            # Create a CEL filter that matches any of the provided refs against
            # host.name, host.id, name, or id (using dot notation for nested fields)
            ref_filters = []
            for ref in stdin_refs:
                ref_filter = f'(name == "{ref}" || id == "{ref}" || host.name == "{ref}" || host.id == "{ref}")'
                ref_filters.append(ref_filter)
            # Combine all ref filters with OR
            combined_filter = " || ".join(ref_filters)
            include_filters.append(combined_filter)

    # --running: alias for --include 'state == "RUNNING"'
    # --stopped: alias for --include 'state == "STOPPED"'
    # --local: alias for --include 'host.provider == "local"'
    # --remote: alias for --exclude 'host.provider == "local"'
    if opts.running:
        include_filters.append(f'state == "{AgentLifecycleState.RUNNING.value}"')
    if opts.stopped:
        include_filters.append(f'state == "{AgentLifecycleState.STOPPED.value}"')
    if opts.local:
        include_filters.append('host.provider == "local"')

    # Build list of exclude filters
    exclude_filters = list(opts.exclude)
    if opts.remote:
        exclude_filters.append('host.provider == "local"')

    # --sort FIELD: Sort by any available field [default: create_time]
    # --sort-order ORDER: Sort order (asc, desc) [default: asc]
    sort_field = opts.sort
    sort_reverse = opts.sort_order.lower() == "desc"

    # --limit N: Limit number of results returned
    # NOTE: The limit is applied after fetching results. The full list is still retrieved
    # from providers and then sliced client-side. For large deployments, this means the
    # command may still take time proportional to the total number of agents.
    limit = opts.limit

    error_behavior = ErrorBehavior(opts.on_error.upper())

    include_filters_tuple = tuple(include_filters)
    exclude_filters_tuple = tuple(exclude_filters)
    provider_names = opts.provider if opts.provider else None

    # Dispatch to the appropriate output path
    if output_opts.output_format == OutputFormat.JSONL:
        _list_jsonl(
            ctx,
            mngr_ctx,
            include_filters_tuple,
            exclude_filters_tuple,
            provider_names,
            error_behavior,
            limit,
            is_watch=bool(opts.watch),
        )
        return

    # Determine if --sort was explicitly set by the user (vs using the default)
    sort_source = ctx.get_parameter_source("sort")
    is_sort_explicit = sort_source is not None and sort_source != click.core.ParameterSource.DEFAULT

    # Streaming mode trades sorted output for faster time-to-first-result: agents display
    # as each provider completes rather than waiting for all providers. Users who need sorted
    # output can pass --sort explicitly, which falls back to batch mode. When --limit is set,
    # batch mode is required to get deterministic results (streaming would show whichever
    # agents load first, since sorting is skipped).
    if _should_use_streaming_mode(
        output_opts.output_format, is_watch=bool(opts.watch), is_sort_explicit=is_sort_explicit, limit=limit
    ):
        display_fields = fields if fields is not None else list(_DEFAULT_HUMAN_DISPLAY_FIELDS)
        _list_streaming_human(
            ctx,
            mngr_ctx,
            include_filters_tuple,
            exclude_filters_tuple,
            provider_names,
            error_behavior,
            display_fields,
        )
        return

    # Batch/watch path
    iteration_params = _ListIterationParams(
        mngr_ctx=mngr_ctx,
        output_opts=output_opts,
        include_filters=include_filters_tuple,
        exclude_filters=exclude_filters_tuple,
        provider_names=provider_names,
        error_behavior=error_behavior,
        sort_field=sort_field,
        sort_reverse=sort_reverse,
        limit=limit,
        fields=fields,
    )

    if opts.watch:
        try:
            run_watch_loop(
                iteration_fn=lambda: _run_list_iteration(iteration_params, ctx),
                interval_seconds=opts.watch,
                on_error_continue=True,
            )
        except KeyboardInterrupt:
            logger.info("\nWatch mode stopped")
            return
    else:
        _run_list_iteration(iteration_params, ctx)


def _list_jsonl(
    ctx: click.Context,
    mngr_ctx: MngrContext,
    include_filters: tuple[str, ...],
    exclude_filters: tuple[str, ...],
    provider_names: tuple[str, ...] | None,
    error_behavior: ErrorBehavior,
    limit: int | None,
    is_watch: bool,
) -> None:
    """JSONL output path: stream agents as JSONL lines with optional limit."""
    if is_watch:
        logger.warning("Watch mode is not supported with JSONL format, running once")

    limited_callback = _LimitedJsonlEmitter(limit=limit)

    result = api_list_agents(
        mngr_ctx=mngr_ctx,
        include_filters=include_filters,
        exclude_filters=exclude_filters,
        provider_names=provider_names,
        error_behavior=error_behavior,
        on_agent=limited_callback,
        on_error=_emit_jsonl_error,
        is_streaming=False,
    )
    # Exit with non-zero code if there were errors (per error_handling.md spec)
    if result.errors:
        ctx.exit(1)


def _list_streaming_human(
    ctx: click.Context,
    mngr_ctx: MngrContext,
    include_filters: tuple[str, ...],
    exclude_filters: tuple[str, ...],
    provider_names: tuple[str, ...] | None,
    error_behavior: ErrorBehavior,
    fields: list[str],
) -> None:
    """Streaming human output path: display agents as each provider completes."""
    renderer = _StreamingHumanRenderer(fields=fields, is_tty=sys.stdout.isatty())
    renderer.start()
    try:
        result = api_list_agents(
            mngr_ctx=mngr_ctx,
            include_filters=include_filters,
            exclude_filters=exclude_filters,
            provider_names=provider_names,
            error_behavior=error_behavior,
            on_agent=renderer,
            is_streaming=True,
        )
    finally:
        renderer.finish()

    if result.errors:
        for error in result.errors:
            logger.warning("{}: {}", error.exception_type, error.message)
        ctx.exit(1)


class _LimitedJsonlEmitter(MutableModel):
    """Callable that emits JSONL output with an optional limit."""

    model_config = {"arbitrary_types_allowed": True}
    limit: int | None
    count: int = 0
    _lock: Lock = PrivateAttr(default_factory=Lock)

    def __call__(self, agent: AgentInfo) -> None:
        with self._lock:
            if self.limit is not None and self.count >= self.limit:
                return
            _emit_jsonl_agent(agent)
            self.count += 1


# Minimum column widths for streaming output (left-justified, not truncated)
_MIN_COLUMN_WIDTHS: Final[dict[str, int]] = {
    "name": 20,
    "host": 15,
    "provider": 10,
    "host.state": 10,
    "state": 10,
    "status": 30,
}
_DEFAULT_MIN_COLUMN_WIDTH: Final[int] = 15
# Columns that get extra space when the terminal is wider than the minimum
_EXPANDABLE_COLUMNS: Final[set[str]] = {"name", "status", "host"}
_MAX_COLUMN_WIDTHS: Final[dict[str, int]] = {
    "host": 20,
}
_COLUMN_SEPARATOR: Final[str] = "  "

# ANSI escape sequences for terminal control
_ANSI_ERASE_LINE: Final[str] = "\r\x1b[K"
_ANSI_DIM_GRAY: Final[str] = "\x1b[38;5;245m"
_ANSI_RESET: Final[str] = "\x1b[0m"


class _StreamingHumanRenderer(MutableModel):
    """Thread-safe streaming renderer for human-readable list output.

    Writes table rows to stdout as agents arrive from the API. Uses an ANSI status
    line ("Searching...") that gets replaced by data rows on TTY outputs. On non-TTY
    outputs (piped), skips status lines and ANSI codes entirely.
    """

    model_config = {"arbitrary_types_allowed": True}
    fields: list[str]
    is_tty: bool
    _lock: Lock = PrivateAttr(default_factory=Lock)
    _count: int = PrivateAttr(default=0)
    _is_header_written: bool = PrivateAttr(default=False)
    _column_widths: dict[str, int] = PrivateAttr(default_factory=dict)

    def start(self) -> None:
        """Compute column widths and write the initial status line (TTY only)."""
        self._column_widths = _compute_column_widths(self.fields)

        if self.is_tty:
            status = f"{_ANSI_DIM_GRAY}Searching...{_ANSI_RESET}"
            sys.stdout.write(status)
            sys.stdout.flush()

    def __call__(self, agent: AgentInfo) -> None:
        """Handle a single agent result (on_agent callback)."""
        with self._lock:
            if self.is_tty:
                # Erase the current status line
                sys.stdout.write(_ANSI_ERASE_LINE)

            # Write header on first agent
            if not self._is_header_written:
                header_line = _format_streaming_header_row(self.fields, self._column_widths)
                sys.stdout.write(header_line + "\n")
                self._is_header_written = True

            # Write the agent row
            row_line = _format_streaming_agent_row(agent, self.fields, self._column_widths)
            sys.stdout.write(row_line + "\n")
            self._count += 1

            if self.is_tty:
                # Write updated status line
                status = f"{_ANSI_DIM_GRAY}Searching... ({self._count} found){_ANSI_RESET}"
                sys.stdout.write(status)

            sys.stdout.flush()

    def finish(self) -> None:
        """Clean up the status line after all providers have completed."""
        with self._lock:
            if self.is_tty:
                # Erase the final status line
                sys.stdout.write(_ANSI_ERASE_LINE)
                sys.stdout.flush()

            if self._count == 0:
                logger.info("No agents found")


@pure
def _compute_column_widths(fields: Sequence[str]) -> dict[str, int]:
    """Compute column widths sized to the terminal, distributing extra space to expandable columns."""
    terminal_width = shutil.get_terminal_size((120, 24)).columns
    separator_total = len(_COLUMN_SEPARATOR) * max(len(fields) - 1, 0)

    # Start with minimum widths
    width_by_field: dict[str, int] = {}
    for field in fields:
        width_by_field[field] = _MIN_COLUMN_WIDTHS.get(field, _DEFAULT_MIN_COLUMN_WIDTH)

    min_total = sum(width_by_field.values()) + separator_total
    extra_space = max(terminal_width - min_total, 0)

    # Distribute extra space to expandable columns, respecting max widths.
    # Two passes: first distribute evenly, then redistribute any space reclaimed by max caps.
    expandable_in_fields = [f for f in fields if f in _EXPANDABLE_COLUMNS]
    if expandable_in_fields and extra_space > 0:
        remaining_space = extra_space
        uncapped_fields = list(expandable_in_fields)

        while remaining_space > 0 and uncapped_fields:
            per_column = remaining_space // len(uncapped_fields)
            remainder = remaining_space % len(uncapped_fields)
            if per_column == 0 and remainder == 0:
                break

            still_uncapped: list[str] = []
            space_used = 0
            for idx, field in enumerate(uncapped_fields):
                bonus = per_column + (1 if idx < remainder else 0)
                max_width = _MAX_COLUMN_WIDTHS.get(field)
                proposed = width_by_field[field] + bonus
                if max_width is not None and proposed > max_width:
                    actual_bonus = max(max_width - width_by_field[field], 0)
                    width_by_field[field] = max_width
                    space_used += actual_bonus
                else:
                    width_by_field[field] = proposed
                    space_used += bonus
                    still_uncapped.append(field)

            remaining_space = remaining_space - space_used
            uncapped_fields = still_uncapped

    return width_by_field


@pure
def _format_streaming_header_row(fields: Sequence[str], column_widths: dict[str, int]) -> str:
    """Format the header row of streaming output with computed column widths."""
    parts: list[str] = []
    for field in fields:
        width = column_widths.get(field, _DEFAULT_MIN_COLUMN_WIDTH)
        value = field.upper().replace(".", "_")
        parts.append(value.ljust(width))
    return _COLUMN_SEPARATOR.join(parts)


@pure
def _format_streaming_agent_row(agent: AgentInfo, fields: Sequence[str], column_widths: dict[str, int]) -> str:
    """Format a single agent as a streaming output row."""
    parts: list[str] = []
    for field in fields:
        width = column_widths.get(field, _DEFAULT_MIN_COLUMN_WIDTH)
        value = _get_field_value(agent, field)
        # Values are padded but intentionally not truncated: full values are preferred
        # over truncated ones, so columns may appear ragged when values exceed the width.
        parts.append(value.ljust(width))
    return _COLUMN_SEPARATOR.join(parts)


class _ListIterationParams(BaseModel):
    """Parameters for a single list iteration, used for watch mode."""

    model_config = {"arbitrary_types_allowed": True}

    mngr_ctx: MngrContext
    output_opts: OutputOptions
    include_filters: tuple[str, ...]
    exclude_filters: tuple[str, ...]
    provider_names: tuple[str, ...] | None
    error_behavior: ErrorBehavior
    sort_field: str
    sort_reverse: bool
    limit: int | None
    fields: list[str] | None


def _run_list_iteration(params: _ListIterationParams, ctx: click.Context) -> None:
    """Run a single list iteration."""
    result = api_list_agents(
        mngr_ctx=params.mngr_ctx,
        include_filters=params.include_filters,
        exclude_filters=params.exclude_filters,
        provider_names=params.provider_names,
        error_behavior=params.error_behavior,
        is_streaming=False,
    )

    if result.errors:
        for error in result.errors:
            logger.warning("{}: {}", error.exception_type, error.message)

    # Apply sorting to results
    agents_to_display = _sort_agents(result.agents, params.sort_field, params.sort_reverse)

    # Apply limit to results (after sorting)
    if params.limit is not None:
        agents_to_display = agents_to_display[: params.limit]

    if not agents_to_display:
        if params.output_opts.output_format == OutputFormat.HUMAN:
            logger.info("No agents found")
        elif params.output_opts.output_format == OutputFormat.JSON:
            emit_final_json({"agents": [], "errors": result.errors})
        else:
            # JSONL is handled above with streaming, so this should be unreachable
            raise AssertionError(f"Unexpected output format: {params.output_opts.output_format}")
        # Exit with non-zero code if there were errors (per error_handling.md spec)
        if result.errors:
            ctx.exit(1)
        return

    if params.output_opts.output_format == OutputFormat.HUMAN:
        _emit_human_output(agents_to_display, params.fields)
    elif params.output_opts.output_format == OutputFormat.JSON:
        _emit_json_output(agents_to_display, result.errors)
    else:
        # JSONL is handled above with streaming, so this should be unreachable
        raise AssertionError(f"Unexpected output format: {params.output_opts.output_format}")

    # Exit with non-zero code if there were errors (per error_handling.md spec)
    if result.errors:
        ctx.exit(1)


def _emit_json_output(agents: list[AgentInfo], errors: list[ErrorInfo]) -> None:
    """Emit JSON output with all agents."""
    agents_data = [agent.model_dump(mode="json") for agent in agents]
    errors_data = [error.model_dump(mode="json") for error in errors]
    output_data = {
        "agents": agents_data,
        "errors": errors_data,
    }
    emit_final_json(output_data)


def _emit_jsonl_agent(agent: AgentInfo) -> None:
    """Emit a single agent as a JSONL line (streaming callback)."""
    agent_data = agent.model_dump(mode="json")
    emit_final_json(agent_data)


def _emit_jsonl_error(error: ErrorInfo) -> None:
    """Emit a single error as a JSONL line (streaming callback)."""
    error_data = {"event": "error", **error.model_dump(mode="json")}
    emit_final_json(error_data)


def _emit_human_output(agents: list[AgentInfo], fields: list[str] | None = None) -> None:
    """Emit human-readable table output with optional field selection.

    If fields is None, uses default fields (name, host, provider, host.state, state, status).
    """
    if not agents:
        return

    # Default fields if none specified
    if fields is None:
        fields = list(_DEFAULT_HUMAN_DISPLAY_FIELDS)

    # Build table data dynamically based on requested fields
    headers = []
    rows = []

    # Generate headers
    for field in fields:
        headers.append(field.upper().replace(".", "_"))

    # Generate rows
    for agent in agents:
        row = []
        for field in fields:
            value = _get_field_value(agent, field)
            row.append(value)
        rows.append(row)

    # Generate table
    table = tabulate(rows, headers=headers, tablefmt="plain")
    logger.info("\n" + table)


def _parse_slice_spec(spec: str) -> int | slice | None:
    """Parse a bracket slice specification like '0', '-1', ':3', '1:3', or '1:'.

    Returns an int for single index, slice object for ranges, or None if invalid.
    """
    spec = spec.strip()

    try:
        # Check if it's a slice (contains ':')
        if ":" in spec:
            parts = spec.split(":")
            if len(parts) == 2:
                start_str, stop_str = parts
                start = int(start_str) if start_str else None
                stop = int(stop_str) if stop_str else None
                return slice(start, stop)
            elif len(parts) == 3:
                start_str, stop_str, step_str = parts
                start = int(start_str) if start_str else None
                stop = int(stop_str) if stop_str else None
                step = int(step_str) if step_str else None
                return slice(start, stop, step)
            else:
                # Invalid slice format (too many colons)
                return None
        else:
            # Simple index
            return int(spec)
    except ValueError:
        # Could not parse integers in the spec
        return None


def _format_value_as_string(value: Any) -> str:
    """Convert a value to string representation for display."""
    if value is None:
        return ""
    elif isinstance(value, Enum):
        return str(value.value)
    elif hasattr(value, "line"):
        # For AgentStatus objects which have a 'line' attribute
        return str(value.line)
    elif hasattr(value, "name") and hasattr(value, "id"):
        # For objects like SnapshotInfo that have both name and id, prefer name
        return str(value.name)
    elif isinstance(value, str):
        return value
    else:
        return str(value)


# Pattern to match a field part with optional bracket notation
# Matches: "fieldname", "fieldname[0]", "fieldname[-1]", "fieldname[:3]", "fieldname[1:3]", etc.
_BRACKET_PATTERN = re.compile(r"^([^\[]+)(?:\[([^\]]+)\])?$")


def _get_sortable_value(agent: AgentInfo, field: str) -> Any:
    """Extract a field value from an AgentInfo object for sorting.

    Returns the raw value (not string-formatted) for proper sorting behavior.
    Supports nested fields like "host.name" and field aliases.
    """
    # FIXME: remove these aliases here and below. If anything must remain, make it a proper on AgentInfo
    # Handle special field aliases for backward compatibility and convenience
    field_aliases = {
        "host": "host.name",
        "provider": "host.provider_name",
        "host.provider": "host.provider_name",
    }

    # Apply alias if it exists
    if field in field_aliases:
        field = field_aliases[field]

    # Handle nested fields (e.g., "host.name")
    parts = field.split(".")
    value: Any = agent

    try:
        for part in parts:
            # Strip any bracket notation for sorting (use base field only)
            base_part = part.split("[")[0]
            if hasattr(value, base_part):
                value = getattr(value, base_part)
            else:
                return None
        return value
    except (AttributeError, KeyError):
        return None


class _AgentSortKey:
    """Callable class for sorting agents by a field (avoids inline function definitions)."""

    sort_field: str

    def __call__(self, agent: AgentInfo) -> tuple[int, Any]:
        value = _get_sortable_value(agent, self.sort_field)
        if value is None:
            return (1, "")
        if hasattr(value, "value"):
            value = value.value
        return (0, str(value))


def _sort_agents(agents: list[AgentInfo], sort_field: str, reverse: bool) -> list[AgentInfo]:
    """Sort a list of agents by the specified field."""
    key = _AgentSortKey()
    key.sort_field = sort_field
    return sorted(agents, key=key, reverse=reverse)


def _get_field_value(agent: AgentInfo, field: str) -> str:
    """Extract a field value from an AgentInfo object and return as string.

    Supports nested fields like "host.name", handles field aliases, and supports
    list slicing syntax like "host.snapshots[0]" or "host.snapshots[:3]".
    """
    # Handle special field aliases for backward compatibility and convenience
    # Note: host.provider maps to host.provider_name for consistency with CEL filters
    field_aliases = {
        "host": "host.name",
        "provider": "host.provider_name",
        "host.provider": "host.provider_name",
    }

    # Apply alias if it exists
    if field in field_aliases:
        field = field_aliases[field]

    # Handle nested fields (e.g., "host.name") with optional bracket notation
    parts = field.split(".")
    value: Any = agent

    try:
        for part in parts:
            # Parse the part for bracket notation
            match = _BRACKET_PATTERN.match(part)
            if not match:
                return ""

            field_name = match.group(1)
            # bracket_spec may be None if no brackets present in the part
            bracket_spec = match.group(2)

            # Get the field value
            if hasattr(value, field_name):
                value = getattr(value, field_name)
            else:
                return ""

            # Apply bracket indexing/slicing if present
            if bracket_spec is not None:
                if not isinstance(value, (list, tuple, Sequence)) or isinstance(value, str):
                    return ""

                index_or_slice = _parse_slice_spec(bracket_spec)
                if index_or_slice is None:
                    return ""

                try:
                    value = value[index_or_slice]
                except (IndexError, ValueError):
                    # IndexError: out of bounds index
                    # ValueError: slice step cannot be zero
                    return ""

                # If the result is a list (from slicing), format each element
                if isinstance(value, (list, tuple)) and not isinstance(value, str):
                    return ", ".join(_format_value_as_string(item) for item in value)

        return _format_value_as_string(value)
    except (AttributeError, KeyError):
        return ""


# Register help metadata for git-style help formatting
_LIST_HELP_METADATA = CommandHelpMetadata(
    name="mngr-list",
    one_line_description="List all agents managed by mngr",
    synopsis="mngr [list|ls] [OPTIONS]",
    description="""List all agents managed by mngr.

Displays agents with their status, host information, and other metadata.
Supports filtering, sorting, and multiple output formats.""",
    aliases=("ls",),
    examples=(
        ("List all agents", "mngr list"),
        ("List only running agents", "mngr list --running"),
        ("List agents on Docker hosts", "mngr list --provider docker"),
        ("List agents as JSON", "mngr list --format json"),
        ("Filter with CEL expression", "mngr list --include 'name.contains(\"prod\")'"),
    ),
    additional_sections=(
        (
            "CEL Filter Examples",
            """CEL (Common Expression Language) filters allow powerful, expressive filtering of agents.
All agent fields from the "Available Fields" section can be used in filter expressions.

**Simple equality filters:**
- `name == "my-agent"` - Match agent by exact name
- `state == "RUNNING"` - Match running agents
- `host.provider == "docker"` - Match agents on Docker hosts
- `type == "claude"` - Match agents of type "claude"

**Compound expressions:**
- `state == "RUNNING" && host.provider == "modal"` - Running agents on Modal
- `state == "STOPPED" || state == "FAILED"` - Stopped or failed agents
- `host.provider == "docker" && name.startsWith("test-")` - Docker agents with names starting with "test-"

**String operations:**
- `name.contains("prod")` - Agent names containing "prod"
- `name.startsWith("staging-")` - Agent names starting with "staging-"
- `name.endsWith("-dev")` - Agent names ending with "-dev"

**Numeric comparisons:**
- `runtime_seconds > 3600` - Agents running for more than an hour
- `idle_seconds < 300` - Agents active in the last 5 minutes
- `host.resource.memory_gb >= 8` - Agents on hosts with 8GB+ memory
- `host.uptime_seconds > 86400` - Agents on hosts running for more than a day

**Existence checks:**
- `has(url)` - Agents that have a URL set
- `has(host.ssh)` - Agents on remote hosts with SSH access
""",
        ),
        (
            "Available Fields",
            """**Agent fields** (same syntax for `--fields` and CEL filters):
- `name` - Agent name
- `id` - Agent ID
- `type` - Agent type (claude, codex, etc.)
- `command` - The command used to start the agent
- `url` - URL where the agent can be accessed (if reported)
- `status` - Status as reported by the agent
  - `status.line` - A single line summary
  - `status.full` - A longer description of the current status
  - `status.html` - Full HTML status report (if available)
- `work_dir` - Working directory for this agent
- `create_time` - Creation timestamp
- `start_time` - Timestamp for when the agent was last started
- `runtime_seconds` - How long the agent has been running
- `user_activity_time` - Timestamp of the last user activity
- `agent_activity_time` - Timestamp of the last agent activity
- `ssh_activity_time` - Timestamp when we last noticed an active SSH connection
- `idle_seconds` - How long since the agent was active
- `idle_mode` - Idle detection mode
- `start_on_boot` - Whether the agent is set to start on host boot
- `state` - Agent lifecycle state (RUNNING, STOPPED, WAITING, REPLACED, DONE)
- `plugin.$PLUGIN_NAME.*` - Plugin-defined fields (e.g., `plugin.chat_history.messages`)

**Host fields** (dot notation for both `--fields` and CEL filters):
- `host.name` - Host name
- `host.id` - Host ID
- `host.host` - Hostname where the host is running (ssh.host for remote, localhost for local)
- `host.provider` - Host provider (local, docker, modal, etc.)
- `host.state` - Current host state (RUNNING, STOPPED, BUILDING, etc.)
- `host.image` - Host image (Docker image name, Modal image ID, etc.)
- `host.tags` - Metadata tags for the host
- `host.boot_time` - When the host was last started
- `host.uptime_seconds` - How long the host has been running
- `host.resource` - Resource limits for the host
  - `host.resource.cpu.count` - Number of CPUs
  - `host.resource.cpu.frequency_ghz` - CPU frequency in GHz
  - `host.resource.memory_gb` - Memory in GB
  - `host.resource.disk_gb` - Disk space in GB
  - `host.resource.gpu.count` - Number of GPUs
  - `host.resource.gpu.model` - GPU model name
  - `host.resource.gpu.memory_gb` - GPU memory in GB
- `host.ssh` - SSH access details (remote hosts only)
  - `host.ssh.command` - Full SSH command to connect
  - `host.ssh.host` - SSH hostname
  - `host.ssh.port` - SSH port
  - `host.ssh.user` - SSH username
  - `host.ssh.key_path` - Path to SSH private key
- `host.snapshots` - List of available snapshots
- `host.plugin.$PLUGIN_NAME.*` - Host plugin fields (e.g., `host.plugin.aws.iam_user`)

**Notes:**
- You can use Python-style list slicing for list fields (e.g., `host.snapshots[0]` for the first snapshot, `host.snapshots[:3]` for the first 3)
""",
        ),
        (
            "Related Documentation",
            """- [Multi-target Options](../generic/multi_target.md) - Behavior when some agents cannot be accessed
- [Common Options](../generic/common.md) - Common CLI options for output format, logging, etc.""",
        ),
    ),
    see_also=(
        ("create", "Create a new agent"),
        ("connect", "Connect to an existing agent"),
        ("destroy", "Destroy agents"),
    ),
)


# FIXME: Remaining host fields that need additional infrastructure:
# - host.is_locked, host.locked_time - Lock status (needs lock file inspection logic)
# - host.plugin.$PLUGIN_NAME.* - Plugin-defined fields (requires plugin field evaluation)

register_help_metadata("list", _LIST_HELP_METADATA)
# Also register under alias for consistent help output
for alias in _LIST_HELP_METADATA.aliases:
    register_help_metadata(alias, _LIST_HELP_METADATA)

# Add pager-enabled help option to the list command
add_pager_help_option(list_command)
