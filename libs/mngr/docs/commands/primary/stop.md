<!-- This file is auto-generated. Do not edit directly. -->
<!-- To modify, edit the command's help metadata and run: uv run python scripts/make_cli_docs.py -->

# mngr stop

**Synopsis:**

```text
mngr [stop|s] [AGENTS...] [--agent <AGENT>] [--all] [--session <SESSION>] [--dry-run]
```


Stop running agent(s).

For remote hosts, this stops the agent's tmux session. The host remains
running (use idle detection or explicit host stop for host shutdown).

For local agents, this stops the agent's tmux session.

Alias: s

Examples:

  mngr stop my-agent

  mngr stop agent1 agent2

  mngr stop --agent my-agent

  mngr stop --all

**Usage:**

```text
mngr stop [OPTIONS] [AGENTS]...
```

## Arguments

- `AGENTS`: The agents (optional)

**Options:**

## Target Selection

| Name | Type | Description | Default |
| ---- | ---- | ----------- | ------- |
| `--agent` | text | Agent name or ID to stop (can be specified multiple times) | None |
| `-a`, `--all`, `--all-agents` | boolean | Stop all running agents | `False` |
| `--session` | text | Tmux session name to stop (can be specified multiple times). The agent name is extracted by stripping the configured prefix from the session name. | None |

## Behavior

| Name | Type | Description | Default |
| ---- | ---- | ----------- | ------- |
| `--dry-run` | boolean | Show what would be stopped without actually stopping | `False` |

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

- [mngr start](./start.md) - Start stopped agents
- [mngr connect](./connect.md) - Connect to an agent
- [mngr list](./list.md) - List existing agents

## Examples

**Stop an agent by name**

```bash
$ mngr stop my-agent
```

**Stop multiple agents**

```bash
$ mngr stop agent1 agent2
```

**Stop all running agents**

```bash
$ mngr stop --all
```

**Stop by tmux session name**

```bash
$ mngr stop --session mngr-my-agent
```

**Preview what would be stopped**

```bash
$ mngr stop --all --dry-run
```
