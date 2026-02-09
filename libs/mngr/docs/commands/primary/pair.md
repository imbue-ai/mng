<!-- This file is auto-generated. Do not edit directly. -->
<!-- To modify, edit the command's help metadata and run: uv run python scripts/make_cli_docs.py -->

# mngr pair

Continuously sync files between an agent and local directory.

This command establishes a bidirectional file sync between an agent's working
directory and a local directory. Changes are watched and synced in real-time.

If git repositories exist on both sides, the command first synchronizes git
state (branches and commits) before starting the continuous file sync.

Press Ctrl+C to stop the sync.

During rapid concurrent edits, changes will be debounced to avoid partial
writes [future].

Examples:
  mngr pair my-agent
  mngr pair my-agent ./local-dir
  mngr pair --source-agent my-agent --target ./local-copy
  mngr pair my-agent --sync-direction=forward
  mngr pair my-agent --conflict=source
  mngr pair my-agent --source-host @local

**Usage:**

```text
mngr pair [OPTIONS] [SOURCE]
```

## Arguments

- `SOURCE`: The source (optional)

**Options:**

## Source Selection

| Name | Type | Description | Default |
| ---- | ---- | ----------- | ------- |
| `--source` | text | Source specification: AGENT, AGENT:PATH, or PATH | None |
| `--source-agent` | text | Source agent name or ID | None |
| `--source-host` | text | Source host name or ID | None |
| `--source-path` | text | Path within the agent's work directory | None |

## Target

| Name | Type | Description | Default |
| ---- | ---- | ----------- | ------- |
| `--target` | path | Local target directory [default: nearest git root or current directory] | None |
| `--target-path` | text | Target path (if different from --target) | None |

## Git Handling

| Name | Type | Description | Default |
| ---- | ---- | ----------- | ------- |
| `--require-git`, `--no-require-git` | boolean | Require that both source and target are git repositories [default: require git] | `True` |
| `--uncommitted-changes` | choice (`stash` &#x7C; `clobber` &#x7C; `merge` &#x7C; `fail`) | How to handle uncommitted changes during initial git sync. The initial sync aborts immediately if unresolved conflicts exist, regardless of this setting. | `fail` |

## Sync Behavior

| Name | Type | Description | Default |
| ---- | ---- | ----------- | ------- |
| `--sync-direction` | choice (`both` &#x7C; `forward` &#x7C; `reverse`) | Sync direction: both (bidirectional), forward (source->target), reverse (target->source) | `both` |
| `--conflict` | choice (`newer` &#x7C; `source` &#x7C; `target` &#x7C; `ask`) | Conflict resolution mode (only matters for bidirectional sync). 'newer' prefers the file with the more recent modification time (uses unison's -prefer newer). 'source' and 'target' always prefer that side. 'ask' prompts interactively [future]. | `newer` |

## File Filtering

| Name | Type | Description | Default |
| ---- | ---- | ----------- | ------- |
| `--include` | text | Include files matching glob pattern [repeatable] | None |
| `--exclude` | text | Exclude files matching glob pattern [repeatable] | None |

## Common

| Name | Type | Description | Default |
| ---- | ---- | ----------- | ------- |
| `--format` | choice (`human` &#x7C; `json` &#x7C; `jsonl`) | Output format for command results | `human` |
| `-q`, `--quiet` | boolean | Suppress all console output | `False` |
| `-v`, `--verbose` | integer range | Increase verbosity (default: BUILD); -v for DEBUG, -vv for TRACE | `0` |
| `--log-file` | path | Path to log file (overrides default ~/.mngr/logs/<timestamp>-<pid>.json) | None |
| `--log-commands`, `--no-log-commands` | boolean | Log commands that were executed | None |
| `--log-command-output`, `--no-log-command-output` | boolean | Log stdout/stderr from commands | None |
| `--log-env-vars`, `--no-log-env-vars` | boolean | Log environment variables (security risk) | None |
| `--context` | path | Project context directory (for build context and loading project-specific config) [default: local .git root] | None |
| `--plugin`, `--enable-plugin` | text | Enable a plugin [repeatable] | None |
| `--disable-plugin` | text | Disable a plugin [repeatable] | None |
