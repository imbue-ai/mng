#!/usr/bin/env python3
"""Generate markdown documentation for mngr CLI commands.

Usage:
    uv run python scripts/make_cli_docs.py

This script uses mkdocs-click to generate markdown documentation
for all CLI commands and writes them to docs/cli/.
"""

from pathlib import Path

from mkdocs_click._docs import make_command_docs

from imbue.mngr.cli.help_formatter import get_help_metadata
from imbue.mngr.main import BUILTIN_COMMANDS
from imbue.mngr.main import cli


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
    """Format additional documentation sections from CommandHelpMetadata."""
    metadata = get_help_metadata(command_name)
    if metadata is None:
        return ""

    sections = []

    # Add additional_sections if present
    if hasattr(metadata, "additional_sections") and metadata.additional_sections:
        for title, content in metadata.additional_sections:
            sections.append(f"\n## {title}\n")
            sections.append(content)
            sections.append("")

    return "\n".join(sections)


def generate_command_doc(command_name: str, output_dir: Path) -> None:
    """Generate markdown documentation for a single command."""
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

    # Combine mkdocs-click output with additional sections and examples
    content = "\n".join(lines)
    content = fix_sentinel_defaults(content)
    content += format_additional_sections(command_name)
    content += format_examples(command_name)

    # Write to file
    output_file = output_dir / f"{command_name}.md"
    output_file.write_text(content)
    print(f"Generated: {output_file}")


def main() -> None:
    # Determine output directory
    output_dir = Path(__file__).parent.parent / "docs" / "cli"
    output_dir.mkdir(parents=True, exist_ok=True)

    # Generate docs for each built-in command
    for cmd in BUILTIN_COMMANDS:
        if cmd.name is not None:
            generate_command_doc(cmd.name, output_dir)

    # Also generate the top-level CLI doc
    lines = make_command_docs(
        prog_name="mngr",
        command=cli,
        depth=0,
        style="table",
    )
    content = "\n".join(lines)
    content = fix_sentinel_defaults(content)
    output_file = output_dir / "index.md"
    output_file.write_text(content)
    print(f"Generated: {output_file}")


if __name__ == "__main__":
    main()
