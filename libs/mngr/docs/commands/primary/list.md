# mngr list

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

| Name | Type | Description | Default |
| ---- | ---- | ----------- | ------- |
| `--include` | text | Include agents matching CEL expression (repeatable) | None |
| `--exclude` | text | Exclude agents matching CEL expression (repeatable) | None |
| `--running` | boolean | Show only running agents (alias for --include state == "running") | `False` |
| `--stopped` | boolean | Show only stopped agents (alias for --include state == "stopped") | `False` |
| `--local` | boolean | Show only local agents (alias for --include host.provider == "local") | `False` |
| `--remote` | boolean | Show only remote agents (alias for --exclude host.provider == "local") | `False` |
| `--provider` | text | Show only agents using specified provider (repeatable) | None |
| `--stdin` | boolean | Read agent and host IDs or names from stdin (one per line) | `False` |
| `--format-template` | text | Output format as a string template (mutually exclusive with --format) | None |
| `--fields` | text | Which fields to include (comma-separated) | None |
| `--sort` | text | Sort by field [default: create_time] | `create_time` |
| `--sort-order` | choice (`asc` &#x7C; `desc`) | Sort order [default: asc] | `asc` |
| `--limit` | integer | Limit number of results | None |
| `-w`, `--watch` | integer | Continuously watch and update status at specified interval (seconds) [default: 2] | None |
| `--on-error` | choice (`abort` &#x7C; `continue`) | What to do when errors occur: abort (stop immediately) or continue (keep going) | `abort` |
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

**Existence checks:**
- `has(url)` - Agents that have a URL set
- `has(host.ssh)` - Agents on remote hosts with SSH access



## Available Fields

The following fields can be used with `--fields`, `--format-template`, and in CEL filter expressions.

**Agent fields:**
- `name` - Agent name
- `id` - Agent ID
- `type` - Agent type (claude, codex, etc.)
- `command` - The command used to start the agent
- `url` - URL where the agent can be accessed
- `status` - Status as reported by the agent
  - `status.line` - A single line summary
  - `status.full` - A longer description of the current status
  - `status.html` - Full HTML status report
- `work_dir` - Working directory for this agent
- `create_time` - Creation timestamp
- `start_time` - Timestamp for when the agent was last started
- `runtime_seconds` - How long the agent has been running
- `user_activity_time` - Timestamp of the last user activity
- `agent_activity_time` - Timestamp of the last agent activity
- `ssh_activity_time` - Timestamp when we last noticed an active ssh connection
- `idle_seconds` - How long since the agent was active
- `idle_mode` - Idle detection mode
- `start_on_boot` - Whether the agent is set to start on host boot
- `plugin.$PLUGIN_NAME.*` - Plugin-defined fields (e.g., `plugin.chat_history.messages`)

**Host fields:**
- `host.name` - Host name
- `host.id` - Host ID
- `host.host` - Hostname where the host is running (if applicable)
- `host.provider` - Host provider (local, docker, modal, etc.)
- `host.state` - Current host state (building, starting, running, stopping, stopped, destroyed, failed)
- `host.image` - Host image (Docker image name, Modal image ID, etc.)
- `host.tags` - Metadata tags for the host
- `host.ssh` - SSH access details (remote hosts only)
  - `host.ssh.command` - Full SSH command
  - `host.ssh.host` - SSH host
  - `host.ssh.port` - SSH port
  - `host.ssh.user` - SSH username
  - `host.ssh.key_path` - Path to SSH private key
- `host.resource` - Resource limits for the host
  - `host.resource.cpu.count` - Number of allocated CPU
  - `host.resource.cpu.frequency_ghz` - CPU frequency in GHz
  - `host.resource.memory_gb` - Allocated memory in GB
  - `host.resource.disk_gb` - Allocated disk space in GB
- `host.snapshots` - List of all available snapshots
- `host.boot_time` - When the host was last started
- `host.is_locked` - If locked for an operation
- `host.locked_time` - When the host was locked for an operation
- `host.uptime_seconds` - How long the host has been running
- `host.plugin.$PLUGIN_NAME.*` - Plugin-defined fields (e.g., `host.plugin.aws.iam_user`)

**Notes:**
Fields which are lists can be sliced using standard Python list slicing syntax,
e.g. `host.snapshots[0]` for the most recent snapshot, or `host.snapshots[:3]`
for the three most recent snapshots.


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
