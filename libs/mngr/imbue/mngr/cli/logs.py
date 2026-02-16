import sys
from typing import Any
from typing import assert_never

import click
from click_option_group import optgroup
from loguru import logger

from imbue.mngr.api.logs import LogFileEntry
from imbue.mngr.api.logs import apply_head_or_tail
from imbue.mngr.api.logs import follow_log_file
from imbue.mngr.api.logs import list_log_files
from imbue.mngr.api.logs import read_log_content
from imbue.mngr.api.logs import resolve_logs_target
from imbue.mngr.cli.common_opts import CommonCliOptions
from imbue.mngr.cli.common_opts import add_common_options
from imbue.mngr.cli.common_opts import setup_command_context
from imbue.mngr.cli.completion import complete_agent_name
from imbue.mngr.cli.help_formatter import CommandHelpMetadata
from imbue.mngr.cli.help_formatter import add_pager_help_option
from imbue.mngr.cli.help_formatter import register_help_metadata
from imbue.mngr.cli.output_helpers import emit_final_json
from imbue.mngr.cli.output_helpers import emit_format_template_lines
from imbue.mngr.cli.output_helpers import write_human_line
from imbue.mngr.config.data_types import OutputOptions
from imbue.mngr.errors import MngrError
from imbue.mngr.errors import UserInputError
from imbue.mngr.primitives import OutputFormat


class LogsCliOptions(CommonCliOptions):
    """Options passed from the CLI to the logs command.

    Inherits common options (output_format, quiet, verbose, etc.) from CommonCliOptions.
    """

    target: str
    log_filename: str | None
    follow: bool
    tail: int | None
    head: int | None


def _write_and_flush_stdout(content: str) -> None:
    """Write content to stdout and flush immediately for piped output."""
    sys.stdout.write(content)
    sys.stdout.flush()


@click.command(name="logs")
@click.argument("target", shell_complete=complete_agent_name)
@click.argument("log_filename", required=False, default=None)
@optgroup.group("Display")
@optgroup.option(
    "--follow/--no-follow",
    default=False,
    show_default=True,
    help="Continue running and print new messages as they appear",
)
@optgroup.option(
    "--tail",
    type=click.IntRange(min=1),
    default=None,
    help="Print the last N lines of the log",
)
@optgroup.option(
    "--head",
    type=click.IntRange(min=1),
    default=None,
    help="Print the first N lines of the log",
)
@add_common_options
@click.pass_context
def logs(ctx: click.Context, **kwargs: Any) -> None:
    """View log files from an agent or host.

    TARGET is an agent name/ID or host name/ID. If a log file name is not
    specified, lists all available log files.

    When listing files, supports custom format templates via --format.
    Available fields: name, size.

    \b
    Examples:
      mngr logs my-agent
      mngr logs my-agent output.log
      mngr logs my-agent output.log --tail 50
      mngr logs my-agent output.log --follow
      mngr logs my-agent --format '{name}\\t{size}'
    """
    mngr_ctx, output_opts, opts = setup_command_context(
        ctx=ctx,
        command_name="logs",
        command_class=LogsCliOptions,
        is_format_template_supported=True,
    )

    # Validate mutually exclusive options
    if opts.head is not None and opts.tail is not None:
        raise UserInputError("Cannot specify both --head and --tail")

    if opts.follow and opts.head is not None:
        raise UserInputError("Cannot use --head with --follow")

    # Resolve the target (agent or host)
    target = resolve_logs_target(
        identifier=opts.target,
        mngr_ctx=mngr_ctx,
    )

    # If no log file specified, list available log files
    if opts.log_filename is None:
        log_files = list_log_files(target)
        _emit_log_file_list(log_files, target.display_name, output_opts)
        return

    # Format templates only apply to file listing, not to viewing file content
    if output_opts.format_template is not None:
        raise UserInputError(
            "Format template strings are only supported when listing log files (without a filename argument). "
            "Use --format human, --format json, or --format jsonl when viewing log content."
        )

    if opts.follow:
        # Follow mode: poll and print new content
        logger.info("Following log file '{}' for {} (Ctrl+C to stop)", opts.log_filename, target.display_name)
        try:
            follow_log_file(
                target=target,
                log_file_name=opts.log_filename,
                on_new_content=_write_and_flush_stdout,
                tail_count=opts.tail,
            )
        except KeyboardInterrupt:
            # Clean exit on Ctrl+C
            sys.stdout.write("\n")
            sys.stdout.flush()
        return

    # Read and display the log file
    try:
        content = read_log_content(target, opts.log_filename)
    except (MngrError, OSError) as e:
        raise MngrError(f"Failed to read log file '{opts.log_filename}': {e}") from e

    filtered_content = apply_head_or_tail(content, head_count=opts.head, tail_count=opts.tail)
    _emit_log_content(filtered_content, opts.log_filename, output_opts)


def _emit_log_file_list(
    log_files: list[LogFileEntry],
    display_name: str,
    output_opts: OutputOptions,
) -> None:
    """Emit the list of available log files."""
    if output_opts.format_template is not None:
        items = [{"name": lf.name, "size": str(lf.size)} for lf in log_files]
        emit_format_template_lines(output_opts.format_template, items)
        return
    match output_opts.output_format:
        case OutputFormat.HUMAN:
            if not log_files:
                write_human_line("No log files found for {}", display_name)
            else:
                write_human_line("Log files for {}:", display_name)
                for log_file in log_files:
                    write_human_line("  {} ({} bytes)", log_file.name, log_file.size)
        case OutputFormat.JSON | OutputFormat.JSONL:
            emit_final_json(
                {
                    "target": display_name,
                    "log_files": [{"name": lf.name, "size": lf.size} for lf in log_files],
                }
            )
        case _ as unreachable:
            assert_never(unreachable)


def _emit_log_content(
    content: str,
    log_file_name: str,
    output_opts: OutputOptions,
) -> None:
    """Emit log content in the appropriate format."""
    match output_opts.output_format:
        case OutputFormat.HUMAN:
            sys.stdout.write(content)
            if content and not content.endswith("\n"):
                sys.stdout.write("\n")
            sys.stdout.flush()
        case OutputFormat.JSON | OutputFormat.JSONL:
            emit_final_json(
                {
                    "log_file": log_file_name,
                    "content": content,
                }
            )
        case _ as unreachable:
            assert_never(unreachable)


# Register help metadata for git-style help formatting
_LOGS_HELP_METADATA = CommandHelpMetadata(
    name="mngr-logs",
    one_line_description="View log files from an agent or host",
    synopsis="mngr logs TARGET [LOG_FILE] [--follow] [--tail N] [--head N]",
    arguments_description=(
        "- `TARGET`: Agent or host name/ID whose logs to view\n"
        "- `LOG_FILE`: Name of the log file to view (optional; lists files if omitted)"
    ),
    description="""View log files from an agent or host.

TARGET identifies an agent (by name or ID) or a host (by name or ID).
The command first tries to match TARGET as an agent, then as a host.

If LOG_FILE is not specified, lists all available log files.
If LOG_FILE is specified, prints its contents.

In follow mode (--follow), the command polls for new content and
prints it as it appears, similar to 'tail -f'. Press Ctrl+C to stop.""",
    examples=(
        ("List available log files for an agent", "mngr logs my-agent"),
        ("View a specific log file", "mngr logs my-agent output.log"),
        ("View the last 50 lines", "mngr logs my-agent output.log --tail 50"),
        ("Follow a log file", "mngr logs my-agent output.log --follow"),
    ),
    see_also=(
        ("list", "List available agents"),
        ("exec", "Execute commands on an agent's host"),
    ),
)

register_help_metadata("logs", _LOGS_HELP_METADATA)

# Add pager-enabled help option to the logs command
add_pager_help_option(logs)
