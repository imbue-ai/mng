# Tests for common CLI options parsing and setup.

from pathlib import Path

from imbue.changelings.cli.common_opts import CommonCliOptions
from imbue.changelings.cli.common_opts import _parse_output_options
from imbue.changelings.primitives import LogLevel
from imbue.changelings.primitives import OutputFormat


def test_parse_output_options_defaults_to_build_level() -> None:
    """Default options (no quiet, no verbose) should use BUILD console level."""
    common_opts = CommonCliOptions(output_format="human", quiet=False, verbose=0, log_file=None)

    result = _parse_output_options(common_opts)

    assert result.console_level == LogLevel.BUILD
    assert result.output_format == OutputFormat.HUMAN
    assert result.log_file_path is None


def test_parse_output_options_quiet_sets_none_level() -> None:
    """--quiet should suppress console output by setting NONE level."""
    common_opts = CommonCliOptions(output_format="human", quiet=True, verbose=0, log_file=None)

    result = _parse_output_options(common_opts)

    assert result.console_level == LogLevel.NONE


def test_parse_output_options_verbose_one_sets_debug_level() -> None:
    """-v should set DEBUG console level."""
    common_opts = CommonCliOptions(output_format="human", quiet=False, verbose=1, log_file=None)

    result = _parse_output_options(common_opts)

    assert result.console_level == LogLevel.DEBUG


def test_parse_output_options_verbose_two_sets_trace_level() -> None:
    """-vv should set TRACE console level."""
    common_opts = CommonCliOptions(output_format="human", quiet=False, verbose=2, log_file=None)

    result = _parse_output_options(common_opts)

    assert result.console_level == LogLevel.TRACE


def test_parse_output_options_verbose_three_still_sets_trace_level() -> None:
    """-vvv should still set TRACE console level (maximum verbosity)."""
    common_opts = CommonCliOptions(output_format="human", quiet=False, verbose=3, log_file=None)

    result = _parse_output_options(common_opts)

    assert result.console_level == LogLevel.TRACE


def test_parse_output_options_log_file_creates_path() -> None:
    """--log-file should produce a Path in the output options."""
    common_opts = CommonCliOptions(output_format="human", quiet=False, verbose=0, log_file="/tmp/test.json")

    result = _parse_output_options(common_opts)

    assert result.log_file_path == Path("/tmp/test.json")


def test_parse_output_options_json_format() -> None:
    """--format json should set JSON output format."""
    common_opts = CommonCliOptions(output_format="json", quiet=False, verbose=0, log_file=None)

    result = _parse_output_options(common_opts)

    assert result.output_format == OutputFormat.JSON


def test_parse_output_options_jsonl_format() -> None:
    """--format jsonl should set JSONL output format."""
    common_opts = CommonCliOptions(output_format="jsonl", quiet=False, verbose=0, log_file=None)

    result = _parse_output_options(common_opts)

    assert result.output_format == OutputFormat.JSONL


def test_parse_output_options_format_is_case_insensitive() -> None:
    """Format parsing should be case-insensitive."""
    common_opts = CommonCliOptions(output_format="JSON", quiet=False, verbose=0, log_file=None)

    result = _parse_output_options(common_opts)

    assert result.output_format == OutputFormat.JSON
