#!/usr/bin/env python3
"""Generate markdown documentation for mngr CLI commands.

Usage:
    uv run python scripts/make_cli_docs.py

This script generates markdown documentation for all CLI commands
and writes them to libs/mngr/docs/commands/. It preserves option
groups defined via click_option_group in the generated markdown.
"""

from pathlib import Path

import click
from click_option_group import GroupedOption
from mkdocs_click._docs import make_command_docs

from imbue.mngr.cli.common_opts import COMMON_OPTIONS_GROUP_NAME
from imbue.mngr.cli.help_formatter import get_help_metadata
from imbue.mngr.main import BUILTIN_COMMANDS
from imbue.mngr.main import cli

# Commands categorized by their documentation location
PRIMARY_COMMANDS = {"connect", "create", "destroy", "list", "pull"}
SECONDARY_COMMANDS = {"config", "gc", "message"}


def fix_sentinel_defaults(content: str) -> str:
    """Replace Click's internal Sentinel.UNSET with user-friendly text.

    Click uses Sentinel.UNSET internally to distinguish between "no default"
    and "default is None". We replace it with "None" for cleaner docs.
    """
    return content.replace("`Sentinel.UNSET`", "None")


def _escape_markdown_table(text: str) -> str:
    """Escape characters that would break markdown table formatting."""
    return text.replace("|", "&#x7C;")


def _format_option_names(option: click.Option) -> str:
    """Format option names for display (e.g., '-n', '--name')."""
    names = []
    for opt in option.opts:
        names.append(f"`{opt}`")
    for opt in option.secondary_opts:
        names.append(f"`{opt}`")
    return ", ".join(names)


def _format_option_type(option: click.Option) -> str:
    """Format option type for display."""
    if option.is_flag:
        return "boolean"
    if option.type is not None:
        type_name = option.type.name.lower()
        if hasattr(option.type, "choices"):
            choices = " &#x7C; ".join(f"`{c}`" for c in option.type.choices)
            return f"choice ({choices})"
        return type_name
    return "text"


def _format_option_default(option: click.Option) -> str:
    """Format option default value for display."""
    if option.default is None:
        return "None"
    if isinstance(option.default, bool):
        return f"`{option.default}`"
    if isinstance(option.default, str):
        if option.default == "":
            return "``"
        return f"`{option.default}`"
    if isinstance(option.default, (int, float)):
        return f"`{option.default}`"
    return f"`{option.default}`"


def _collect_options_by_group(command: click.Command) -> dict[str | None, list[click.Option]]:
    """Collect command options organized by their option group."""
    options_by_group: dict[str | None, list[click.Option]] = {}

    for param in command.params:
        if not isinstance(param, click.Option):
            continue

        if isinstance(param, GroupedOption):
            group_name = param.group.name
        else:
            group_name = None

        if group_name not in options_by_group:
            options_by_group[group_name] = []
        options_by_group[group_name].append(param)

    return options_by_group


def _order_option_groups(options_by_group: dict[str | None, list[click.Option]]) -> list[str | None]:
    """Order option groups: named groups first, Common last, ungrouped at the end."""
    group_names = list(options_by_group.keys())
    ordered: list[str | None] = []

    # First: named groups (except Common)
    for name in group_names:
        if name is not None and name != COMMON_OPTIONS_GROUP_NAME:
            ordered.append(name)

    # Then: Common group
    if COMMON_OPTIONS_GROUP_NAME in group_names:
        ordered.append(COMMON_OPTIONS_GROUP_NAME)

    # Finally: ungrouped options (None)
    if None in group_names:
        ordered.append(None)

    return ordered


def _generate_options_table(options: list[click.Option]) -> str:
    """Generate a markdown table for a list of options."""
    lines = [
        "| Name | Type | Description | Default |",
        "| ---- | ---- | ----------- | ------- |",
    ]

    for option in options:
        if option.hidden:
            continue

        names = _format_option_names(option)
        opt_type = _format_option_type(option)
        description = _escape_markdown_table(option.help or "")
        default = _format_option_default(option)

        lines.append(f"| {names} | {opt_type} | {description} | {default} |")

    return "\n".join(lines)


def generate_grouped_options_markdown(command: click.Command) -> str:
    """Generate markdown for options organized by groups."""
    options_by_group = _collect_options_by_group(command)
    ordered_groups = _order_option_groups(options_by_group)

    lines: list[str] = []

    for group_name in ordered_groups:
        options = options_by_group[group_name]
        if not options:
            continue

        # Filter out hidden options
        visible_options = [o for o in options if not o.hidden]
        if not visible_options:
            continue

        # Add group heading
        if group_name is not None:
            lines.append(f"### {group_name}")
        else:
            lines.append("### Other Options")
        lines.append("")

        # Add options table
        lines.append(_generate_options_table(visible_options))
        lines.append("")

    return "\n".join(lines)


def format_examples(command_name: str) -> str:
    """Format examples section from CommandHelpMetadata if available."""
    metadata = get_help_metadata(command_name)
    if metadata is None or not metadata.examples:
        return ""

    lines = ["", "## Examples", ""]
    for description, command in metadata.examples:
        lines.append(f"**{description}**")
        lines.append("")
        lines.append("```bash")
        lines.append(f"$ {command}")
        lines.append("```")
        lines.append("")

    return "\n".join(lines)


def format_additional_sections(command_name: str) -> str:
    """Format additional documentation sections from CommandHelpMetadata.

    Note: "See Also" sections are handled separately by format_see_also_section,
    so they are excluded here.
    """
    metadata = get_help_metadata(command_name)
    if metadata is None:
        return ""

    sections = []

    # Add additional_sections if present (excluding "See Also" which is handled separately)
    if hasattr(metadata, "additional_sections") and metadata.additional_sections:
        for title, content in metadata.additional_sections:
            if title == "See Also":
                continue
            sections.append(f"\n## {title}\n")
            sections.append(content)
            sections.append("")

    return "\n".join(sections)


def get_command_category(command_name: str) -> str | None:
    """Get the category (primary/secondary) for a command."""
    if command_name in PRIMARY_COMMANDS:
        return "primary"
    elif command_name in SECONDARY_COMMANDS:
        return "secondary"
    return None


def get_relative_link(from_command: str, to_command: str) -> str:
    """Get the relative markdown link path from one command's doc to another.

    Examples:
        get_relative_link("connect", "create") -> "./create.md" (both in primary)
        get_relative_link("connect", "gc") -> "../secondary/gc.md" (primary to secondary)
        get_relative_link("gc", "destroy") -> "../primary/destroy.md" (secondary to primary)
    """
    from_category = get_command_category(from_command)
    to_category = get_command_category(to_command)

    if to_category is None:
        # Target command doesn't have docs, just return the command name
        return f"mngr {to_command}"

    if from_category == to_category:
        return f"./{to_command}.md"
    else:
        return f"../{to_category}/{to_command}.md"


def format_see_also_section(command_name: str) -> str:
    """Format the See Also section from CommandHelpMetadata with markdown links."""
    metadata = get_help_metadata(command_name)
    if metadata is None or not metadata.see_also:
        return ""

    lines = ["", "## See Also", ""]
    for ref_command, description in metadata.see_also:
        link = get_relative_link(command_name, ref_command)
        lines.append(f"- [mngr {ref_command}]({link}) - {description}")

    lines.append("")
    return "\n".join(lines)


def get_output_dir(command_name: str, base_dir: Path) -> Path | None:
    """Determine the output directory for a command based on its category."""
    if command_name in PRIMARY_COMMANDS:
        return base_dir / "primary"
    elif command_name in SECONDARY_COMMANDS:
        return base_dir / "secondary"
    else:
        # Commands not in either category don't get docs generated
        return None


def _extract_sections(lines: list[str]) -> tuple[str, int, str]:
    """Extract sections from mkdocs-click output.

    Returns:
        - header_content: Everything before **Options:**
        - options_start_idx: Index where options start
        - subcommands_content: Everything from the first subcommand (## heading) onwards
    """
    options_start_idx = None
    subcommands_start_idx = None

    for i, line in enumerate(lines):
        if options_start_idx is None and line.strip() == "**Options:**":
            options_start_idx = i
        # After finding **Options:**, look for subcommand sections (## headings)
        # that indicate subcommand documentation
        elif options_start_idx is not None and subcommands_start_idx is None:
            if line.startswith("## "):
                subcommands_start_idx = i
                break

    if options_start_idx is None:
        # No options section found, return everything as header
        return "\n".join(lines), len(lines), ""

    header_content = "\n".join(lines[:options_start_idx])

    if subcommands_start_idx is not None:
        subcommands_content = "\n".join(lines[subcommands_start_idx:])
    else:
        subcommands_content = ""

    return header_content, options_start_idx, subcommands_content


def generate_command_doc(command_name: str, base_dir: Path) -> None:
    """Generate markdown documentation for a single command."""
    output_dir = get_output_dir(command_name, base_dir)
    if output_dir is None:
        print(f"Skipping: {command_name} (not in PRIMARY_COMMANDS or SECONDARY_COMMANDS)")
        return

    # Get the command from the CLI group
    cmd = cli.commands.get(command_name)
    if cmd is None:
        print(f"Warning: Command '{command_name}' not found")
        return

    # Generate markdown using mkdocs-click for header/usage/description
    mkdocs_lines = list(
        make_command_docs(
            prog_name=f"mngr {command_name}",
            command=cmd,
            depth=0,
            style="table",
        )
    )

    # Extract header, options start, and subcommands content
    header_content, _, subcommands_content = _extract_sections(mkdocs_lines)

    # Build the final content
    content_parts = [header_content]

    # Add grouped options section
    content_parts.append("**Options:**")
    content_parts.append("")
    content_parts.append(generate_grouped_options_markdown(cmd))

    # Add subcommands documentation if present (from mkdocs-click)
    if subcommands_content:
        content_parts.append(subcommands_content)

    # Combine all parts
    content = "\n".join(content_parts)
    content = fix_sentinel_defaults(content)

    # Add additional sections from metadata
    content += format_additional_sections(command_name)
    content += format_see_also_section(command_name)
    content += format_examples(command_name)

    # Write to file
    output_dir.mkdir(parents=True, exist_ok=True)
    output_file = output_dir / f"{command_name}.md"
    output_file.write_text(content)
    print(f"Generated: {output_file}")


def main() -> None:
    # Base output directory
    base_dir = Path(__file__).parent.parent / "libs" / "mngr" / "docs" / "commands"

    # Generate docs for each built-in command
    for cmd in BUILTIN_COMMANDS:
        if cmd.name is not None:
            generate_command_doc(cmd.name, base_dir)


if __name__ == "__main__":
    main()
