import shlex
import subprocess
from pathlib import Path
from typing import Any
from typing import assert_never

import click
from click_option_group import optgroup
from loguru import logger

from imbue.mngr.cli.common_opts import CommonCliOptions
from imbue.mngr.cli.common_opts import add_common_options
from imbue.mngr.cli.common_opts import setup_command_context
from imbue.mngr.cli.help_formatter import CommandHelpMetadata
from imbue.mngr.cli.help_formatter import add_pager_help_option
from imbue.mngr.cli.help_formatter import register_help_metadata
from imbue.mngr.cli.output_helpers import emit_final_json
from imbue.mngr.cli.output_helpers import emit_info
from imbue.mngr.errors import MngrError
from imbue.mngr.primitives import OutputFormat

_QUERY_PREFIX = (
    "answer this question about `mngr`. "
    "respond with the valid mngr command only, with no markdown formatting or explanation: "
)

_EXECUTE_QUERY_PREFIX = (
    "answer this question about `mngr`. "
    "respond with ONLY the valid mngr command, with no markdown formatting, explanation, or extra text. "
    "the output will be executed directly as a shell command: "
)


class AskCliOptions(CommonCliOptions):
    """Options passed from the CLI to the ask command."""

    query: tuple[str, ...]
    execute: bool


@click.command(name="ask")
@click.argument("query", nargs=-1, required=False)
@optgroup.group("Behavior")
@optgroup.option(
    "--execute",
    is_flag=True,
    help="Execute the generated CLI command instead of just printing it",
)
@add_common_options
@click.pass_context
def ask(ctx: click.Context, **kwargs: Any) -> None:
    """Chat with mngr for help.

    Ask mngr a question and it will generate the appropriate CLI command.
    If no query is provided, shows general help.

    Examples:

      mngr ask "how do I create an agent?"

      mngr ask start a container with claude code

      mngr ask --execute forward port 8080 to the public internet
    """
    _mngr_ctx, output_opts, opts = setup_command_context(
        ctx=ctx,
        command_name="ask",
        command_class=AskCliOptions,
    )
    logger.debug("Started ask command")

    if not opts.query:
        raise click.UsageError("No query provided. Pass a question as arguments.", ctx=ctx)

    prefix = _EXECUTE_QUERY_PREFIX if opts.execute else _QUERY_PREFIX
    query_string = prefix + " ".join(opts.query)

    cwd = Path(opts.project_context_path) if opts.project_context_path else None

    emit_info("Thinking...", output_opts.output_format)

    response = _run_claude_print(query_string, cwd)

    if opts.execute:
        _execute_response(response=response, output_format=output_opts.output_format)
    else:
        _emit_response(response=response, output_format=output_opts.output_format)


def _run_claude_print(query_string: str, cwd: Path | None) -> str:
    """Run claude --print and return the response text."""
    result = subprocess.run(
        ["claude", "--print", query_string],
        capture_output=True,
        text=True,
        stdin=subprocess.DEVNULL,
        cwd=cwd,
    )

    if result.returncode != 0:
        stderr_msg = result.stderr.strip()
        stdout_msg = result.stdout.strip()
        detail = stderr_msg or stdout_msg or "unknown error (no output captured)"
        raise MngrError(f"claude --print failed (exit code {result.returncode}): {detail}")

    return result.stdout.rstrip("\n")


def _emit_response(response: str, output_format: OutputFormat) -> None:
    """Emit the ask response in the appropriate format."""
    match output_format:
        case OutputFormat.HUMAN:
            logger.info("{}", response)
        case OutputFormat.JSON:
            emit_final_json({"response": response})
        case OutputFormat.JSONL:
            emit_final_json({"event": "response", "response": response})
        case _ as unreachable:
            assert_never(unreachable)


def _execute_response(response: str, output_format: OutputFormat) -> None:
    """Execute the command from claude's response."""
    command = response.strip()
    if not command:
        raise MngrError("claude returned an empty response; nothing to execute")

    emit_info(f"Running: {command}", output_format)

    args = shlex.split(command)
    result = subprocess.run(args, capture_output=False)

    if result.returncode != 0:
        raise MngrError(f"command failed (exit code {result.returncode}): {command}")


# Register help metadata for git-style help formatting
_ASK_HELP_METADATA = CommandHelpMetadata(
    name="mngr-ask",
    one_line_description="Chat with mngr for help",
    synopsis="mngr ask [--execute] QUERY...",
    description="""Chat directly with mngr for help -- it can create the
necessary CLI call for pretty much anything you want to do.

If no query is provided, shows general help about available commands
and common workflows.

When --execute is specified, the generated CLI command is executed
directly instead of being printed.""",
    examples=(
        ("Ask a question", 'mngr ask "how do I create an agent?"'),
        ("Ask without quotes", "mngr ask start a container with claude code"),
        ("Execute the generated command", "mngr ask --execute forward port 8080 to the public internet"),
    ),
    see_also=(
        ("create", "Create an agent"),
        ("list", "List existing agents"),
        ("connect", "Connect to an agent"),
    ),
)

register_help_metadata("ask", _ASK_HELP_METADATA)

# Add pager-enabled help option to the ask command
add_pager_help_option(ask)
