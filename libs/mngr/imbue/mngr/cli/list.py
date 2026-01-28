import sys
from enum import Enum
from typing import Any

import click
from click_option_group import optgroup
from loguru import logger
from tabulate import tabulate

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
from imbue.mngr.primitives import ErrorBehavior
from imbue.mngr.primitives import OutputFormat


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
    help='Show only running agents (alias for --include state == "running")',
)
@optgroup.option(
    "--stopped",
    is_flag=True,
    help='Show only stopped agents (alias for --include state == "stopped")',
)
@optgroup.option(
    "--local",
    is_flag=True,
    help='Show only local agents (alias for --include host.provider == "local")',
)
@optgroup.option(
    "--remote",
    is_flag=True,
    help='Show only remote agents (alias for --exclude host.provider == "local")',
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
    help="Output format as a string template (mutually exclusive with --format)",
)
@optgroup.option(
    "--fields",
    help="Which fields to include (comma-separated)",
)
@optgroup.option(
    "--sort",
    default="create_time",
    help="Sort by field [default: create_time]",
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
    help="Limit number of results",
)
@optgroup.group("Watch Mode")
@optgroup.option(
    "-w",
    "--watch",
    type=int,
    help="Continuously watch and update status at specified interval (seconds) [default: 2]",
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
    logger.debug("Running list command")

    # TODO: Implement custom format templates
    # --format-template FORMAT: Output format as a string template, mutually exclusive with --format
    # Template can reference any field from the Available Fields list (see CommandHelpMetadata)
    if opts.format_template:
        raise NotImplementedError("Custom format templates not implemented yet")

    # Parse fields if provided
    fields = None
    if opts.fields:
        fields = [f.strip() for f in opts.fields.split(",") if f.strip()]

    # TODO: Implement watch mode
    # -w, --watch SECONDS: Continuously watch and update status at interval [default: 2]
    # Should refresh the agent list display periodically until interrupted
    if opts.watch:
        raise NotImplementedError("Watch mode not implemented yet")

    # Build list of include filters
    include_filters = list(opts.include)

    # Handle stdin input by converting to CEL filters
    if opts.stdin:
        stdin_refs = [line.strip() for line in sys.stdin if line.strip()]
        if stdin_refs:
            # Create a CEL filter that matches any of the provided refs against
            # host.name, host.id, agent.name, or agent.id
            ref_filters = []
            for ref in stdin_refs:
                ref_filter = f'(name == "{ref}" || id == "{ref}" || host.name == "{ref}" || host.id == "{ref}")'
                ref_filters.append(ref_filter)
            # Combine all ref filters with OR
            combined_filter = " || ".join(ref_filters)
            include_filters.append(combined_filter)

    # TODO: Implement convenience filter aliases
    # --running: alias for --include 'state == "running"'
    # --stopped: alias for --include 'state == "stopped"'
    # --local: alias for --include 'host.provider == "local"'
    # --remote: alias for --exclude 'host.provider == "local"'
    if opts.running or opts.stopped or opts.local or opts.remote:
        raise NotImplementedError("Convenience filter aliases not implemented yet")

    # TODO: Implement custom sorting
    # --sort FIELD: Sort by any available field [default: create_time]
    # --sort-order ORDER: Sort order (asc, desc) [default: asc]
    if opts.sort != "create_time":
        raise NotImplementedError("Custom sorting not implemented yet")

    # TODO: Implement result limiting
    # --limit N: Limit number of results returned
    if opts.limit:
        raise NotImplementedError("Result limiting not implemented yet")

    error_behavior = ErrorBehavior(opts.on_error.upper())

    # For JSONL format, use streaming callbacks to emit output as agents are found
    if output_opts.output_format == OutputFormat.JSONL:
        result = api_list_agents(
            mngr_ctx=mngr_ctx,
            include_filters=tuple(include_filters),
            exclude_filters=opts.exclude,
            provider_names=opts.provider if opts.provider else None,
            error_behavior=error_behavior,
            on_agent=_emit_jsonl_agent,
            on_error=_emit_jsonl_error,
        )
        # Exit with non-zero code if there were errors (per error_handling.md spec)
        if result.errors:
            ctx.exit(1)
        return

    # For other formats, collect all results first
    result = api_list_agents(
        mngr_ctx=mngr_ctx,
        include_filters=tuple(include_filters),
        exclude_filters=opts.exclude,
        provider_names=opts.provider if opts.provider else None,
        error_behavior=error_behavior,
    )

    if result.errors:
        for error in result.errors:
            logger.warning("{}: {}", error.exception_type, error.message)

    if not result.agents:
        if output_opts.output_format == OutputFormat.HUMAN:
            logger.info("No agents found")
        elif output_opts.output_format == OutputFormat.JSON:
            emit_final_json({"agents": [], "errors": result.errors})
        else:
            # JSONL is handled above with streaming, so this should be unreachable
            raise AssertionError(f"Unexpected output format: {output_opts.output_format}")
        # Exit with non-zero code if there were errors (per error_handling.md spec)
        if result.errors:
            ctx.exit(1)
        return

    if output_opts.output_format == OutputFormat.HUMAN:
        _emit_human_output(result.agents, fields)
    elif output_opts.output_format == OutputFormat.JSON:
        _emit_json_output(result.agents, result.errors)
    else:
        # JSONL is handled above with streaming, so this should be unreachable
        raise AssertionError(f"Unexpected output format: {output_opts.output_format}")

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

    If fields is None, uses default fields (name, state, status, host, provider).
    """
    if not agents:
        return

    # Default fields if none specified
    if fields is None:
        fields = ["name", "state", "status", "host", "provider"]

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


def _get_field_value(agent: AgentInfo, field: str) -> str:
    """Extract a field value from an AgentInfo object and return as string.

    Supports nested fields like "host.name" and handles field aliases.
    """
    # Handle special field aliases for backward compatibility and convenience
    field_aliases = {
        "state": "lifecycle_state",
        "host": "host.name",
        "provider": "host.provider_name",
    }

    # Apply alias if it exists
    if field in field_aliases:
        field = field_aliases[field]

    # Handle nested fields (e.g., "host.name")
    parts = field.split(".")
    value: Any = agent

    try:
        for part in parts:
            if hasattr(value, part):
                value = getattr(value, part)
            else:
                return ""

        # Convert various types to string
        # Check for enums first (before str check, since some enums inherit from str)
        if value is None:
            return ""
        elif isinstance(value, Enum):
            return str(value.value).lower()
        elif hasattr(value, "line"):
            # For AgentStatus objects which have a 'line' attribute
            return str(value.line)
        elif isinstance(value, str):
            return value
        else:
            return str(value)
    except (AttributeError, KeyError):
        return ""


# Register help metadata for git-style help formatting
_LIST_HELP_METADATA = CommandHelpMetadata(
    name="mngr-list",
    one_line_description="List all agents managed by mngr",
    synopsis="mngr list [OPTIONS]",
    description="""List all agents managed by mngr.

Displays agents with their status, host information, and other metadata.
Supports filtering, sorting, and multiple output formats.""",
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
- `state == "running"` - Match running agents
- `host.provider_name == "docker"` - Match agents on Docker hosts
- `type == "claude"` - Match agents of type "claude"

**Compound expressions:**
- `state == "running" && host.provider_name == "modal"` - Running agents on Modal
- `state == "stopped" || state == "failed"` - Stopped or failed agents

**String operations:**
- `name.contains("prod")` - Agent names containing "prod"
- `name.startsWith("staging-")` - Agent names starting with "staging-"
- `name.endsWith("-dev")` - Agent names ending with "-dev"

**Numeric comparisons:**
- `runtime_seconds > 3600` - Agents running for more than an hour

**Existence checks:**
- `has(url)` - Agents that have a URL set
""",
        ),
        (
            "Available Fields",
            """The following fields can be used with `--fields` and in CEL filter expressions.

**Agent fields:**
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
- `start_on_boot` - Whether the agent is set to start on host boot
- `state` - Lifecycle state (running, stopped, etc.) - derived from lifecycle_state
- `plugin` - Plugin-defined fields (dict)

**Host fields:**
- `host.name` - Host name
- `host.id` - Host ID
- `host.provider_name` - Host provider (local, docker, modal, etc.)
""",
        ),
    ),
)


# TODO: Expand HostInfo to include more fields for richer list output and filtering:
# - host.host - Hostname where the host is running
# - host.state - Current host state (building, starting, running, etc.)
# - host.image - Host image (Docker image name, Modal image ID, etc.)
# - host.tags - Metadata tags for the host
# - host.ssh.* - SSH access details (command, host, port, user, key_path)
# - host.resource.* - Resource limits (cpu.count, cpu.frequency_ghz, memory_gb, disk_gb)
# - host.snapshots - List of all available snapshots
# - host.boot_time, host.uptime_seconds - Host timing info
# - host.is_locked, host.locked_time - Lock status
# - host.plugin.$PLUGIN_NAME.* - Plugin-defined fields
# See libs/mngr/docs/commands/primary/list.md (original) for full planned field list

register_help_metadata("list", _LIST_HELP_METADATA)

# Add pager-enabled help option to the list command
add_pager_help_option(list_command)
