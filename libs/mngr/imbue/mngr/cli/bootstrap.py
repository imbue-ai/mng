import importlib.resources
import sys
from pathlib import Path
from typing import Any
from typing import Final
from typing import assert_never

import click
from click_option_group import optgroup
from loguru import logger

from imbue.imbue_common.pure import pure
from imbue.mngr import resources
from imbue.mngr.cli.claude_backend import SubprocessClaudeBackend
from imbue.mngr.cli.claude_backend import accumulate_chunks
from imbue.mngr.cli.common_opts import CommonCliOptions
from imbue.mngr.cli.common_opts import add_common_options
from imbue.mngr.cli.common_opts import setup_command_context
from imbue.mngr.cli.help_formatter import CommandHelpMetadata
from imbue.mngr.cli.help_formatter import add_pager_help_option
from imbue.mngr.cli.help_formatter import register_help_metadata
from imbue.mngr.cli.output_helpers import AbortError
from imbue.mngr.cli.output_helpers import emit_final_json
from imbue.mngr.cli.output_helpers import emit_info
from imbue.mngr.errors import MngrError
from imbue.mngr.primitives import OutputFormat

# Read-only tools for agentic project exploration
_BOOTSTRAP_ALLOWED_TOOLS: Final[tuple[str, ...]] = ("Read", "Glob", "Grep")

_USER_PROMPT: Final[str] = (
    "Generate a Dockerfile for the project in the current directory. "
    "Explore the project structure and dependencies first, then output "
    "ONLY the raw Dockerfile content."
)


def _get_default_dockerfile() -> str:
    """Read the default Dockerfile from mngr resources."""
    resource_files = importlib.resources.files(resources)
    dockerfile_resource = resource_files.joinpath("Dockerfile")
    return dockerfile_resource.read_text()


@pure
def _resolve_output_path(project_dir: Path, override: str | None) -> Path:
    if override is not None:
        return Path(override)
    return project_dir / ".mngr" / "Dockerfile"


@pure
def _build_system_prompt(default_dockerfile: str) -> str:
    """Build the system prompt for Dockerfile generation."""
    return f"""You are a Dockerfile generator for the mngr tool.

You have access to Read, Glob, and Grep tools. Use them to explore the project
in the current directory before generating the Dockerfile.

Start by exploring:
- Root directory listing to understand the project structure
- Dependency files (pyproject.toml, package.json, Cargo.toml, go.mod, etc.)
- Any existing Dockerfile or .dockerignore
- Build configuration files

Then generate a Dockerfile that:
1. Uses an appropriate base image for the project's language/framework
2. Includes ALL of the following mngr-required system packages (mandatory):
   openssh-server, tmux, git, git-lfs, ripgrep, fd-find, rsync, tini, curl, wget, jq, nano, bash, build-essential, unison
3. Installs GitHub CLI (gh) using the official Debian/Ubuntu package repository
4. Installs uv (Python package manager) using: curl -LsSf https://astral.sh/uv/install.sh | sh
5. Installs Claude Code using: curl -fsSL https://claude.ai/install.sh | bash
6. Detects and supports the project's language/framework (install appropriate runtimes, etc.)
7. Does NOT include COPY, WORKDIR, or CMD instructions for the project code (mngr handles this)

Here is the reference Dockerfile that mngr uses by default (for Python projects).
Use it as a guide for the required tool installation steps, but adapt the base
image and language-specific setup to match the actual project:

```dockerfile
{default_dockerfile}
```

IMPORTANT RULES:
- Return ONLY the raw Dockerfile content. No markdown fences, no explanation, no commentary.
- The Dockerfile must NOT contain COPY, WORKDIR, or CMD instructions (mngr adds these automatically).
- Always include ALL the mngr-required system packages and tools listed above.
- Use the exact GitHub CLI, uv, and Claude Code installation commands from the reference Dockerfile.
- Set PATH environment variables for uv and Claude Code."""


class BootstrapCliOptions(CommonCliOptions):
    """Options passed from the CLI to the bootstrap command."""

    output_path: str | None
    force: bool
    dry_run: bool
    project_dir: str | None


@click.command(name="bootstrap")
@optgroup.group("Bootstrap")
@optgroup.option(
    "--output",
    "output_path",
    type=click.Path(),
    default=None,
    help="Output path for the generated Dockerfile [default: .mngr/Dockerfile]",
)
@optgroup.option(
    "--force",
    is_flag=True,
    help="Overwrite existing Dockerfile",
)
@optgroup.option(
    "--dry-run",
    is_flag=True,
    help="Print the generated Dockerfile to stdout instead of writing it",
)
@optgroup.option(
    "--project-dir",
    type=click.Path(exists=True),
    default=None,
    help="Directory to analyze [default: current working directory]",
)
@add_common_options
@click.pass_context
def bootstrap(ctx: click.Context, **kwargs: Any) -> None:
    """Generate a Dockerfile for your project.

    Analyzes the current project directory and uses AI to generate an
    appropriate Dockerfile at .mngr/Dockerfile. This Dockerfile can then
    be used with mngr create --build-arg "--dockerfile .mngr/Dockerfile".
    """
    try:
        _bootstrap_impl(ctx, **kwargs)
    except AbortError as e:
        logger.error("Aborted: {}", e.message)
        ctx.exit(1)


def _bootstrap_impl(ctx: click.Context, **kwargs: Any) -> None:
    """Implementation of bootstrap command (extracted for exception handling)."""
    _mngr_ctx, output_opts, opts = setup_command_context(
        ctx=ctx,
        command_name="bootstrap",
        command_class=BootstrapCliOptions,
    )
    logger.debug("Started bootstrap command")

    project_dir = Path(opts.project_dir) if opts.project_dir else Path.cwd()
    output_path = _resolve_output_path(project_dir, opts.output_path)

    # Check if output file already exists
    if not opts.dry_run and output_path.exists() and not opts.force:
        raise MngrError(f"Dockerfile already exists at {output_path}. Use --force to overwrite.")

    # Build system prompt with the default Dockerfile as reference
    default_dockerfile = _get_default_dockerfile()
    system_prompt = _build_system_prompt(default_dockerfile)

    emit_info("Generating Dockerfile...", output_opts.output_format)

    # Query Claude with read-only tools so it can explore the project
    backend = SubprocessClaudeBackend(
        allowed_tools=_BOOTSTRAP_ALLOWED_TOOLS,
        working_directory=project_dir,
    )
    chunks = backend.query(prompt=_USER_PROMPT, system_prompt=system_prompt)
    dockerfile_content = accumulate_chunks(chunks).strip()

    if not dockerfile_content:
        raise MngrError("Claude returned an empty response; no Dockerfile was generated")

    # Strip any markdown fences that Claude might have included despite instructions
    dockerfile_content = _strip_markdown_fences(dockerfile_content)

    if opts.dry_run:
        _output_dry_run(
            dockerfile_content=dockerfile_content,
            output_format=output_opts.output_format,
        )
    else:
        _write_dockerfile(
            dockerfile_content=dockerfile_content,
            output_path=output_path,
            output_format=output_opts.output_format,
        )


@pure
def _strip_markdown_fences(content: str) -> str:
    """Strip markdown code fences if Claude included them despite instructions."""
    lines = content.strip().splitlines()
    if len(lines) >= 2 and lines[0].startswith("```") and lines[-1].strip() == "```":
        return "\n".join(lines[1:-1]).strip()
    return content


def _output_dry_run(
    dockerfile_content: str,
    output_format: OutputFormat,
) -> None:
    """Output the generated Dockerfile for dry-run mode."""
    match output_format:
        case OutputFormat.HUMAN:
            logger.info("Generated Dockerfile:\n")
            sys.stdout.write(dockerfile_content + "\n")
            sys.stdout.flush()
        case OutputFormat.JSON:
            emit_final_json({"dockerfile": dockerfile_content})
        case OutputFormat.JSONL:
            emit_final_json({"event": "dockerfile", "dockerfile": dockerfile_content})
        case _ as unreachable:
            assert_never(unreachable)


def _write_dockerfile(
    dockerfile_content: str,
    output_path: Path,
    output_format: OutputFormat,
) -> None:
    """Write the generated Dockerfile to disk."""
    # Ensure parent directory exists
    output_path.parent.mkdir(parents=True, exist_ok=True)

    output_path.write_text(dockerfile_content + "\n")

    match output_format:
        case OutputFormat.HUMAN:
            logger.info("Wrote Dockerfile to {}", output_path)
        case OutputFormat.JSON:
            emit_final_json(
                {
                    "dockerfile": dockerfile_content,
                    "output_path": str(output_path),
                }
            )
        case OutputFormat.JSONL:
            emit_final_json(
                {
                    "event": "written",
                    "dockerfile": dockerfile_content,
                    "output_path": str(output_path),
                }
            )
        case _ as unreachable:
            assert_never(unreachable)


# Register help metadata for git-style help formatting
_BOOTSTRAP_HELP_METADATA: Final[CommandHelpMetadata] = CommandHelpMetadata(
    name="mngr-bootstrap",
    one_line_description="Generate a Dockerfile for your project",
    synopsis="mngr bootstrap [--output PATH] [--force] [--dry-run] [--project-dir DIR]",
    description="""Analyze the current project directory and generate an appropriate
Dockerfile at .mngr/Dockerfile. The generated Dockerfile includes all
mngr-required system packages and tools, plus language/framework-specific
setup detected from the project.

Use the generated Dockerfile with:
    mngr create --in modal --build-arg "--dockerfile .mngr/Dockerfile"

The AI explores the project using read-only file access to understand
the language, framework, and dependencies before generating the Dockerfile.""",
    examples=(
        ("Generate a Dockerfile", "mngr bootstrap"),
        ("Preview without writing", "mngr bootstrap --dry-run"),
        ("Overwrite existing", "mngr bootstrap --force"),
        ("Specify project directory", "mngr bootstrap --project-dir /path/to/project"),
    ),
    see_also=(
        ("create", "Create an agent"),
        ("ask", "Chat with mngr for help"),
    ),
)

register_help_metadata("bootstrap", _BOOTSTRAP_HELP_METADATA)

# Add pager-enabled help option to the bootstrap command
add_pager_help_option(bootstrap)
