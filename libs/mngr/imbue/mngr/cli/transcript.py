import sys
from typing import assert_never

import click
from loguru import logger

from imbue.mngr.api.transcript import TranscriptResult
from imbue.mngr.api.transcript import get_agent_transcript
from imbue.mngr.cli.common_opts import CommonCliOptions
from imbue.mngr.cli.common_opts import add_common_options
from imbue.mngr.cli.common_opts import setup_command_context
from imbue.mngr.cli.help_formatter import CommandHelpMetadata
from imbue.mngr.cli.help_formatter import add_pager_help_option
from imbue.mngr.cli.help_formatter import register_help_metadata
from imbue.mngr.cli.output_helpers import emit_final_json
from imbue.mngr.config.data_types import OutputOptions
from imbue.mngr.primitives import OutputFormat


class TranscriptCliOptions(CommonCliOptions):
    """Options passed from the CLI to the transcript command.

    Inherits common options (output_format, quiet, verbose, etc.) from CommonCliOptions.

    Note that this class VERY INTENTIONALLY DOES NOT use Field() decorators with descriptions, defaults, etc.
    For that information, see the click.option() and click.argument() decorators on the transcript() function itself.
    """

    agent: str


@click.command(name="transcript")
@click.argument("agent", required=True)
@add_common_options
@click.pass_context
def transcript(ctx: click.Context, **kwargs) -> None:
    """Retrieve the raw JSONL session transcript for an agent.

    Reads the Claude Code session data from the agent's host and outputs
    the raw JSONL content to stdout.

    Examples:

      mngr transcript my-agent

      mngr transcript my-agent --format json
    """
    _transcript_impl(ctx, **kwargs)


def _transcript_impl(ctx: click.Context, **kwargs) -> None:
    """Implementation of transcript command (extracted for exception handling)."""
    mngr_ctx, output_opts, opts = setup_command_context(
        ctx=ctx,
        command_name="transcript",
        command_class=TranscriptCliOptions,
    )
    logger.debug("Started transcript command")

    result = get_agent_transcript(
        mngr_ctx=mngr_ctx,
        agent_identifier=opts.agent,
    )

    _emit_output(result, output_opts)


def _emit_output(result: TranscriptResult, output_opts: OutputOptions) -> None:
    """Emit output based on the result and format."""
    match output_opts.output_format:
        case OutputFormat.HUMAN:
            _emit_raw_output(result)
        case OutputFormat.JSONL:
            _emit_raw_output(result)
        case OutputFormat.JSON:
            _emit_json_output(result)
        case _ as unreachable:
            assert_never(unreachable)


def _emit_raw_output(result: TranscriptResult) -> None:
    """Emit raw JSONL content to stdout."""
    sys.stdout.write(result.content)
    if result.content and not result.content.endswith("\n"):
        sys.stdout.write("\n")
    sys.stdout.flush()


def _emit_json_output(result: TranscriptResult) -> None:
    """Emit JSON output wrapping the transcript content."""
    output_data = {
        "agent_name": result.agent_name,
        "session_file_path": str(result.session_file_path),
        "content": result.content,
    }
    emit_final_json(output_data)


# Register help metadata for git-style help formatting
_TRANSCRIPT_HELP_METADATA = CommandHelpMetadata(
    name="mngr-transcript",
    one_line_description="Retrieve the raw JSONL session transcript for an agent",
    synopsis="mngr transcript <AGENT>",
    description="""Retrieve the raw JSONL session transcript for an agent.

Reads the Claude Code session data from the agent's host and outputs
the raw JSONL content to stdout. The session file is located by searching
for the agent's UUID under ~/.claude/projects/ on the host.""",
    examples=(
        ("View an agent's transcript", "mngr transcript my-agent"),
        ("Get transcript as JSON", "mngr transcript my-agent --format json"),
        ("Pipe transcript to jq for processing", "mngr transcript my-agent | jq ."),
    ),
    see_also=(
        ("message", "Send a message to one or more agents"),
        ("list", "List available agents"),
        ("connect", "Connect to an agent interactively"),
    ),
)

register_help_metadata("transcript", _TRANSCRIPT_HELP_METADATA)

# Add pager-enabled help option to the transcript command
add_pager_help_option(transcript)
