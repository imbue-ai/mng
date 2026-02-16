<!-- This file is auto-generated. Do not edit directly. -->
<!-- To modify, edit the command's help metadata and run: uv run python scripts/make_cli_docs.py -->

# mngr logs

**Synopsis:**

```text
mngr logs TARGET [LOG_FILE] [--follow] [--tail N] [--head N]
```


View log files from an agent or host.

TARGET is an agent name/ID or host name/ID. If a log file name is not
specified, lists all available log files.

Examples:
  mngr logs my-agent
  mngr logs my-agent output.log
  mngr logs my-agent output.log --tail 50
  mngr logs my-agent output.log --follow

**Usage:**

```text
mngr logs [OPTIONS] TARGET [LOG_FILENAME]
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

## Connection

| Name | Type | Description | Default |
| ---- | ---- | ----------- | ------- |
| `--allow-unknown-host`, `--no-allow-unknown-host` | boolean | Allow following logs on hosts without a known_hosts file (disables SSH host key verification) | `False` |

## Common

| Name | Type | Description | Default |
| ---- | ---- | ----------- | ------- |
| `--format` | text | Output format (human, json, jsonl); some commands also accept a template string | `human` |
| `--json` | boolean | Alias for --format json | `False` |
| `--jsonl` | boolean | Alias for --format jsonl | `False` |
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

- [mngr list](../primary/list.md) - List available agents
- [mngr exec](../primary/exec.md) - Execute commands on an agent's host

## Examples

**List available log files for an agent**

```bash
$ mngr logs my-agent
```

**View a specific log file**

```bash
$ mngr logs my-agent output.log
```

**View the last 50 lines**

```bash
$ mngr logs my-agent output.log --tail 50
```

**Follow a log file**

```bash
$ mngr logs my-agent output.log --follow
```
