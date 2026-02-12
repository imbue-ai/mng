<!-- This file is auto-generated. Do not edit directly. -->
<!-- To modify, edit the command's help metadata and run: uv run python scripts/make_cli_docs.py -->

# mngr open

**Synopsis:**

```text
mngr open [OPTIONS] [AGENT] [URL_TYPE]
```


Open an agent's URL in a web browser.

Opens the URL associated with an agent. Agents can have a variety of
different URLs associated with them. If the URL type is unspecified (and
there is more than one URL), a TUI lets you pick from the available
URLs [future].

Use `mngr connect` to attach to an agent via the terminal instead.

If no agent is specified, shows an interactive selector to choose from
available agents.

**Usage:**

```text
mngr open [OPTIONS] [AGENT] [URL_TYPE]
```

## Arguments

- `AGENT`: The agent to open (by name or ID). If not specified, opens the most recently created agent
- `URL_TYPE`: The type of URL to open (e.g., `chat`, `terminal`, `diff`) [future]

**Options:**

## General

| Name | Type | Description | Default |
| ---- | ---- | ----------- | ------- |
| `--agent` | text | The agent to open (by name or ID) | None |
| `-t`, `--type` | text | The type of URL to open (e.g., chat, terminal, diff) [future] | None |
| `--start`, `--no-start` | boolean | Automatically start the agent if stopped | `True` |

## Options

| Name | Type | Description | Default |
| ---- | ---- | ----------- | ------- |
| `--wait`, `--no-wait` | boolean | Keep running after opening (press Ctrl+C to exit) | `False` |
| `--active` | boolean | Continually update active timestamp while connected (prevents idle shutdown, only with --wait) | `False` |

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

- [mngr connect](./connect.md) - Connect to an agent via the terminal
- [mngr list](./list.md) - List available agents

## Examples

**Open an agent's URL by name**

```bash
$ mngr open my-agent
```

**Open without auto-starting if stopped**

```bash
$ mngr open my-agent --no-start
```

**Open and keep running**

```bash
$ mngr open my-agent --wait
```

**Open and keep agent active**

```bash
$ mngr open my-agent --wait --active
```
