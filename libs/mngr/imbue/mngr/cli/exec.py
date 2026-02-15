import sys
from typing import Any
from typing import assert_never

import click
from click_option_group import optgroup
from loguru import logger

from imbue.mngr.api.exec import ExecResult
from imbue.mngr.api.exec import exec_command_on_agent
from imbue.mngr.cli.common_opts import CommonCliOptions
from imbue.mngr.cli.common_opts import add_common_options
from imbue.mngr.cli.common_opts import setup_command_context
from imbue.mngr.cli.help_formatter import CommandHelpMetadata
from imbue.mngr.cli.help_formatter import add_pager_help_option
from imbue.mngr.cli.help_formatter import register_help_metadata
from imbue.mngr.cli.output_helpers import emit_event
from imbue.mngr.cli.output_helpers import emit_final_json
from imbue.mngr.config.data_types import OutputOptions
from imbue.mngr.primitives import OutputFormat


class ExecCliOptions(CommonCliOptions):
    """Options passed from the CLI to the exec command.

    Inherits common options (output_format, quiet, verbose, etc.) from CommonCliOptions.
    """

    agent: str
    command_arg: str
    user: str | None
    cwd: str | None
    timeout: float | None
    start: bool


@click.command(name="exec")
# FIXME: like our other commands (destroy, message, etc), we should be able to specify multiple agents that we want to run the command against
#  note that this will require similar "what should happen on error" logic (eg, abort on first failure, continue, or retry until success/timeout)
@click.argument("agent")
@click.argument("command_arg", metavar="COMMAND")
@optgroup.group("Execution")
@optgroup.option(
    "--user",
    default=None,
    help="User to run the command as",
)
@optgroup.option(
    "--cwd",
    default=None,
    help="Working directory for the command (default: agent's work_dir)",
)
@optgroup.option(
    "--timeout",
    type=float,
    default=None,
    help="Timeout in seconds for the command",
)
@optgroup.group("General")
@optgroup.option(
    "--start/--no-start",
    default=True,
    show_default=True,
    help="Automatically start the host/agent if stopped",
)
@add_common_options
@click.pass_context
def exec_command(ctx: click.Context, **kwargs: Any) -> None:
    """Execute a shell command on an agent's host.

    Runs COMMAND on the host where AGENT is running, defaulting to the
    agent's work_dir. The command's stdout is printed to stdout and stderr
    to stderr.

    \b
    Alias: x
    """
    mngr_ctx, output_opts, opts = setup_command_context(
        ctx=ctx,
        command_name="exec",
        command_class=ExecCliOptions,
    )
    logger.debug("Started exec command")

    result = exec_command_on_agent(
        mngr_ctx=mngr_ctx,
        agent_str=opts.agent,
        command=opts.command_arg,
        user=opts.user,
        cwd=opts.cwd,
        timeout_seconds=opts.timeout,
        is_start_desired=opts.start,
    )

    _emit_output(result, output_opts)

    if not result.success:
        ctx.exit(1)


def _emit_output(result: ExecResult, output_opts: OutputOptions) -> None:
    """Emit output based on the result and format."""
    match output_opts.output_format:
        case OutputFormat.HUMAN:
            _emit_human_output(result)
        case OutputFormat.JSON:
            _emit_json_output(result)
        case OutputFormat.JSONL:
            _emit_jsonl_output(result)
        case _ as unreachable:
            assert_never(unreachable)


def _emit_human_output(result: ExecResult) -> None:
    """Emit human-readable output.

    Prints command stdout directly to stdout and stderr to stderr,
    then logs success/failure status.
    """
    if result.stdout:
        sys.stdout.write(result.stdout)
        if not result.stdout.endswith("\n"):
            sys.stdout.write("\n")
        sys.stdout.flush()

    if result.stderr:
        sys.stderr.write(result.stderr)
        if not result.stderr.endswith("\n"):
            sys.stderr.write("\n")
        sys.stderr.flush()

    if result.success:
        logger.info("Command succeeded on agent {}", result.agent_name)
    else:
        logger.error("Command failed on agent {}", result.agent_name)


def _emit_json_output(result: ExecResult) -> None:
    """Emit JSON output."""
    emit_final_json(
        {
            "agent": result.agent_name,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "success": result.success,
        }
    )


def _emit_jsonl_output(result: ExecResult) -> None:
    """Emit JSONL output."""
    emit_event(
        "exec_result",
        {
            "agent": result.agent_name,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "success": result.success,
        },
        OutputFormat.JSONL,
    )


# Register help metadata for git-style help formatting
_EXEC_HELP_METADATA = CommandHelpMetadata(
    name="mngr-exec",
    one_line_description="Execute a shell command on an agent's host",
    synopsis="mngr [exec|x] AGENT COMMAND [--user <USER>] [--cwd <DIR>] [--timeout <SECONDS>]",
    arguments_description=(
        "- `AGENT`: Name or ID of the agent whose host will run the command\n"
        "- `COMMAND`: Shell command to execute on the agent's host"
    ),
    description="""Execute a shell command on the host where an agent runs.

The command runs in the agent's work_dir by default. Use --cwd to override
the working directory.

The command's stdout is printed to stdout and stderr to stderr. The exit
code is 0 if the command succeeded, 1 if it failed.""",
    aliases=("x",),
    examples=(
        ("Run a command on an agent", 'mngr exec my-agent "echo hello"'),
        ("Run with a custom working directory", 'mngr exec my-agent "ls -la" --cwd /tmp'),
        ("Run as a different user", 'mngr exec my-agent "whoami" --user root'),
        ("Run with a timeout", 'mngr exec my-agent "sleep 100" --timeout 5'),
    ),
    see_also=(
        ("connect", "Connect to an agent interactively"),
        ("message", "Send a message to an agent"),
        ("list", "List available agents"),
    ),
)

register_help_metadata("exec", _EXEC_HELP_METADATA)
for alias in _EXEC_HELP_METADATA.aliases:
    register_help_metadata(alias, _EXEC_HELP_METADATA)

# Add pager-enabled help option to the exec command
add_pager_help_option(exec_command)
