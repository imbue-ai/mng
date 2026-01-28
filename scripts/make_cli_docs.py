#!/usr/bin/env python3
"""Generate markdown documentation for mngr CLI commands.

Usage:
    uv run python scripts/make_cli_docs.py

This script uses mkdocs-click to generate markdown documentation
for all CLI commands and writes them to libs/mngr/docs/commands/.
"""

from pathlib import Path

from mkdocs_click._docs import make_command_docs

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

    # Generate markdown using mkdocs-click
    lines = make_command_docs(
        prog_name=f"mngr {command_name}",
        command=cmd,
        depth=0,
        style="table",  # Use table style for options
    )

    # Combine mkdocs-click output with additional sections, see also, and examples
    content = "\n".join(lines)
    content = fix_sentinel_defaults(content)
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
