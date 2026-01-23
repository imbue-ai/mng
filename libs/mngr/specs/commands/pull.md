# Pull Command Spec

Implementation details for the `mngr pull` command.

## Overview

The `pull` command syncs git state and/or files from a source (agent or host) to a target (agent, host, or local directory).

This spec documents the minimal initial implementation:
- Files-only mode using rsync
- All CLI options defined (but unsupported options raise NotImplementedError)
- Interactive agent selection when `--interactive` and no agent specified

## Initial Implementation Scope

The initial implementation will support:
- `--files-only` mode (default for minimal implementation)
- Single source agent to local directory
- Basic rsync options (`--rsync-arg`, `--rsync-args`)
- Dry-run using rsync's built-in `--dry-run` flag
- Interactive agent selection (using urwid library)
- `--stop` flag to stop agent after pulling

All other options will be defined in the CLI but raise `NotImplementedError` when used.

## Command Structure

### CLI Options Class

```python
class PullCliOptions(CommonCliOptions):
    """Options for the pull command.

    Inherits common options from CommonCliOptions (output_format, quiet, verbose, etc.)
    """

    # Positional arguments
    agent: str | None  # Optional agent name/id
    to_agent: str | None  # Optional second agent for agent-to-agent sync

    # Source/target specification
    source: str | None
    source_agent: str | None
    source_host: str | None
    source_path: str | None
    target: str | None
    target_agent: str | None
    target_host: str | None
    target_path: str | None

    # Input options
    stdin: bool

    # Rsync options
    rsync_arg: tuple[str, ...]
    rsync_args: str | None
    dry_run: bool

    # Sync mode
    both: bool
    git_only: bool
    files_only: bool

    # File filtering
    include_gitignored: bool
    include: tuple[str, ...]
    exclude: tuple[str, ...]
    include_file: str | None
    exclude_file: str | None

    # Git options
    branch: tuple[str, ...]
    target_branch: str | None
    all_branches: bool
    tags: bool
    force_git: bool
    warn_on_uncommitted_source: bool
    error_on_uncommitted_source: bool
    merge: bool
    rebase: bool

    # Stop option
    stop: bool

    # Interactive mode (inherited from CommonCliOptions)
    interactive: bool
```

## Implementation Steps

### 1. CLI Definition

Define all click options and arguments according to the documentation in `docs/commands/primary/pull.md`:

```python
@click.command(name="pull")
@click.argument("agent", required=False)
@click.argument("to_agent", required=False)
@optgroup.group("Source/Target Specification")
@optgroup.option("--source", help="...")
@optgroup.option("--source-agent", help="...")
@optgroup.option("--source-host", help="...")
@optgroup.option("--source-path", help="...")
@optgroup.option("--target", help="...")
@optgroup.option("--target-agent", help="...")
@optgroup.option("--target-host", help="...")
@optgroup.option("--target-path", help="...")
@optgroup.group("Input Options")
@optgroup.option("--stdin", is_flag=True, help="...")
@optgroup.group("Rsync Options")
@optgroup.option("--rsync-arg", multiple=True, help="...")
@optgroup.option("--rsync-args", help="...")
@optgroup.option("--dry-run", is_flag=True, help="...")
@optgroup.group("Sync Mode")
@optgroup.option("--both", is_flag=True, help="...")
@optgroup.option("--git-only", is_flag=True, help="...")
@optgroup.option("--files-only", is_flag=True, help="...")
@optgroup.group("File Filtering")
@optgroup.option("--include-gitignored", is_flag=True, help="...")
@optgroup.option("--include", multiple=True, help="...")
@optgroup.option("--exclude", multiple=True, help="...")
@optgroup.option("--include-file", help="...")
@optgroup.option("--exclude-file", help="...")
@optgroup.group("Git Options")
@optgroup.option("--branch", multiple=True, help="...")
@optgroup.option("--target-branch", help="...")
@optgroup.option("--all", "--all-branches", "all_branches", is_flag=True, help="...")
@optgroup.option("--tags", is_flag=True, help="...")
@optgroup.option("--force-git", is_flag=True, help="...")
@optgroup.option("--warn-on-uncommitted-source/--error-on-uncommitted-source", help="...")
@optgroup.option("--merge/--rebase", help="...")
@optgroup.group("Stop Options")
@optgroup.option("--stop/--no-stop", default=False, help="Stop the agent after pulling")
@add_common_options
@click.pass_context
def pull(ctx: click.Context, **kwargs) -> None:
    """Pull data from an agent or host.

    By default, syncs from an agent's work_dir to the local current directory.
    """
    # Setup command context
    config, output_opts, opts = setup_command_context(
        ctx=ctx,
        command_name="pull",
        command_class=PullCliOptions,
    )

    # Implementation continues...
```

### 2. Option Validation

Validate conflicting options:
- Only one of `--both`, `--git-only`, `--files-only` can be set
- `--merge` and `--rebase` are mutually exclusive
- Source and target specifications must be valid
- Cannot use git options with `--files-only` mode

For the initial implementation:
- Default to `--files-only` mode
- Raise `NotImplementedError` for any git-related options
- Raise `NotImplementedError` for advanced source/target specifications (only support basic agent-to-local)

### 3. Agent Selection

If `--interactive` is enabled (default) and no agent is specified:
- Use urwid library to show an interactive list of available agents
- Allow user to select an agent from the list
- Handle cancellation gracefully

If not interactive or agent is specified:
- Resolve agent by name or ID
- Raise error if agent not found

### 4. Files-Only Sync Implementation

The minimal implementation performs a files-only sync using rsync:

```python
def _perform_files_only_sync(
    source_path: Path,
    target_path: Path,
    rsync_args: list[str],
    dry_run: bool,
) -> None:
    """Perform files-only sync using rsync.

    Args:
        source_path: Source directory path
        target_path: Target directory path
        rsync_args: Additional rsync arguments
        dry_run: Whether to perform a dry run
    """
    # Build rsync command
    cmd = ["rsync", "-avz"]

    if dry_run:
        cmd.append("--dry-run")

    # Add user-specified rsync args
    cmd.extend(rsync_args)

    # Add source and target
    cmd.append(f"{source_path}/")
    cmd.append(f"{target_path}/")

    # Execute rsync
    # ... use appropriate subprocess/ssh execution
```

### 5. Stop Agent After Pull

If `--stop` flag is set:
- After successful pull, stop the source agent
- Use the existing stop command implementation/API
- Only stop if pull completed successfully

### 6. Error Handling

Follow the error handling patterns from `specs/error_handling.md`:
- Use appropriate exception types (AgentError, HostError, etc.)
- Provide clear error messages
- Handle connection errors gracefully
- Follow multi-target behavior patterns if applicable

### 7. Output

Follow output patterns from other commands:
- Support `--format` option (human, json, jsonl)
- Log progress to stderr
- Output results to stdout
- In dry-run mode, show what would be synced

## Future Work

The following features are not in the initial implementation but should be added later:

1. Git sync modes (`--git-only`, `--both`)
2. Agent-to-agent sync
3. Host-to-host sync
4. Advanced source/target specifications (unified syntax)
5. File filtering (`--include`, `--exclude`, etc.)
6. Git options (branches, tags, merge/rebase, etc.)
7. Multi-target support with `--stdin`
8. Uncommitted changes handling

## Implementation Notes

### Interactive Agent Selection

Use urwid library for TUI:
- Show list of available agents with status
- Display agent name, host, state, and work_dir
- Allow arrow keys and enter to select
- Support ESC or q to cancel
- Only show when `--interactive` is true (default)

### Rsync Execution

For remote agents:
- Use SSH to access remote host
- Execute rsync over SSH connection
- Handle SSH key authentication
- Use host's SSH configuration from agent state

For local agents:
- Direct rsync between directories
- No SSH required

### Dry-Run Mode

Leverage rsync's built-in `--dry-run`:
- Pass `--dry-run` flag directly to rsync
- Capture and display rsync output
- Show what would be transferred without actually transferring

### Stop After Pull

Implementation:
- Only stop if pull succeeds
- Log that agent is being stopped
- Use agent.stop() or similar API
- Handle errors during stop gracefully (warn but don't fail the pull)

## Testing

The initial implementation should include:
- Unit tests for option parsing and validation
- Unit tests for rsync command generation
- Integration tests for files-only sync
- Tests for interactive selection (mocked TUI)
- Tests for stop-after-pull behavior
- Tests that unsupported options raise NotImplementedError

## Related Specs

- `specs/git_interactions.md` - Git sync behavior (for future implementation)
- `specs/error_handling.md` - Error handling patterns
- `specs/agent.md` - Agent state and data
- `specs/host.md` - Host state and data
- `specs/ssh_access.md` - SSH connection handling

## TODOs

Features from this spec not yet implemented:

- Git sync modes (`--git-only`, `--both`)
- Agent-to-agent sync (`to_agent` positional argument)
- Remote agent support (currently only local agents work)
- Host specifications (`--source-host`, `--target-host`, `--target-agent`)
- Custom rsync arguments (`--rsync-arg`, `--rsync-args`)
- File filtering (`--include`, `--include-gitignored`, `--include-file`, `--exclude-file`)
- Git options (`--branch`, `--target-branch`, `--all-branches`, `--tags`, `--force-git`, `--merge`, `--rebase`)
- Multi-target support (`--stdin`)
- Uncommitted changes handling (`--warn-on-uncommitted-source`, `--error-on-uncommitted-source`)
