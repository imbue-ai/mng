# mngr list - CLI Options Reference

Lists all agents managed by mngr.

Includes filtering and formatting options. By default, shows agent host type and status in a way that is easily readable by humans.

**Alias:** `ls`

## Usage

```
mngr list
```

## General

- `--watch, -w SECONDS`: Continuously watch and update status. If SECONDS is provided, update at that interval [default: 2]

See [multi-target](../generic/multi_target.md) options for behavior when some agents cannot be accessed.

## Filtering

- `--include FILTER`: Include agents matching CEL expression [repeatable]
- `--exclude FILTER`: Exclude agents matching CEL expression [repeatable]
- `--running`: Show only running agents (alias for `--include 'state == "running"'`)
- `--stopped`: Show only stopped agents (alias for `--include 'state == "stopped"'`)
- `--local`: Show only local agents (alias for `--include host.provider == "local"`)
- `--remote`: Show only remote agents (alias for `--exclude host.provider == "local"`)
- `--provider PROVIDER`: Show only agents using specified provider (e.g., `docker`, `modal`) [repeatable]
- `--stdin`: Read agents and hosts to watch (ids or names) from stdin (one per line)

### CEL Filter Examples

CEL (Common Expression Language) filters allow powerful, expressive filtering of agents. All agent fields from the "Available Fields" section below can be used directly in filter expressions.

Simple equality filters:
- `name == "my-agent"` - Match agent by exact name
- `status == "running"` - Match running agents
- `host.provider == "docker"` - Match agents on Docker hosts
- `type == "claude"` - Match agents of type "claude"

Compound expressions:
- `status == "running" && host.provider == "modal"` - Running agents on Modal
- `status == "stopped" || status == "failed"` - Stopped or failed agents
- `host.provider == "docker" && name.startsWith("test-")` - Docker agents with names starting with "test-"

String operations:
- `name.contains("prod")` - Agent names containing "prod"
- `name.startsWith("staging-")` - Agent names starting with "staging-"
- `name.endsWith("-dev")` - Agent names ending with "-dev"

Numeric comparisons:
- `runtime_seconds > 3600` - Agents running for more than an hour
- `idle_seconds < 300` - Agents active in the last 5 minutes
- `host.resource.memory_gb >= 8` - Agents on hosts with 8GB+ memory

Existence checks:
- `has(url)` - Agents that have a URL set
- `has(host.ssh)` - Agents on remote hosts with SSH access

## Output Format

- `--format FORMAT`: Output format as a string template, see docs. Mutually exclusive with `--json` and `--jsonl` (see [common options](../generic/common.md))
- `--fields FIELDS`: Which fields to include (comma-separated). See below for list of available fields.
- `--sort FIELD`: Sort by field [default: `created`]
- `--sort-order ORDER`: Sort order [default: `asc`, choices: `asc`, `desc`]
- `--limit N`: Limit number of results

# Available Fields

The following fields can be used with `--fields` and `--format`.

- `name`: Agent name
- `id`: Agent ID
- `type`: Agent type (claude, codex, etc.)
- `command`: The command used to start the agent
- `url`: URL where the agent can be accessed
- `status`: Status as reported by the agent
  - `status.line`: A single line summary
  - `status.full`: A longer description of the current status
  - `status.html`: Full HTML status report
- `work_dir`: Working directory for this agent
- `create_time`: Creation timestamp
- `start_time`: Timestamp for when the agent was last started
- `runtime_seconds`: How long the agent has been running
- `user_activity_time`: Timestamp of the last user activity
- `agent_activity_time`: Timestamp of the last agent activity
- `ssh_activity_time`: Timestamp when we last noticed an active ssh connection
- `idle_seconds`: How long since the agent was active
- `idle_mode`: Idle detection mode
- `start_on_boot`: Whether the agent is set to start on host boot
- `plugin.$PLUGIN_NAME.*`: Each plugin can add its own fields under its namespace (e.g., `plugin.chat_history.messages`)
- `host`: Host information
  - `host.name`: Host name
  - `host.id`: Host ID
  - `host.host`: Hostname where the host is running (if applicable)
  - `host.provider`: Host provider (local, docker, modal, etc.)
  - `host.state`: Current host state (building, starting, running, stopping, stopped, destroyed, failed)
  - `host.image`: Host image (Docker image name, Modal image ID, etc.)
  - `host.tags`: Metadata tags for the host
  - `host.ssh`: SSH access details (remote hosts only)
    - `host.ssh.command`: Full SSH command
    - `host.ssh.host`: SSH host
    - `host.ssh.port`: SSH port
    - `host.ssh.user`: SSH username
    - `host.ssh.key_path`: Path to SSH private key
  - `host.resource`: Resource limits for the host. These likely differ per provider.
    - `host.resource.cpu.count`: Number of allocated CPU
    - `host.resource.cpu.frequency_ghz`: CPU frequency in GHz
    - `host.resource.memory_gb`: Allocated memory in GB
    - `host.resource.disk_gb`: Allocated disk space in GB
  - `host.snapshots`: List of all available snapshots
  - `host.boot_time`: When the host was last started
  - `host.is_locked`: If locked for an operation.
  - `host.locked_time`: When the host was locked for an operation. Empty if not locked
  - `host.uptime_seconds`: How long the host has been running
  - `host.plugin`: Plugin-defined fields, namespaced by plugin name
    - `host.plugin.$PLUGIN_NAME.*`: Each plugin can add its own fields under its namespace (e.g., `machine.plugin.aws.iam_user`)

---

## Notes

Fields which are lists can be sliced using standard Python list slicing syntax, e.g. `machine.snapshots[0]` for the most recent snapshot, or `machine.snapshots[:3]` for the three most recent snapshots.
