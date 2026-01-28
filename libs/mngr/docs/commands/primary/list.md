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

**Simple equality filters:**
- `name == "my-agent"` - Match agent by exact name
- `state == "running"` - Match running agents
- `host.provider == "docker"` - Match agents on Docker hosts

**Compound expressions:**
- `state == "running" && host.provider == "modal"` - Running agents on Modal
- `state == "stopped" || state == "failed"` - Stopped or failed agents

**String operations:**
- `name.contains("prod")` - Agent names containing "prod"
- `name.startsWith("staging-")` - Agent names starting with "staging-"



## Available Fields

The following fields can be used with `--fields` and in CEL filter expressions:

**Agent fields:**
- `name` - Agent name
- `id` - Agent ID
- `type` - Agent type (claude, codex, etc.)
- `state` - Lifecycle state (running, stopped, etc.)
- `status` - Status as reported by the agent
- `work_dir` - Working directory for this agent
- `create_time` - Creation timestamp
- `start_time` - Timestamp for when the agent was last started

**Host fields:**
- `host.name` - Host name
- `host.id` - Host ID
- `host.provider` - Host provider (local, docker, modal, etc.)
- `host.state` - Current host state


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
