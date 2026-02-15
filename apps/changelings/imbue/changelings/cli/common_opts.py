from collections.abc import Callable
from pathlib import Path
from typing import Any
from typing import TypeVar

import click
from click_option_group import optgroup

from imbue.changelings.data_types import OutputOptions
from imbue.changelings.primitives import LogLevel
from imbue.changelings.primitives import OutputFormat
from imbue.changelings.utils.logging import setup_logging
from imbue.imbue_common.frozen_model import FrozenModel
from imbue.imbue_common.logging import log_span

# Constant for the "Common" option group name used across all commands
COMMON_OPTIONS_GROUP_NAME = "Common"

TDecorated = TypeVar("TDecorated", bound=Callable[..., Any])


class CommonCliOptions(FrozenModel):
    """Base class for common CLI options shared across all commands.

    This captures the options added by the @add_common_options decorator.
    """

    output_format: str
    quiet: bool
    verbose: int
    log_file: str | None


def add_common_options(command: TDecorated) -> TDecorated:
    """Decorator to add common options to a command.

    Adds the following options in the "Common" option group:
    - --format: Output format (human/json/jsonl)
    - -q, --quiet: Suppress console output
    - -v, --verbose: Increase verbosity
    - --log-file: Override log file path
    """
    # Apply decorators in reverse order (bottom to top)
    # These are wrapped in the "Common" option group
    command = optgroup.option(
        "--log-file",
        type=click.Path(),
        default=None,
        help="Path to log file (overrides default ~/.changelings/logs/<timestamp>-<pid>.json)",
    )(command)
    command = optgroup.option(
        "-v", "--verbose", count=True, help="Increase verbosity (default: BUILD); -v for DEBUG, -vv for TRACE"
    )(command)
    command = optgroup.option("-q", "--quiet", is_flag=True, help="Suppress all console output")(command)
    command = optgroup.option(
        "--format",
        "output_format",
        type=click.Choice(["human", "json", "jsonl"], case_sensitive=False),
        default="human",
        show_default=True,
        help="Output format for command results",
    )(command)
    # Start the "Common" option group - applied last since decorators run in reverse order
    command = optgroup.group(COMMON_OPTIONS_GROUP_NAME)(command)

    return command


def setup_command_context(
    ctx: click.Context,
    command_name: str,
) -> OutputOptions:
    """Set up logging for a command.

    This is the single entry point for command setup. Call this at the top of
    each command to parse common options, set up logging, and enter a log span
    for the command lifetime.
    """
    # Parse common options from the click context
    common_opts = CommonCliOptions(
        output_format=ctx.params["output_format"],
        quiet=ctx.params["quiet"],
        verbose=ctx.params["verbose"],
        log_file=ctx.params.get("log_file"),
    )

    # Parse output options from CLI flags
    output_opts = _parse_output_options(common_opts)

    # Set up logging
    setup_logging(output_opts)

    # Enter a log span for the command lifetime
    span = log_span("Started {} command", command_name)
    ctx.with_resource(span)

    return output_opts


def _parse_output_options(common_opts: CommonCliOptions) -> OutputOptions:
    """Parse common CLI options into OutputOptions."""
    # Parse output format
    parsed_output_format = OutputFormat(common_opts.output_format.upper())

    # Determine console level based on quiet and verbose flags
    if common_opts.quiet:
        console_level = LogLevel.NONE
    elif common_opts.verbose >= 2:
        console_level = LogLevel.TRACE
    elif common_opts.verbose == 1:
        console_level = LogLevel.DEBUG
    else:
        console_level = LogLevel.BUILD

    # Parse log file path
    log_file_path = Path(common_opts.log_file) if common_opts.log_file else None

    return OutputOptions(
        output_format=parsed_output_format,
        console_level=console_level,
        log_file_path=log_file_path,
    )
