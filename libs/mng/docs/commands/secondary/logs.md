<!-- This file is auto-generated. Do not edit directly. -->
<!-- To modify, edit the command's help metadata and run: uv run python scripts/make_cli_docs.py -->

# mng logs

**Synopsis:**

```text
mng logs TARGET [LOG_FILE] [--follow] [--tail N] [--head N]
```


View log files from an agent or host. [experimental]

TARGET is an agent name/ID or host name/ID. If a log file name is not
specified, lists all available log files.

When listing files, supports custom format templates via --format.
Available fields: name, size.

Examples:
  mng logs my-agent
  mng logs my-agent output.log
  mng logs my-agent output.log --tail 50
  mng logs my-agent output.log --follow
  mng logs my-agent --format '{name}\t{size}'

**Usage:**

```text
mng logs [OPTIONS] TARGET [LOG_FILENAME]
```

## Arguments

- `TARGET`: Agent or host name/ID whose logs to view
- `LOG_FILE`: Name of the log file to view (optional; lists files if omitted)

**Options:**

## Display

| Name | Type | Description | Default |
| ---- | ---- | ----------- | ------- |
| `--follow`, `--no-follow` | boolean | Continue running and print new messages as they appear | `False` |
| `--tail` | integer range | Print the last N lines of the log | None |
| `--head` | integer range | Print the first N lines of the log | None |

## Common

| Name | Type | Description | Default |
| ---- | ---- | ----------- | ------- |
| `--format` | text | Output format (human, json, jsonl, FORMAT): Output format for results. When a template is provided [experimental], fields use standard python templating like 'name: {agent.name}' See below for available fields. | `human` |
| `--json` | boolean | Alias for --format json | `False` |
| `--jsonl` | boolean | Alias for --format jsonl | `False` |
| `-q`, `--quiet` | boolean | Suppress all console output | `False` |
| `-v`, `--verbose` | integer range | Increase verbosity (default: BUILD); -v for DEBUG, -vv for TRACE | `0` |
| `--log-file` | path | Path to log file (overrides default ~/.mng/logs/<timestamp>-<pid>.json) | None |
| `--log-commands`, `--no-log-commands` | boolean | Log commands that were executed | None |
| `--log-command-output`, `--no-log-command-output` | boolean | Log stdout/stderr from commands | None |
| `--log-env-vars`, `--no-log-env-vars` | boolean | Log environment variables (security risk) | None |
| `--context` | path | Project context directory (for build context and loading project-specific config) [default: local .git root] | None |
| `--plugin`, `--enable-plugin` | text | Enable a plugin [repeatable] | None |
| `--disable-plugin` | text | Disable a plugin [repeatable] | None |
| `-h`, `--help` | boolean | Show this message and exit. | `False` |

## See Also

- [mng list](../primary/list.md) - List available agents
- [mng exec](../primary/exec.md) - Execute commands on an agent's host

## Examples

**List available log files for an agent**

```bash
$ mng logs my-agent
```

**View a specific log file**

```bash
$ mng logs my-agent output.log
```

**View the last 50 lines**

```bash
$ mng logs my-agent output.log --tail 50
```

**Follow a log file**

```bash
$ mng logs my-agent output.log --follow
```
