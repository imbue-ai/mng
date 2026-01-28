# mngr pull

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

**Options:**

### Source Selection

| Name | Type | Description | Default |
| ---- | ---- | ----------- | ------- |
| `--source` | text | Source specification: AGENT, AGENT:PATH, or PATH | None |
| `--source-agent` | text | Source agent name or ID | None |
| `--source-host` | text | Source host name or ID | None |
| `--source-path` | text | Path within the agent's work directory | None |

### Destination

| Name | Type | Description | Default |
| ---- | ---- | ----------- | ------- |
| `--destination` | path | Local destination directory [default: .] | None |

### Sync Options

| Name | Type | Description | Default |
| ---- | ---- | ----------- | ------- |
| `--dry-run` | boolean | Show what would be transferred without actually transferring | `False` |
| `--stop` | boolean | Stop the agent after pulling (for state consistency) | `False` |
| `--delete`, `--no-delete` | boolean | Delete files in destination that don't exist in source | `False` |
| `--sync-mode` | choice (`files` &#x7C; `state` &#x7C; `full`) | What to sync: files (working directory only), state (agent state), or full (everything) | `files` |
| `--exclude` | text | Patterns to exclude from sync [repeatable] | None |

### Common

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

### Other Options

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
