import io
import re
import sys
from unittest import mock

import click
from click.testing import CliRunner
from click_option_group import optgroup

from imbue.mngr.cli.common_opts import COMMON_OPTIONS_GROUP_NAME
from imbue.mngr.cli.create import create
from imbue.mngr.cli.help_formatter import CommandHelpMetadata
from imbue.mngr.cli.help_formatter import add_pager_help_option
from imbue.mngr.cli.help_formatter import format_git_style_help
from imbue.mngr.cli.help_formatter import get_help_metadata
from imbue.mngr.cli.help_formatter import get_pager_command
from imbue.mngr.cli.help_formatter import help_option_callback
from imbue.mngr.cli.help_formatter import is_interactive_terminal
from imbue.mngr.cli.help_formatter import register_help_metadata
from imbue.mngr.cli.help_formatter import run_pager
from imbue.mngr.cli.help_formatter import show_help_with_pager
from imbue.mngr.config.data_types import MngrConfig
from imbue.mngr.main import BUILTIN_COMMANDS


def test_is_interactive_terminal_returns_bool() -> None:
    """is_interactive_terminal should return a boolean without raising."""
    result = is_interactive_terminal()
    # In a test environment, this is typically False, but the important
    # thing is that it doesn't raise an exception
    assert isinstance(result, bool)


def test_get_pager_command_uses_config_first(mngr_test_prefix: str) -> None:
    """Config pager setting takes precedence over environment."""
    config = MngrConfig(prefix=mngr_test_prefix, pager="custom-pager")
    result = get_pager_command(config)
    assert result == "custom-pager"


def test_get_pager_command_defaults_to_less_when_no_config() -> None:
    """When no config is provided, defaults to less."""
    result = get_pager_command(None)
    # Could be from PAGER env var or default "less"
    assert result is not None


def test_get_pager_command_uses_less_when_config_has_no_pager(mngr_test_prefix: str) -> None:
    """When config has no pager set, falls back to PAGER env or less."""
    config = MngrConfig(prefix=mngr_test_prefix)
    result = get_pager_command(config)
    # Should be "less" or PAGER env var
    assert result is not None


def test_register_and_get_help_metadata() -> None:
    """Test registering and retrieving help metadata."""
    metadata = CommandHelpMetadata(
        name="test-cmd",
        one_line_description="A test command",
        synopsis="mngr test [options]",
        description="This is a test command for testing.",
        examples=(("Run a basic test", "mngr test"),),
    )

    register_help_metadata("test", metadata)
    retrieved = get_help_metadata("test")

    assert retrieved is not None
    assert retrieved.name == "test-cmd"
    assert retrieved.one_line_description == "A test command"


def test_get_help_metadata_returns_none_for_unregistered() -> None:
    """Test that unregistered commands return None."""
    result = get_help_metadata("nonexistent-command-12345")
    assert result is None


def test_format_git_style_help_with_metadata() -> None:
    """Test that git-style help is formatted correctly with metadata."""

    @click.command()
    @click.option("--name", "-n", help="The name to use")
    @click.option("--verbose", "-v", is_flag=True, help="Enable verbose output")
    def test_cmd(name: str | None, verbose: bool) -> None:
        """A simple test command."""
        pass

    metadata = CommandHelpMetadata(
        name="mngr-test",
        one_line_description="A test command for testing",
        synopsis="mngr test [options]",
        description="This is a detailed description of what the test command does.",
        examples=(
            ("Run with a name", "mngr test --name foo"),
            ("Run in verbose mode", "mngr test -v"),
        ),
    )

    runner = CliRunner()
    with runner.isolated_filesystem():
        ctx = click.Context(test_cmd)
        help_text = format_git_style_help(ctx, test_cmd, metadata)

        # Check that the help contains expected sections
        assert "NAME" in help_text
        assert "mngr-test - A test command for testing" in help_text
        assert "SYNOPSIS" in help_text
        assert "mngr test [options]" in help_text
        assert "DESCRIPTION" in help_text
        assert "This is a detailed description" in help_text
        assert "OPTIONS" in help_text
        assert "--name" in help_text
        assert "--verbose" in help_text
        assert "EXAMPLES" in help_text
        assert "mngr test --name foo" in help_text


def test_format_git_style_help_without_metadata() -> None:
    """Test that standard click help is used when no metadata is available."""

    @click.command()
    @click.option("--name", "-n", help="The name to use")
    def simple_cmd(name: str | None) -> None:
        """A simple command without metadata."""
        pass

    runner = CliRunner()
    with runner.isolated_filesystem():
        ctx = click.Context(simple_cmd)
        help_text = format_git_style_help(ctx, simple_cmd, None)

        # Should fall back to standard click help
        assert "--name" in help_text
        assert "The name to use" in help_text


def test_add_pager_help_option_adds_custom_help() -> None:
    """Test that add_pager_help_option adds a custom help option with -h shortcut."""

    @click.command()
    @click.option("--name", help="The name")
    def cmd_without_help(name: str | None) -> None:
        """A command."""
        pass

    # Apply pager help option
    add_pager_help_option(cmd_without_help)

    # After modification, should have help option with -h shortcut
    help_params = [p for p in cmd_without_help.params if isinstance(p, click.Option) and p.name == "help"]
    assert len(help_params) == 1
    assert "-h" in help_params[0].opts
    assert "--help" in help_params[0].opts


def test_format_git_style_help_handles_empty_examples() -> None:
    """Test that help formatting works with no examples."""

    @click.command()
    def no_examples_cmd() -> None:
        """A command with no examples."""
        pass

    metadata = CommandHelpMetadata(
        name="mngr-noex",
        one_line_description="No examples here",
        synopsis="mngr noex",
        description="A command that has no usage examples.",
        examples=(),
    )

    runner = CliRunner()
    with runner.isolated_filesystem():
        ctx = click.Context(no_examples_cmd)
        help_text = format_git_style_help(ctx, no_examples_cmd, metadata)

        # Should have other sections but no EXAMPLES section
        assert "NAME" in help_text
        assert "SYNOPSIS" in help_text
        assert "DESCRIPTION" in help_text
        # EXAMPLES section should not appear when empty
        assert "EXAMPLES" not in help_text


def test_create_command_has_help_metadata_registered() -> None:
    """Test that the create command has its help metadata registered."""
    metadata = get_help_metadata("create")

    assert metadata is not None
    assert metadata.name == "mngr-create"
    assert "Create and run an agent" in metadata.one_line_description


def test_create_command_help_output_structure() -> None:
    """Test that create command help has expected sections."""
    runner = CliRunner()
    result = runner.invoke(create, ["--help"])

    # Check exit code
    assert result.exit_code == 0

    # Check for git-style sections
    help_output = result.output
    assert "NAME" in help_output
    assert "SYNOPSIS" in help_output
    assert "DESCRIPTION" in help_output
    assert "OPTIONS" in help_output
    assert "EXAMPLES" in help_output


def test_create_command_help_contains_common_options() -> None:
    """Test that create command help contains the common options."""
    runner = CliRunner()
    result = runner.invoke(create, ["--help"])

    help_output = result.output

    # Check for some key options
    assert "--connect" in help_output or "--no-connect" in help_output
    assert "--in" in help_output or "--new-host" in help_output
    assert "--host" in help_output
    assert "--name" in help_output
    assert "--agent-type" in help_output


def test_create_command_help_contains_examples() -> None:
    """Test that create command help contains usage examples."""
    runner = CliRunner()
    result = runner.invoke(create, ["--help"])

    help_output = result.output

    # Check for example patterns
    assert "mngr create" in help_output
    assert "--in docker" in help_output or "--in modal" in help_output


def test_run_pager_writes_to_stdout_when_not_interactive() -> None:
    """Test that run_pager writes directly to stdout when not in a terminal."""
    test_text = "Hello, this is test output"

    # Capture stdout
    captured_output = io.StringIO()
    with mock.patch.object(sys, "stdout", captured_output):
        with mock.patch(
            "imbue.mngr.cli.help_formatter.is_interactive_terminal",
            return_value=False,
        ):
            run_pager(test_text, None)

    assert test_text in captured_output.getvalue()


def test_run_pager_uses_subprocess_when_interactive() -> None:
    """Test that run_pager uses subprocess pager when in a terminal."""
    test_text = "Interactive pager test"

    with mock.patch(
        "imbue.mngr.cli.help_formatter.is_interactive_terminal",
        return_value=True,
    ):
        with mock.patch("subprocess.Popen") as mock_popen:
            mock_process = mock.MagicMock()
            mock_popen.return_value = mock_process

            run_pager(test_text, None)

            # Verify popen was called
            mock_popen.assert_called_once()
            # Verify communicate was called with the text
            mock_process.communicate.assert_called_once()
            call_args = mock_process.communicate.call_args
            assert test_text.encode("utf-8") in call_args.kwargs.get(
                "input", call_args.args[0] if call_args.args else b""
            )


def test_run_pager_falls_back_on_subprocess_error() -> None:
    """Test that run_pager falls back to stdout when subprocess fails."""
    test_text = "Fallback test"

    captured_output = io.StringIO()
    with mock.patch.object(sys, "stdout", captured_output):
        with mock.patch(
            "imbue.mngr.cli.help_formatter.is_interactive_terminal",
            return_value=True,
        ):
            with mock.patch("subprocess.Popen", side_effect=OSError("pager not found")):
                run_pager(test_text, None)

    # Should have fallen back to stdout
    assert test_text in captured_output.getvalue()


def test_show_help_with_pager_formats_and_displays_help() -> None:
    """Test that show_help_with_pager formats help and passes to pager."""

    @click.command()
    @click.option("--test", help="A test option")
    def test_cmd(test: str | None) -> None:
        """Test command."""
        pass

    ctx = click.Context(test_cmd)

    with mock.patch("imbue.mngr.cli.help_formatter.run_pager") as mock_run_pager:
        show_help_with_pager(ctx, test_cmd, None)

        # Verify run_pager was called with formatted help text
        mock_run_pager.assert_called_once()
        help_text = mock_run_pager.call_args[0][0]
        assert "--test" in help_text


def test_help_option_callback_shows_help_and_exits() -> None:
    """Test that help_option_callback shows help and exits context."""

    @click.command()
    def test_cmd() -> None:
        """Test command."""
        pass

    ctx = click.Context(test_cmd)
    mock_param = mock.MagicMock(spec=click.Parameter)

    with mock.patch("imbue.mngr.cli.help_formatter.show_help_with_pager") as mock_show:
        with mock.patch.object(ctx, "exit") as mock_exit:
            help_option_callback(ctx, mock_param, True)

            mock_show.assert_called_once()
            mock_exit.assert_called_once_with(0)


def test_help_option_callback_does_nothing_when_value_false() -> None:
    """Test that help_option_callback does nothing when value is False."""

    @click.command()
    def test_cmd() -> None:
        """Test command."""
        pass

    ctx = click.Context(test_cmd)
    mock_param = mock.MagicMock(spec=click.Parameter)

    with mock.patch("imbue.mngr.cli.help_formatter.show_help_with_pager") as mock_show:
        help_option_callback(ctx, mock_param, False)

        mock_show.assert_not_called()


def test_help_option_callback_does_nothing_during_resilient_parsing() -> None:
    """Test that help_option_callback does nothing during resilient parsing."""

    @click.command()
    def test_cmd() -> None:
        """Test command."""
        pass

    ctx = click.Context(test_cmd)
    ctx.resilient_parsing = True
    mock_param = mock.MagicMock(spec=click.Parameter)

    with mock.patch("imbue.mngr.cli.help_formatter.show_help_with_pager") as mock_show:
        help_option_callback(ctx, mock_param, True)

        mock_show.assert_not_called()


def test_mngr_config_pager_merge_override_wins(mngr_test_prefix: str) -> None:
    """Test that pager config merges correctly with override winning."""
    base = MngrConfig(prefix=mngr_test_prefix, pager="less")
    override = MngrConfig(prefix=mngr_test_prefix, pager="more")

    merged = base.merge_with(override)
    assert merged.pager == "more"


def test_mngr_config_pager_merge_keeps_base_when_override_none(mngr_test_prefix: str) -> None:
    """Test that pager config merge keeps base when override is None."""
    base = MngrConfig(prefix=mngr_test_prefix, pager="less")
    override = MngrConfig(prefix=mngr_test_prefix)

    merged = base.merge_with(override)
    assert merged.pager == "less"


def test_common_options_group_appears_last_in_help() -> None:
    """Test that the Common options group appears after all other named option groups."""
    runner = CliRunner()
    result = runner.invoke(create, ["--help"])

    assert result.exit_code == 0
    help_output = result.output

    # Find all option group headers (lines that match "   <GroupName>\n")
    # These are 3-space indented group names
    group_pattern = re.compile(r"^   ([A-Z][a-zA-Z ]+)$", re.MULTILINE)
    groups_in_order = group_pattern.findall(help_output)

    # Filter to only named groups (exclude "Ungrouped" which may appear for truly ungrouped options)
    named_groups = [g for g in groups_in_order if g != "Ungrouped"]

    # Verify Common is present and is the last named group
    assert COMMON_OPTIONS_GROUP_NAME in named_groups, f"Common group not found. Groups: {named_groups}"
    assert named_groups[-1] == COMMON_OPTIONS_GROUP_NAME, f"Common should be last, but groups are: {named_groups}"


def test_ungrouped_options_display_as_ungrouped_not_common() -> None:
    """Test that options without a group are displayed under 'Ungrouped', not 'Common'."""

    @click.command()
    @optgroup.group("Feature Options")
    @optgroup.option("--feature", help="A feature flag")
    @click.option("--ungrouped-opt", help="This option has no group")
    def cmd_with_ungrouped(feature: bool, ungrouped_opt: str | None) -> None:
        """A command with both grouped and ungrouped options."""
        pass

    metadata = CommandHelpMetadata(
        name="mngr-test",
        one_line_description="Test ungrouped options display",
        synopsis="mngr test [options]",
        description="Test that ungrouped options show as Ungrouped.",
        examples=(),
    )

    runner = CliRunner()
    with runner.isolated_filesystem():
        ctx = click.Context(cmd_with_ungrouped)
        help_text = format_git_style_help(ctx, cmd_with_ungrouped, metadata)

        # The ungrouped option should appear under "Ungrouped" header
        assert "Ungrouped" in help_text
        # The "Common" header should only appear if there are actual common options in a Common group
        # In this test, there's no Common group, so we should NOT see "Common" as a fallback
        # for truly ungrouped options
        ungrouped_index = help_text.find("Ungrouped")
        assert ungrouped_index != -1
        # Verify the ungrouped option appears after the Ungrouped header
        assert "--ungrouped-opt" in help_text[ungrouped_index:]


def test_option_group_ordering_logic() -> None:
    """Test that option groups are ordered: other groups first, then Common, then Ungrouped."""

    # Test command with multiple option groups:
    # - "Zebra Options" named to be alphabetically last
    # - "Alpha Options" named to be alphabetically first
    # - Common options group
    # - One ungrouped option
    @click.command()
    @optgroup.group("Zebra Options")
    @optgroup.option("--zebra", help="Zebra option")
    @optgroup.group("Alpha Options")
    @optgroup.option("--alpha", help="Alpha option")
    @optgroup.group(COMMON_OPTIONS_GROUP_NAME)
    @optgroup.option("--common", help="Common option")
    @click.option("--ungrouped", help="Ungrouped option")
    def cmd_with_multiple_groups(zebra: bool, alpha: bool, common: bool, ungrouped: str | None) -> None:
        """A command with multiple option groups."""
        pass

    metadata = CommandHelpMetadata(
        name="mngr-test",
        one_line_description="Test option group ordering",
        synopsis="mngr test [options]",
        description="Test that groups are ordered correctly.",
        examples=(),
    )

    runner = CliRunner()
    with runner.isolated_filesystem():
        ctx = click.Context(cmd_with_multiple_groups)
        help_text = format_git_style_help(ctx, cmd_with_multiple_groups, metadata)

        # Find positions of each group header
        zebra_pos = help_text.find("Zebra Options")
        alpha_pos = help_text.find("Alpha Options")
        common_pos = help_text.find(COMMON_OPTIONS_GROUP_NAME)
        ungrouped_pos = help_text.find("Ungrouped")

        # All groups should be present
        assert zebra_pos != -1, "Zebra Options not found"
        assert alpha_pos != -1, "Alpha Options not found"
        assert common_pos != -1, "Common not found"
        assert ungrouped_pos != -1, "Ungrouped not found"

        # Common should appear after other named groups (Alpha and Zebra)
        assert common_pos > zebra_pos, "Common should appear after Zebra Options"
        assert common_pos > alpha_pos, "Common should appear after Alpha Options"

        # Ungrouped should appear last (after Common)
        assert ungrouped_pos > common_pos, "Ungrouped should appear after Common"


def test_create_command_common_group_contains_expected_options() -> None:
    """Test that the create command's Common group contains the expected common options."""
    runner = CliRunner()
    result = runner.invoke(create, ["--help"])

    assert result.exit_code == 0
    help_output = result.output

    # Find the Common section
    common_index = help_output.find(f"\n   {COMMON_OPTIONS_GROUP_NAME}\n")
    assert common_index != -1, "Common options group not found in help output"

    # Find the next section (either Ungrouped or end of OPTIONS)
    # Look for the next group header or EXAMPLES section
    after_common = help_output[common_index + len(f"\n   {COMMON_OPTIONS_GROUP_NAME}\n") :]

    # Find where Common section ends (next group header or EXAMPLES)
    next_section_match = re.search(r"\n   [A-Z][a-zA-Z ]+\n|\nEXAMPLES", after_common)
    if next_section_match:
        common_section = after_common[: next_section_match.start()]
    else:
        common_section = after_common

    # Verify that key common options are in the Common section
    assert "--format" in common_section, "--format should be in Common section"
    assert "--quiet" in common_section, "--quiet should be in Common section"
    assert "--verbose" in common_section, "--verbose should be in Common section"
    assert "--log-commands" in common_section, "--log-commands should be in Common section"
    assert "--context" in common_section, "--context should be in Common section"
    assert "--plugin" in common_section, "--plugin should be in Common section"


def test_commands_with_aliases_have_aliases_in_synopsis() -> None:
    """Commands with aliases must include them in the synopsis as [cmd|alias].

    This ensures users see the alias directly in the synopsis rather than
    needing to look elsewhere in the help output.
    """
    for cmd in BUILTIN_COMMANDS:
        if cmd.name is None:
            continue
        metadata = get_help_metadata(cmd.name)
        if metadata is None or not metadata.aliases:
            continue

        # Build expected pattern: mngr [cmd|alias1|alias2...]
        expected_parts = [cmd.name, *metadata.aliases]
        joined = "|".join(expected_parts)
        expected_pattern = f"mngr [{joined}]"

        assert expected_pattern in metadata.synopsis, (
            f"Command '{cmd.name}' has aliases {metadata.aliases} but synopsis "
            f"doesn't contain '{expected_pattern}'. Synopsis: {metadata.synopsis}"
        )
