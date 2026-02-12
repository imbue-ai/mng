<!-- This file is auto-generated. Do not edit directly. -->
<!-- To modify, edit the command's help metadata and run: uv run python scripts/make_cli_docs.py -->

# mngr exec

**Synopsis:**

```text
mngr [exec|x] AGENT COMMAND [--user <USER>] [--cwd <DIR>] [--timeout <SECONDS>]
```


Execute a shell command on an agent's host.

Runs COMMAND on the host where AGENT is running, defaulting to the
agent's work_dir. The command's stdout is printed to stdout and stderr
to stderr.

Examples:

  mngr exec my-agent "echo hello"

  mngr exec my-agent "ls -la" --cwd /tmp

  mngr exec my-agent "whoami" --user root

**Usage:**

```text
mngr exec [OPTIONS] AGENT COMMAND
```

## Arguments

- `AGENT`: The agent
- `COMMAND`: The command arg

**Options:**

## Execution

| Name | Type | Description | Default |
| ---- | ---- | ----------- | ------- |
| `--user` | text | User to run the command as | None |
| `--cwd` | text | Working directory for the command (default: agent's work_dir) | None |
| `--timeout` | float | Timeout in seconds for the command | None |

## General

| Name | Type | Description | Default |
| ---- | ---- | ----------- | ------- |
| `--start`, `--no-start` | boolean | Automatically start the host/agent if stopped | `True` |

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

- [mngr connect](./connect.md) - Connect to an agent interactively
- [mngr message](../secondary/message.md) - Send a message to an agent
- [mngr list](./list.md) - List available agents

## Examples

**Run a command on an agent**

```bash
$ mngr exec my-agent "echo hello"
```

**Run with a custom working directory**

```bash
$ mngr exec my-agent "ls -la" --cwd /tmp
```

**Run as a different user**

```bash
$ mngr exec my-agent "whoami" --user root
```

**Run with a timeout**

```bash
$ mngr exec my-agent "sleep 100" --timeout 5
```
