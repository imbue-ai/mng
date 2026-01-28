<!-- This file is auto-generated. Do not edit directly. -->
<!-- To modify, edit the command's help metadata and run: uv run python scripts/make_cli_docs.py -->

# mngr pull

**Synopsis:**

```text
mngr pull [SOURCE] [DESTINATION] [--source-agent <AGENT>] [--dry-run] [--stop]
```


Pull files from an agent to local machine.

Syncs files from an agent's working directory to a local directory.
Default behavior uses rsync for efficient incremental file transfer.

If no source is specified, shows an interactive selector to choose an agent.

Examples:
  mngr pull my-agent
  mngr pull my-agent ./local-copy
  mngr pull my-agent:src ./local-src
  mngr pull --source-agent my-agent

**Usage:**

```text
mngr pull [OPTIONS] [SOURCE] [DESTINATION]
```

## Arguments

- `SOURCE`: The source (optional)
- `DESTINATION`: The destination (optional)

**Options:**

## Source Selection

| Name | Type | Description | Default |
| ---- | ---- | ----------- | ------- |
| `--source` | text | Source specification: AGENT, AGENT:PATH, or PATH | None |
| `--source-agent` | text | Source agent name or ID | None |
| `--source-host` | text | Source host name or ID | None |
| `--source-path` | text | Path within the agent's work directory | None |

## Destination

| Name | Type | Description | Default |
| ---- | ---- | ----------- | ------- |
| `--destination` | path | Local destination directory [default: .] | None |

## Sync Options

| Name | Type | Description | Default |
| ---- | ---- | ----------- | ------- |
| `--dry-run` | boolean | Show what would be transferred without actually transferring | `False` |
| `--stop` | boolean | Stop the agent after pulling (for state consistency) | `False` |
| `--delete`, `--no-delete` | boolean | Delete files in destination that don't exist in source | `False` |
| `--sync-mode` | choice (`files` &#x7C; `state` &#x7C; `full`) | What to sync: files (working directory only), state (agent state), or full (everything) | `files` |
| `--exclude` | text | Patterns to exclude from sync [repeatable] | None |

## Target (for agent-to-agent sync)

| Name | Type | Description | Default |
| ---- | ---- | ----------- | ------- |
| `--target` | text | Target specification: AGENT, AGENT.HOST, AGENT.HOST:PATH, or HOST:PATH [NOT YET IMPLEMENTED] | None |
| `--target-agent` | text | Target agent name or ID [NOT YET IMPLEMENTED] | None |
| `--target-host` | text | Target host name or ID [NOT YET IMPLEMENTED] | None |
| `--target-path` | text | Path within target to sync to [NOT YET IMPLEMENTED] | None |

## Multi-source

| Name | Type | Description | Default |
| ---- | ---- | ----------- | ------- |
| `--stdin` | boolean | Read source agents/hosts from stdin, one per line [NOT YET IMPLEMENTED] | `False` |

## File Filtering

| Name | Type | Description | Default |
| ---- | ---- | ----------- | ------- |
| `--include` | text | Include files matching glob pattern [repeatable] [NOT YET IMPLEMENTED] | None |
| `--include-gitignored` | boolean | Include files that match .gitignore patterns [NOT YET IMPLEMENTED] | `False` |
| `--include-file` | path | Read include patterns from file [NOT YET IMPLEMENTED] | None |
| `--exclude-file` | path | Read exclude patterns from file [NOT YET IMPLEMENTED] | None |

## Rsync Options

| Name | Type | Description | Default |
| ---- | ---- | ----------- | ------- |
| `--rsync-arg` | text | Additional argument to pass to rsync [repeatable] [NOT YET IMPLEMENTED] | None |
| `--rsync-args` | text | Additional arguments to pass to rsync (as a single string) [NOT YET IMPLEMENTED] | None |

## Git Sync Options

| Name | Type | Description | Default |
| ---- | ---- | ----------- | ------- |
| `--branch` | text | Pull a specific branch [repeatable] [NOT YET IMPLEMENTED] | None |
| `--all-branches` | boolean | Pull all remote branches [NOT YET IMPLEMENTED] | `False` |
| `--tags` | boolean | Include git tags in sync [NOT YET IMPLEMENTED] | `False` |
| `--force-git` | boolean | Force overwrite local git state (use with caution) [NOT YET IMPLEMENTED] | `False` |
| `--merge` | boolean | Merge remote changes with local changes [NOT YET IMPLEMENTED] | `False` |
| `--rebase` | boolean | Rebase local changes onto remote changes [NOT YET IMPLEMENTED] | `False` |
| `--uncommitted-source` | choice (`warn` &#x7C; `error`) | Warn or error if source has uncommitted changes [NOT YET IMPLEMENTED] | None |

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

## Other Options

| Name | Type | Description | Default |
| ---- | ---- | ----------- | ------- |
| `-h`, `--help` | boolean | Show this message and exit. | `False` |

## See Also

- [mngr create](./create.md) - Create a new agent
- [mngr list](./list.md) - List agents to find one to pull from
- [mngr connect](./connect.md) - Connect to an agent interactively

## Examples

**Pull from agent to current directory**

```bash
$ mngr pull my-agent
```

**Pull to specific local directory**

```bash
$ mngr pull my-agent ./local-copy
```

**Pull specific subdirectory**

```bash
$ mngr pull my-agent:src ./local-src
```

**Preview what would be transferred**

```bash
$ mngr pull my-agent --dry-run
```
