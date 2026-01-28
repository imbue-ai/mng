# mngr connect

**Synopsis:**

```text
mngr connect [OPTIONS] [AGENT]
```


Connect to an existing agent via the terminal.

Attaches to the agent's tmux session, roughly equivalent to SSH'ing into
the agent's machine and attaching to the tmux session. Use `mngr open` to
open an agent's URLs in a web browser instead.

If no agent is specified, shows an interactive selector to choose from
available agents.

Alias: conn

**Usage:**

```text
mngr connect [OPTIONS] [AGENT]
```

**Options:**

### General

| Name | Type | Description | Default |
| ---- | ---- | ----------- | ------- |
| `--agent` | text | The agent to connect to (by name or ID) | None |
| `--start`, `--no-start` | boolean | Automatically start the agent if stopped | `True` |

### Options

| Name | Type | Description | Default |
| ---- | ---- | ----------- | ------- |
| `--reconnect`, `--no-reconnect` | boolean | Automatically reconnect if dropped | `True` |
| `--message` | text | Initial message to send after connecting | None |
| `--message-file` | path | File containing initial message to send | None |
| `--message-delay` | float | Seconds to wait before sending initial message | `1.0` |
| `--retry` | integer | Number of connection retries | `3` |
| `--retry-delay` | text | Delay between retries | `5s` |
| `--attach-command` | text | Command to run instead of attaching to main session | None |

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

- [mngr create](./create.md) - Create and connect to a new agent
- [mngr list](./list.md) - List available agents

## Examples

**Connect to an agent by name**

```bash
$ mngr connect my-agent
```

**Connect without auto-starting if stopped**

```bash
$ mngr connect my-agent --no-start
```

**Show interactive agent selector**

```bash
$ mngr connect
```
