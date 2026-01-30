<!-- This file is auto-generated. Do not edit directly. -->
<!-- To modify, edit the command's help metadata and run: uv run python scripts/make_cli_docs.py -->

# mngr list

**Synopsis:**

```text
mngr [list|ls] [OPTIONS]
```


List all agents managed by mngr.

Displays agents with their status, host information, and other metadata.
Supports filtering, sorting, and multiple output formats.

Examples:

  mngr list

  mngr list --running

  mngr list --provider docker

  mngr list --format json

**Usage:**

```text
mngr list [OPTIONS]
```

**Options:**

## Filtering

| Name | Type | Description | Default |
| ---- | ---- | ----------- | ------- |
| `--include` | text | Include agents matching CEL expression (repeatable) | None |
| `--exclude` | text | Exclude agents matching CEL expression (repeatable) | None |
| `--running` | boolean | Show only running agents (alias for --include 'state == "running"') | `False` |
| `--stopped` | boolean | Show only stopped agents (alias for --include 'state == "stopped"') | `False` |
| `--local` | boolean | Show only local agents (alias for --include 'host.provider == "local"') | `False` |
| `--remote` | boolean | Show only remote agents (alias for --exclude 'host.provider == "local"') | `False` |
| `--provider` | text | Show only agents using specified provider (repeatable) | None |
| `--stdin` | boolean | Read agent and host IDs or names from stdin (one per line) | `False` |

## Output Format

| Name | Type | Description | Default |
| ---- | ---- | ----------- | ------- |
| `--format-template` | text | Output format as a string template (mutually exclusive with --format) [future] | None |
| `--fields` | text | Which fields to include (comma-separated) | None |
| `--sort` | text | Sort by field [default: create_time] [future] | `create_time` |
| `--sort-order` | choice (`asc` &#x7C; `desc`) | Sort order [default: asc] | `asc` |
| `--limit` | integer | Limit number of results [future] | None |

## Watch Mode

| Name | Type | Description | Default |
| ---- | ---- | ----------- | ------- |
| `-w`, `--watch` | integer | Continuously watch and update status at specified interval (seconds) [future] | None |

## Error Handling

| Name | Type | Description | Default |
| ---- | ---- | ----------- | ------- |
| `--on-error` | choice (`abort` &#x7C; `continue`) | What to do when errors occur: abort (stop immediately) or continue (keep going) | `abort` |

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

## CEL Filter Examples

CEL (Common Expression Language) filters allow powerful, expressive filtering of agents.
All agent fields from the "Available Fields" section can be used in filter expressions.

**Simple equality filters:**
- `name == "my-agent"` - Match agent by exact name
- `state == "running"` - Match running agents
- `host.provider == "docker"` - Match agents on Docker hosts
- `type == "claude"` - Match agents of type "claude"

**Compound expressions:**
- `state == "running" && host.provider == "modal"` - Running agents on Modal
- `state == "stopped" || state == "failed"` - Stopped or failed agents
- `host.provider == "docker" && name.startsWith("test-")` - Docker agents with names starting with "test-"

**String operations:**
- `name.contains("prod")` - Agent names containing "prod"
- `name.startsWith("staging-")` - Agent names starting with "staging-"
- `name.endsWith("-dev")` - Agent names ending with "-dev"

**Numeric comparisons:**
- `runtime_seconds > 3600` - Agents running for more than an hour
- `idle_seconds < 300` - Agents active in the last 5 minutes
- `host.resource.memory_gb >= 8` - Agents on hosts with 8GB+ memory
- `host.uptime_seconds > 86400` - Agents on hosts running for more than a day

**Existence checks:**
- `has(url)` - Agents that have a URL set
- `has(host.ssh)` - Agents on remote hosts with SSH access



## Available Fields

**Agent fields** (same syntax for `--fields` and CEL filters):
- `name` - Agent name
- `id` - Agent ID
- `type` - Agent type (claude, codex, etc.)
- `command` - The command used to start the agent
- `url` - URL where the agent can be accessed (if reported)
- `status` - Status as reported by the agent
  - `status.line` - A single line summary
  - `status.full` - A longer description of the current status
  - `status.html` - Full HTML status report (if available)
- `work_dir` - Working directory for this agent
- `create_time` - Creation timestamp
- `start_time` - Timestamp for when the agent was last started
- `runtime_seconds` - How long the agent has been running
- `user_activity_time` - Timestamp of the last user activity
- `agent_activity_time` - Timestamp of the last agent activity
- `ssh_activity_time` - Timestamp when we last noticed an active SSH connection
- `idle_seconds` - How long since the agent was active
- `idle_mode` - Idle detection mode
- `start_on_boot` - Whether the agent is set to start on host boot
- `state` - Lifecycle state (running, stopped, etc.) - derived from lifecycle_state
- `plugin.$PLUGIN_NAME.*` - Plugin-defined fields (e.g., `plugin.chat_history.messages`)

**Host fields** (dot notation for both `--fields` and CEL filters):
- `host.name` - Host name
- `host.id` - Host ID
- `host.host` - Hostname where the host is running (ssh.host for remote, localhost for local)
- `host.provider` - Host provider (local, docker, modal, etc.)
- `host.state` - Current host state (running, stopped, building, etc.)
- `host.image` - Host image (Docker image name, Modal image ID, etc.)
- `host.tags` - Metadata tags for the host
- `host.boot_time` - When the host was last started
- `host.uptime_seconds` - How long the host has been running
- `host.resource` - Resource limits for the host
  - `host.resource.cpu.count` - Number of CPUs
  - `host.resource.cpu.frequency_ghz` - CPU frequency in GHz
  - `host.resource.memory_gb` - Memory in GB
  - `host.resource.disk_gb` - Disk space in GB
  - `host.resource.gpu.count` - Number of GPUs
  - `host.resource.gpu.model` - GPU model name
  - `host.resource.gpu.memory_gb` - GPU memory in GB
- `host.ssh` - SSH access details (remote hosts only)
  - `host.ssh.command` - Full SSH command to connect
  - `host.ssh.host` - SSH hostname
  - `host.ssh.port` - SSH port
  - `host.ssh.user` - SSH username
  - `host.ssh.key_path` - Path to SSH private key
- `host.snapshots` - List of available snapshots
- `host.plugin.$PLUGIN_NAME.*` - Host plugin fields (e.g., `host.plugin.aws.iam_user`)

**Notes:**
- You can use Python-style list slicing for list fields (e.g., `host.snapshots[0]` for the first snapshot, `host.snapshots[:3]` for the first 3)



## Related Documentation

- [Multi-target Options](../generic/multi_target.md) - Behavior when some agents cannot be accessed
- [Common Options](../generic/common.md) - Common CLI options for output format, logging, etc.

## See Also

- [mngr create](./create.md) - Create a new agent
- [mngr connect](./connect.md) - Connect to an existing agent
- [mngr destroy](./destroy.md) - Destroy agents

## Examples

**List all agents**

```bash
$ mngr list
```

**List only running agents**

```bash
$ mngr list --running
```

**List agents on Docker hosts**

```bash
$ mngr list --provider docker
```

**List agents as JSON**

```bash
$ mngr list --format json
```

**Filter with CEL expression**

```bash
$ mngr list --include 'name.contains("prod")'
```
