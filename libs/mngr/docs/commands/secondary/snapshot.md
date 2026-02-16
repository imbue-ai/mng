<!-- This file is auto-generated. Do not edit directly. -->
<!-- To modify, edit the command's help metadata and run: uv run python scripts/make_cli_docs.py -->

# mngr snapshot

**Synopsis:**

```text
mngr [snapshot|snap] [create|list|destroy] [AGENTS...] [OPTIONS]
```


Create, list, and destroy host snapshots.

Snapshots capture the complete state of an agent's host, allowing it
to be restored later. Because the snapshot is at the host level, the
state of all agents on the host is saved.

Alias: snap

Examples:

  mngr snapshot create my-agent

  mngr snapshot list my-agent

  mngr snapshot destroy my-agent --all-snapshots --force

**Usage:**

```text
mngr snapshot [OPTIONS] COMMAND [ARGS]...
```

**Options:**

## Common

| Name | Type | Description | Default |
| ---- | ---- | ----------- | ------- |
| `--format` | text | Output format: human, json, jsonl, or a template string (e.g. '{name}\t{state}') | `human` |
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

## mngr snapshot create

Create a snapshot of agent host(s).

Snapshots capture the complete filesystem state of a host. When multiple
agents share a host, the host is snapshotted once (capturing all agents).

Examples:

  mngr snapshot create my-agent

  mngr snapshot create my-agent --name before-refactor

  mngr snapshot create --all --dry-run

**Usage:**

```text
mngr snapshot create [OPTIONS] [AGENTS]...
```

**Options:**

## Target Selection

| Name | Type | Description | Default |
| ---- | ---- | ----------- | ------- |
| `--agent` | text | Agent name or ID to snapshot (can be specified multiple times) | None |
| `--host` | text | Host ID or name to snapshot directly (can be specified multiple times) | None |
| `-a`, `--all`, `--all-agents` | boolean | Snapshot all running agents | `False` |

## Snapshot Options

| Name | Type | Description | Default |
| ---- | ---- | ----------- | ------- |
| `--name` | text | Custom name for the snapshot | None |
| `--dry-run` | boolean | Show what would be snapshotted without actually creating snapshots | `False` |
| `--include` | text | Filter agents by CEL expression (repeatable) [future] | None |
| `--exclude` | text | Exclude agents matching CEL expression (repeatable) [future] | None |
| `--stdin` | boolean | Read agent/host names from stdin [future] | `False` |
| `--tag` | text | Metadata tag for the snapshot (KEY=VALUE) [future] | None |
| `--description` | text | Description for the snapshot [future] | None |
| `--restart-if-larger-than` | text | Restart host if snapshot exceeds size (e.g., 5G) [future] | None |
| `--pause-during`, `--no-pause-during` | boolean | Pause agent during snapshot creation [future] | `True` |
| `--wait`, `--no-wait` | boolean | Wait for snapshot to complete [future] | `True` |

## Common

| Name | Type | Description | Default |
| ---- | ---- | ----------- | ------- |
| `--format` | text | Output format: human, json, jsonl, or a template string (e.g. '{name}\t{state}') | `human` |
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

## mngr snapshot list

List snapshots for agent host(s).

Shows snapshot ID, name, creation time, size, and host for each snapshot.

Examples:

  mngr snapshot list my-agent

  mngr snapshot list --all

  mngr snapshot list my-agent --limit 5

  mngr snapshot list my-agent --format json

**Usage:**

```text
mngr snapshot list [OPTIONS] [AGENTS]...
```

**Options:**

## Target Selection

| Name | Type | Description | Default |
| ---- | ---- | ----------- | ------- |
| `--agent` | text | Agent name or ID to list snapshots for (can be specified multiple times) | None |
| `-a`, `--all`, `--all-agents` | boolean | List snapshots for all running agents | `False` |

## Filtering

| Name | Type | Description | Default |
| ---- | ---- | ----------- | ------- |
| `--limit` | integer | Maximum number of snapshots to show | None |
| `--include` | text | Filter snapshots by CEL expression (repeatable) [future] | None |
| `--exclude` | text | Exclude snapshots matching CEL expression (repeatable) [future] | None |
| `--after` | text | Show only snapshots created after this date [future] | None |
| `--before` | text | Show only snapshots created before this date [future] | None |

## Common

| Name | Type | Description | Default |
| ---- | ---- | ----------- | ------- |
| `--format` | text | Output format: human, json, jsonl, or a template string (e.g. '{name}\t{state}') | `human` |
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

## mngr snapshot destroy

Destroy snapshots for agent host(s).

Requires either --snapshot (to delete specific snapshots) or --all-snapshots
(to delete all snapshots for the resolved hosts). A confirmation prompt is
shown unless --force is specified.

Examples:

  mngr snapshot destroy my-agent --snapshot snap-abc123 --force

  mngr snapshot destroy my-agent --all-snapshots --force

  mngr snapshot destroy my-agent --all-snapshots --dry-run

**Usage:**

```text
mngr snapshot destroy [OPTIONS] [AGENTS]...
```

**Options:**

## Target Selection

| Name | Type | Description | Default |
| ---- | ---- | ----------- | ------- |
| `--agent` | text | Agent name or ID whose snapshots to destroy (can be specified multiple times) | None |
| `--snapshot` | text | Snapshot ID to destroy (can be specified multiple times) | None |
| `--all-snapshots` | boolean | Destroy all snapshots for the specified agent(s) | `False` |

## Safety

| Name | Type | Description | Default |
| ---- | ---- | ----------- | ------- |
| `-f`, `--force` | boolean | Skip confirmation prompt | `False` |
| `--dry-run` | boolean | Show what would be destroyed without actually deleting | `False` |
| `--include` | text | Filter snapshots by CEL expression (repeatable) [future] | None |
| `--exclude` | text | Exclude snapshots matching CEL expression (repeatable) [future] | None |
| `--stdin` | boolean | Read agent/host names from stdin [future] | `False` |

## Common

| Name | Type | Description | Default |
| ---- | ---- | ----------- | ------- |
| `--format` | text | Output format: human, json, jsonl, or a template string (e.g. '{name}\t{state}') | `human` |
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

## See Also

- [mngr create](../primary/create.md) - Create a new agent (supports --snapshot to restore from snapshot)
- [mngr gc](./gc.md) - Garbage collect unused resources including snapshots

## Examples

**Create a snapshot of an agent's host**

```bash
$ mngr snapshot create my-agent
```

**Create a named snapshot**

```bash
$ mngr snapshot create my-agent --name before-refactor
```

**List snapshots for an agent**

```bash
$ mngr snapshot list my-agent
```

**Destroy all snapshots for an agent**

```bash
$ mngr snapshot destroy my-agent --all-snapshots --force
```

**Preview what would be destroyed**

```bash
$ mngr snapshot destroy my-agent --all-snapshots --dry-run
```
