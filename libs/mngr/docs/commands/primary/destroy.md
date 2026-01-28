# mngr destroy

Destroy agent(s) and clean up resources.

When the last agent on a host is destroyed, the host itself is also destroyed.

Examples:

  mngr destroy my-agent

  mngr destroy agent1 agent2 agent3

  mngr destroy --agent my-agent --agent another-agent

  mngr destroy --session mngr-my-agent

  mngr destroy --all --force

**Usage:**

```text
mngr destroy [OPTIONS] [AGENTS]...
```

**Options:**

| Name | Type | Description | Default |
| ---- | ---- | ----------- | ------- |
| `--agent` | text | Agent name or ID to destroy (can be specified multiple times) | None |
| `-a`, `--all`, `--all-agents` | boolean | Destroy all agents | `False` |
| `--session` | text | Tmux session name to destroy (can be specified multiple times). The agent name is extracted by stripping the configured prefix from the session name. | None |
| `-f`, `--force` | boolean | Skip confirmation prompts and force destroy running agents | `False` |
| `--dry-run` | boolean | Show what would be destroyed without actually destroying | `False` |
| `--gc` / `--no-gc` | boolean | Run garbage collection after destroying agents to clean up orphaned resources (default: enabled) | `True` |
| `--format` | choice (`human` &#x7C; `json` &#x7C; `jsonl`) | Output format for command results | `human` |
| `-q`, `--quiet` | boolean | Suppress all console output | `False` |
| `-v`, `--verbose` | integer range (`0` and above) | Increase verbosity (default: BUILD); -v for DEBUG, -vv for TRACE | `0` |
| `--log-file` | path | Path to log file (overrides default ~/.mngr/logs/<timestamp>-<pid>.json) | None |
| `--log-commands` / `--no-log-commands` | boolean | Log commands that were executed | None |
| `--log-command-output` / `--no-log-command-output` | boolean | Log stdout/stderr from commands | None |
| `--log-env-vars` / `--no-log-env-vars` | boolean | Log environment variables (security risk) | None |
| `--context` | path | Project context directory (for build context and loading project-specific config) [default: local .git root] | None |
| `--plugin`, `--enable-plugin` | text | Enable a plugin [repeatable] | None |
| `--disable-plugin` | text | Disable a plugin [repeatable] | None |
| `-h`, `--help` | boolean | Show this message and exit. | `False` |

## See Also

- [mngr create](./create.md) - Create a new agent
- [mngr list](./list.md) - List existing agents
- [mngr gc](../secondary/gc.md) - Garbage collect orphaned resources

## Examples

**Destroy an agent by name**

```bash
$ mngr destroy my-agent
```

**Destroy multiple agents**

```bash
$ mngr destroy agent1 agent2 agent3
```

**Destroy all agents**

```bash
$ mngr destroy --all --force
```

**Preview what would be destroyed**

```bash
$ mngr destroy my-agent --dry-run
```
