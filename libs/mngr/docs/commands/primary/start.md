<!-- This file is auto-generated. Do not edit directly. -->
<!-- To modify, edit the command's help metadata and run: uv run python scripts/make_cli_docs.py -->

# mngr start

**Synopsis:**

```text
mngr start [AGENTS...] [--agent <AGENT>] [--all] [--host <HOST>] [--connect] [--dry-run] [--snapshot <SNAPSHOT>]
```


Start stopped agent(s).

For remote hosts, this restores from the most recent snapshot and starts
the container/instance. For local agents, this starts the agent's tmux
session.

Examples:

  mngr start my-agent

  mngr start agent1 agent2

  mngr start --agent my-agent --connect

  mngr start --all

**Usage:**

```text
mngr start [OPTIONS] [AGENTS]...
```

## Arguments

- `AGENTS`: The agents (optional)

**Options:**

## Target Selection

| Name | Type | Description | Default |
| ---- | ---- | ----------- | ------- |
| `--agent` | text | Agent name or ID to start (can be specified multiple times) | None |
| `-a`, `--all`, `--all-agents` | boolean | Start all stopped agents | `False` |
| `--host` | text | Host(s) to start all stopped agents on [repeatable] [future] | None |
| `--include` | text | Filter agents and hosts to start by CEL expression (repeatable) [future] | None |
| `--exclude` | text | Exclude agents and hosts matching CEL expression (repeatable) [future] | None |
| `--stdin` | boolean | Read agent and host names/IDs from stdin, one per line [future] | `False` |

## Behavior

| Name | Type | Description | Default |
| ---- | ---- | ----------- | ------- |
| `--dry-run` | boolean | Show what would be started without actually starting | `False` |
| `--connect`, `--no-connect` | boolean | Connect to the agent after starting (only valid for single agent) | `False` |

## Snapshot

| Name | Type | Description | Default |
| ---- | ---- | ----------- | ------- |
| `--snapshot` | text | Start from a specific snapshot instead of the most recent [future] | None |
| `--latest`, `--no-latest` | boolean | Start from the most recent snapshot or state [default] [future] | `True` |

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

- [mngr stop](./stop.md) - Stop running agents
- [mngr connect](./connect.md) - Connect to an agent
- [mngr list](./list.md) - List existing agents

## Examples

**Start an agent by name**

```bash
$ mngr start my-agent
```

**Start multiple agents**

```bash
$ mngr start agent1 agent2
```

**Start and connect**

```bash
$ mngr start my-agent --connect
```

**Start all stopped agents**

```bash
$ mngr start --all
```

**Preview what would be started**

```bash
$ mngr start --all --dry-run
```
