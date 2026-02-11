# mngr CLI Documentation

---

This is the reference documentation for all mngr commands.

---

<!-- This file is auto-generated. Do not edit directly. -->
<!-- To modify, edit the command's help metadata and run: uv run python scripts/make_cli_docs.py -->

# mngr connect

**Synopsis:**

```text
mngr [connect|conn] [OPTIONS] [AGENT]
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

## Arguments

- `AGENT`: The agent (optional)

**Options:**

## General

| Name | Type | Description | Default |
| ---- | ---- | ----------- | ------- |
| `--agent` | text | The agent to connect to (by name or ID) | None |
| `--start`, `--no-start` | boolean | Automatically start the agent if stopped | `True` |

## Options

| Name | Type | Description | Default |
| ---- | ---- | ----------- | ------- |
| `--reconnect`, `--no-reconnect` | boolean | Automatically reconnect if dropped [future] | `True` |
| `--message` | text | Initial message to send after connecting [future] | None |
| `--message-file` | path | File containing initial message to send [future] | None |
| `--ready-timeout` | float | Timeout in seconds to wait for agent readiness [future] | `10.0` |
| `--retry` | integer | Number of connection retries [future] | `3` |
| `--retry-delay` | text | Delay between retries [future] | `5s` |
| `--attach-command` | text | Command to run instead of attaching to main session [future] | None |
| `--allow-unknown-host`, `--no-allow-unknown-host` | boolean | Allow connecting to hosts without a known_hosts file (disables SSH host key verification) | `False` |

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
---


---

<!-- This file is auto-generated. Do not edit directly. -->
<!-- To modify, edit the command's help metadata and run: uv run python scripts/make_cli_docs.py -->

# mngr create

**Synopsis:**

```text
mngr [create|c] [<AGENT_NAME>] [<AGENT_TYPE>] [-t <TEMPLATE>] [--in <PROVIDER>] [--host <HOST>] [--c WINDOW_NAME=COMMAND]
    [--tag KEY=VALUE] [--project <PROJECT>] [--from <SOURCE>] [--in-place|--copy|--clone|--worktree]
    [--[no-]rsync] [--rsync-args <ARGS>] [--base-branch <BRANCH>] [--new-branch [<BRANCH-NAME>]] [--[no-]ensure-clean]
    [--snapshot <ID>] [-b <BUILD_ARG>] [-s <START_ARG>]
    [--env <KEY=VALUE>] [--env-file <FILE>] [--grant <PERMISSION>] [--user-command <COMMAND>] [--upload-file <LOCAL:REMOTE>]
    [--idle-timeout <SECONDS>] [--idle-mode <MODE>] [--start-on-boot|--no-start-on-boot] [--reuse|--no-reuse]
    [--] [<AGENT_ARGS>...]
```


Create and run an agent.

Sets up the agent's work_dir, optionally provisions a new host (or uses
an existing one), runs the specified agent, and connects to it (by default).

Alias: c

**Usage:**

```text
mngr create [OPTIONS] [POSITIONAL_NAME] [POSITIONAL_AGENT_TYPE]
            [AGENT_ARGS]...
```

## Arguments

- `NAME`: Name for the agent (auto-generated if not provided)
- `AGENT_TYPE`: Which type of agent to run (default: `claude`). Can also be specified via `--agent-type`
- `AGENT_ARGS`: Additional arguments passed to the agent

**Options:**

## Agent Options

| Name | Type | Description | Default |
| ---- | ---- | ----------- | ------- |
| `-t`, `--template` | text | Use a named template from create_templates config [repeatable, stacks in order] | None |
| `-n`, `--name` | text | Agent name (alternative to positional argument) [default: auto-generated] | None |
| `--name-style` | choice (`english` &#x7C; `fantasy` &#x7C; `scifi` &#x7C; `painters` &#x7C; `authors` &#x7C; `artists` &#x7C; `musicians` &#x7C; `animals` &#x7C; `scientists` &#x7C; `demons`) | Auto-generated name style | `english` |
| `--agent-type` | text | Which type of agent to run [default: claude] | None |
| `--agent-cmd`, `--agent-command` | text | Run a literal command using the generic agent type (mutually exclusive with --agent-type) | None |
| `-c`, `--add-cmd`, `--add-command` | text | Run extra command in additional window. Use name="command" to set window name. Note: ALL_UPPERCASE names (e.g., FOO="bar") are treated as env var assignments, not window names | None |
| `--user` | text | Override which user to run the agent as [default: current user for local, provider-defined or root for remote] | None |

## Host Options

By default, `mngr create` uses the "local" host. Use these options to change that behavior.

| Name | Type | Description | Default |
| ---- | ---- | ----------- | ------- |
| `--in`, `--new-host` | text | Create a new host using provider (docker, modal, ...) | None |
| `--host`, `--target-host` | text | Use an existing host (by name or ID) [default: local] | None |
| `--project` | text | Project name for the agent [default: derived from git remote origin or folder name] | None |
| `--tag` | text | Metadata tag KEY=VALUE [repeatable] | None |
| `--host-name` | text | Name for the new host | None |
| `--host-name-style` | choice (`astronomy` &#x7C; `places` &#x7C; `cities` &#x7C; `fantasy` &#x7C; `scifi` &#x7C; `painters` &#x7C; `authors` &#x7C; `artists` &#x7C; `musicians` &#x7C; `scientists`) | Auto-generated host name style | `astronomy` |

## Behavior

| Name | Type | Description | Default |
| ---- | ---- | ----------- | ------- |
| `--reuse`, `--no-reuse` | boolean | Reuse existing agent with the same name if it exists (idempotent create) | `False` |
| `--connect`, `--no-connect` | boolean | Connect to the agent after creation [default: connect] | `True` |
| `--await-ready`, `--no-await-ready` | boolean | Wait until agent is ready before returning [default: no-await-ready if --no-connect] | None |
| `--await-agent-stopped`, `--no-await-agent-stopped` | boolean | Wait until agent has completely finished running before exiting. Useful for testing and scripting. First waits for agent to become ready, then waits for it to stop. [default: no-await-agent-stopped] | None |
| `--ensure-clean`, `--no-ensure-clean` | boolean | Abort if working tree is dirty | `True` |
| `--snapshot-source`, `--no-snapshot-source` | boolean | Snapshot source agent first [default: yes if --source-agent and not local] | None |
| `--copy-work-dir`, `--no-copy-work-dir` | boolean | Copy source work_dir immediately. Useful when launching background agents so you can continue editing locally without changes being copied to the new agent [default: copy if --no-connect, no-copy if --connect] | None |

## Agent Source Data (what to include in the new agent)

| Name | Type | Description | Default |
| ---- | ---- | ----------- | ------- |
| `--from`, `--source` | text | Directory to use as work_dir root [AGENT &#x7C; AGENT.HOST &#x7C; AGENT.HOST:PATH &#x7C; HOST:PATH]. Defaults to current dir if no other source args are given | None |
| `--source-agent`, `--from-agent` | text | Source agent for cloning work_dir | None |
| `--source-host` | text | Source host | None |
| `--source-path` | text | Source path | None |
| `--rsync`, `--no-rsync` | boolean | Use rsync for file transfer [default: yes if rsync-args are present or if git is disabled] | None |
| `--rsync-args` | text | Additional arguments to pass to rsync | None |
| `--include-git`, `--no-include-git` | boolean | Include .git directory | `True` |
| `--include-unclean`, `--exclude-unclean` | boolean | Include uncommitted files [default: include if --no-ensure-clean] | None |
| `--include-gitignored`, `--no-include-gitignored` | boolean | Include gitignored files | `False` |

## Agent Target (where to put the new agent)

| Name | Type | Description | Default |
| ---- | ---- | ----------- | ------- |
| `--target` | text | Target [HOST][:PATH]. Defaults to current dir if no other target args are given | None |
| `--target-path` | text | Directory to mount source inside agent host. Incompatible with --in-place | None |
| `--in-place` | boolean | Run directly in source directory. Incompatible with --target-path | `False` |
| `--copy` | boolean | Copy source to isolated directory before running [default for remote agents, and for local agents if not in a git repo] | `False` |
| `--clone` | boolean | Create a git clone that shares objects with original repo (only works for local agents) | `False` |
| `--worktree` | boolean | Create a git worktree that shares objects and index with original repo [default for local agents in a git repo]. Requires --new-branch (which is the default) | `False` |

## Agent Git Configuration

| Name | Type | Description | Default |
| ---- | ---- | ----------- | ------- |
| `--base-branch` | text | The starting point for the agent [default: current branch] | None |
| `--new-branch` | text | Create a fresh branch (named TEXT if provided, otherwise auto-generated) [default: new branch] | `` |
| `--no-new-branch` | boolean | Do not create a new branch; use the current branch directly. Incompatible with --worktree | None |
| `--new-branch-prefix` | text | Prefix for auto-generated branch names | `mngr/` |
| `--depth` | integer | Shallow clone depth [default: full] | None |
| `--shallow-since` | text | Shallow clone since date | None |

## Agent Environment Variables

| Name | Type | Description | Default |
| ---- | ---- | ----------- | ------- |
| `--env`, `--agent-env` | text | Set environment variable KEY=VALUE | None |
| `--env-file`, `--agent-env-file` | path | Load env | None |
| `--pass-env`, `--pass-agent-env` | text | Forward variable from shell | None |

## Agent Provisioning

See [Provision Options](../secondary/provision.md) for full details.

| Name | Type | Description | Default |
| ---- | ---- | ----------- | ------- |
| `--grant` | text | Grant a permission to the agent [repeatable] | None |
| `--user-command` | text | Run custom shell command during provisioning [repeatable] | None |
| `--sudo-command` | text | Run custom shell command as root during provisioning [repeatable] | None |
| `--upload-file` | text | Upload LOCAL:REMOTE file pair [repeatable] | None |
| `--append-to-file` | text | Append REMOTE:TEXT to file [repeatable] | None |
| `--prepend-to-file` | text | Prepend REMOTE:TEXT to file [repeatable] | None |
| `--create-directory` | text | Create directory on remote [repeatable] | None |

## New Host Environment Variables

| Name | Type | Description | Default |
| ---- | ---- | ----------- | ------- |
| `--host-env` | text | Set environment variable KEY=VALUE for host [repeatable] | None |
| `--host-env-file` | path | Load env file for host [repeatable] | None |
| `--pass-host-env` | text | Forward variable from shell for host [repeatable] | None |
| `--known-host` | text | SSH known_hosts entry to add to the host (for outbound SSH) [repeatable] | None |

## New Host Build

| Name | Type | Description | Default |
| ---- | ---- | ----------- | ------- |
| `--snapshot` | text | Use existing snapshot instead of building | None |
| `-b`, `--build`, `--build-arg` | text | Build argument as key=value or --key=value (e.g., -b gpu=h100 -b cpu=2) [repeatable] | None |
| `--build-args` | text | Space-separated build arguments (e.g., 'gpu=h100 cpu=2') | None |
| `-s`, `--start`, `--start-arg` | text | Argument for start [repeatable] | None |
| `--start-args` | text | Space-separated start arguments (alternative to -s) | None |

## New Host Lifecycle

| Name | Type | Description | Default |
| ---- | ---- | ----------- | ------- |
| `--idle-timeout` | integer | Shutdown after idle for N seconds [default: none] | None |
| `--idle-mode` | choice (`io` &#x7C; `user` &#x7C; `agent` &#x7C; `ssh` &#x7C; `create` &#x7C; `boot` &#x7C; `start` &#x7C; `run` &#x7C; `custom` &#x7C; `disabled`) | When to consider host idle [default: io if remote, disabled if local] | None |
| `--activity-sources` | text | Activity sources for idle detection (comma-separated) | None |
| `--start-on-boot`, `--no-start-on-boot` | boolean | Restart on host boot [default: no] | None |

## Connection Options

See [connect options](./connect.md) for full details (only applies if `--connect` is specified).

| Name | Type | Description | Default |
| ---- | ---- | ----------- | ------- |
| `--reconnect`, `--no-reconnect` | boolean | Automatically reconnect if dropped | `True` |
| `--interactive`, `--no-interactive` | boolean | Enable interactive mode [default: yes if TTY] | None |
| `--message` | text | Initial message to send after the agent starts | None |
| `--message-file` | path | File containing initial message to send | None |
| `--edit-message` | boolean | Open an editor to compose the initial message (uses $EDITOR). Editor runs in parallel with agent creation. If --message or --message-file is provided, their content is used as initial editor content. | `False` |
| `--resume-message` | text | Message to send when the agent is started (resumed) after being stopped | None |
| `--resume-message-file` | path | File containing resume message to send on start | None |
| `--ready-timeout` | float | Timeout in seconds to wait for agent readiness before sending initial message | `10.0` |
| `--retry` | integer | Number of connection retries | `3` |
| `--retry-delay` | text | Delay between retries (e.g., 5s, 1m) | `5s` |
| `--attach-command` | text | Command to run instead of attaching to main session | None |

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

## Agent Limits

See [Limit Options](../secondary/limit.md)

## See Also

- [mngr connect](./connect.md) - Connect to an existing agent
- [mngr list](./list.md) - List existing agents
- [mngr destroy](./destroy.md) - Destroy agents

## Examples

**Create an agent locally in a new git worktree (default)**

```bash
$ mngr create my-agent
```

**Create an agent in a Docker container**

```bash
$ mngr create my-agent --in docker
```

**Create an agent in a Modal sandbox**

```bash
$ mngr create my-agent --in modal
```

**Create using a named template**

```bash
$ mngr create my-agent --template modal
```

**Stack multiple templates**

```bash
$ mngr create my-agent -t modal -t codex
```

**Create a codex agent instead of claude**

```bash
$ mngr create my-agent codex
```

**Pass arguments to the agent**

```bash
$ mngr create my-agent -- --model opus
```

**Create on an existing host**

```bash
$ mngr create my-agent --host my-dev-box
```

**Clone from an existing agent**

```bash
$ mngr create new-agent --source other-agent
```

**Run directly in-place (no worktree)**

```bash
$ mngr create my-agent --in-place
```

**Create without connecting**

```bash
$ mngr create my-agent --no-connect
```

**Add extra tmux windows**

```bash
$ mngr create my-agent -c server="npm run dev"
```

**Reuse existing agent or create if not found**

```bash
$ mngr create my-agent --reuse
```
---


---

<!-- This file is auto-generated. Do not edit directly. -->
<!-- To modify, edit the command's help metadata and run: uv run python scripts/make_cli_docs.py -->

# mngr destroy

**Synopsis:**

```text
mngr [destroy|rm] [AGENTS...] [--agent <AGENT>] [--all] [--session <SESSION>] [-f|--force] [--dry-run]
```


Destroy agent(s) and clean up resources.

When the last agent on a host is destroyed, the host itself is also destroyed.

Use with caution! This operation is irreversible.

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

## Arguments

- `AGENTS`: The agents (optional)

**Options:**

## Target Selection

| Name | Type | Description | Default |
| ---- | ---- | ----------- | ------- |
| `--agent` | text | Agent name or ID to destroy (can be specified multiple times) | None |
| `-a`, `--all`, `--all-agents` | boolean | Destroy all agents | `False` |
| `--session` | text | Tmux session name to destroy (can be specified multiple times). The agent name is extracted by stripping the configured prefix from the session name. | None |
| `--include` | text | Filter agents to destroy by CEL expression (repeatable). [future] | None |
| `--exclude` | text | Exclude agents matching CEL expression from destruction (repeatable). [future] | None |
| `--stdin` | boolean | Read agent names/IDs from stdin, one per line. [future] | `False` |

## Behavior

| Name | Type | Description | Default |
| ---- | ---- | ----------- | ------- |
| `-f`, `--force` | boolean | Skip confirmation prompts and force destroy running agents | `False` |
| `--dry-run` | boolean | Show what would be destroyed without actually destroying | `False` |
| `--gc`, `--no-gc` | boolean | Run garbage collection after destroying agents to clean up orphaned resources (default: enabled) | `True` |

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

## Related Documentation

- [Resource Cleanup Options](../generic/resource_cleanup.md) - Control which associated resources are destroyed
- [Multi-target Options](../generic/multi_target.md) - Behavior when targeting multiple agents

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
---


---

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
| `--running` | boolean | Show only running agents (alias for --include 'state == "RUNNING"') | `False` |
| `--stopped` | boolean | Show only stopped agents (alias for --include 'state == "STOPPED"') | `False` |
| `--local` | boolean | Show only local agents (alias for --include 'host.provider == "local"') | `False` |
| `--remote` | boolean | Show only remote agents (alias for --exclude 'host.provider == "local"') | `False` |
| `--provider` | text | Show only agents using specified provider (repeatable) | None |
| `--stdin` | boolean | Read agent and host IDs or names from stdin (one per line) | `False` |

## Output Format

| Name | Type | Description | Default |
| ---- | ---- | ----------- | ------- |
| `--format-template` | text | Output format as a string template (mutually exclusive with --format) [future] | None |
| `--fields` | text | Which fields to include (comma-separated) | None |
| `--sort` | text | Sort by field (supports nested fields like host.name) [default: create_time] | `create_time` |
| `--sort-order` | choice (`asc` &#x7C; `desc`) | Sort order [default: asc] | `asc` |
| `--limit` | integer | Limit number of results (applied after fetching from all providers) | None |

## Watch Mode

| Name | Type | Description | Default |
| ---- | ---- | ----------- | ------- |
| `-w`, `--watch` | integer | Continuously watch and update status at specified interval (seconds) | None |

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
- `state == "RUNNING"` - Match running agents
- `host.provider == "docker"` - Match agents on Docker hosts
- `type == "claude"` - Match agents of type "claude"

**Compound expressions:**
- `state == "RUNNING" && host.provider == "modal"` - Running agents on Modal
- `state == "STOPPED" || state == "FAILED"` - Stopped or failed agents
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
- `state` - Agent lifecycle state (RUNNING, STOPPED, WAITING, REPLACED, DONE)
- `plugin.$PLUGIN_NAME.*` - Plugin-defined fields (e.g., `plugin.chat_history.messages`)

**Host fields** (dot notation for both `--fields` and CEL filters):
- `host.name` - Host name
- `host.id` - Host ID
- `host.host` - Hostname where the host is running (ssh.host for remote, localhost for local)
- `host.provider` - Host provider (local, docker, modal, etc.)
- `host.state` - Current host state (RUNNING, STOPPED, BUILDING, etc.)
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
---


---

# mngr open [future] - CLI Options Reference

Opens a URL associated with an agent in a web browser.

Agents can have a variety of different URLs associated with them. If the URL type is unspecified (and there is more than one URL), this command opens a little TUI that lets you pick from the available URLs.

Use `mngr connect` to attach to an agent via the terminal instead.

## Usage

```
mngr open [[--agent] AGENT] [[--type] URL_TYPE]
```

The agent and url type can be specified as positional arguments for convenience. The following are equivalent:

```
mngr open my-agent terminal
mngr open --agent my-agent --type terminal
```

## General

- `--agent AGENT`: The agent to open. A positional argument is also accepted as a shorthand. If not specified, opens the most recently created agent.
- `-t, --type URL_TYPE`: The type of URL to open (e.g., `chat`, `terminal`, `diff`, etc.). If not specified, and there are multiple URL types, a TUI will be shown to select from the available URLs.
- `--[no-]start`: Automatically start the agent if it is currently stopped [default: start]

## Options

- `--[no-]wait`: Wait for the browser to be closed before exiting [default: no-wait]
- `--active`: Continually update the active timestamp while connected (prevents idle shutdown). Only makes sense with `--wait`
---


---

<!-- This file is auto-generated. Do not edit directly. -->
<!-- To modify, edit the command's help metadata and run: uv run python scripts/make_cli_docs.py -->

# mngr pair

**Synopsis:**

```text
mngr pair [SOURCE] [--target <DIR>] [--sync-direction <DIR>] [--conflict <MODE>]
```


Continuously sync files between an agent and local directory.

This command establishes a bidirectional file sync between an agent's working
directory and a local directory. Changes are watched and synced in real-time.

If git repositories exist on both sides, the command first synchronizes git
state (branches and commits) before starting the continuous file sync.

Press Ctrl+C to stop the sync.

During rapid concurrent edits, changes will be debounced to avoid partial
writes [future].

Examples:
  mngr pair my-agent
  mngr pair my-agent --target ./local-dir
  mngr pair --source-agent my-agent --target ./local-copy
  mngr pair my-agent --sync-direction=forward
  mngr pair my-agent --conflict=source
  mngr pair my-agent --source-host @local

**Usage:**

```text
mngr pair [OPTIONS] SOURCE
```

## Arguments

- `SOURCE`: The source (optional)

**Options:**

## Source Selection

| Name | Type | Description | Default |
| ---- | ---- | ----------- | ------- |
| `--source` | text | Source specification: AGENT, AGENT:PATH, or PATH | None |
| `--source-agent` | text | Source agent name or ID | None |
| `--source-host` | text | Source host name or ID | None |
| `--source-path` | text | Path within the agent's work directory | None |

## Target

| Name | Type | Description | Default |
| ---- | ---- | ----------- | ------- |
| `--target` | path | Local target directory [default: nearest git root or current directory] | None |

## Git Handling

| Name | Type | Description | Default |
| ---- | ---- | ----------- | ------- |
| `--require-git`, `--no-require-git` | boolean | Require that both source and target are git repositories [default: require git] | `True` |
| `--uncommitted-changes` | choice (`stash` &#x7C; `clobber` &#x7C; `merge` &#x7C; `fail`) | How to handle uncommitted changes during initial git sync. The initial sync aborts immediately if unresolved conflicts exist, regardless of this setting. | `fail` |

## Sync Behavior

| Name | Type | Description | Default |
| ---- | ---- | ----------- | ------- |
| `--sync-direction` | choice (`both` &#x7C; `forward` &#x7C; `reverse`) | Sync direction: both (bidirectional), forward (source->target), reverse (target->source) | `both` |
| `--conflict` | choice (`newer` &#x7C; `source` &#x7C; `target` &#x7C; `ask`) | Conflict resolution mode (only matters for bidirectional sync). 'newer' prefers the file with the more recent modification time (uses unison's -prefer newer; note that clock skew between machines can cause incorrect results). 'source' and 'target' always prefer that side. 'ask' prompts interactively [future]. | `newer` |

## File Filtering

| Name | Type | Description | Default |
| ---- | ---- | ----------- | ------- |
| `--include` | text | Include files matching glob pattern [repeatable] | None |
| `--exclude` | text | Exclude files matching glob pattern [repeatable] | None |

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

- [mngr push](./push.md) - Push files or git commits to an agent
- [mngr pull](./pull.md) - Pull files or git commits from an agent
- [mngr create](./create.md) - Create a new agent
- [mngr list](./list.md) - List agents to find one to pair with

## Examples

**Pair with an agent**

```bash
$ mngr pair my-agent
```

**Pair to specific local directory**

```bash
$ mngr pair my-agent --target ./local-dir
```

**One-way sync (source to target)**

```bash
$ mngr pair my-agent --sync-direction=forward
```

**Prefer source on conflicts**

```bash
$ mngr pair my-agent --conflict=source
```

**Filter to specific host**

```bash
$ mngr pair my-agent --source-host @local
```
---


---

<!-- This file is auto-generated. Do not edit directly. -->
<!-- To modify, edit the command's help metadata and run: uv run python scripts/make_cli_docs.py -->

# mngr pull

**Synopsis:**

```text
mngr pull [SOURCE] [DESTINATION] [--source-agent <AGENT>] [--dry-run] [--stop]
```


Pull files or git commits from an agent to local machine.

Syncs files or git state from an agent's working directory to a local directory.
Default behavior uses rsync for efficient incremental file transfer.
Use --sync-mode=git to merge git branches instead of syncing files.

If no source is specified, shows an interactive selector to choose an agent.

Examples:
  mngr pull my-agent
  mngr pull my-agent ./local-copy
  mngr pull my-agent:src ./local-src
  mngr pull --source-agent my-agent
  mngr pull my-agent --sync-mode=git
  mngr pull my-agent --sync-mode=git --target-branch=main

**Usage:**

```text
mngr pull [OPTIONS] SOURCE DESTINATION
```

## Arguments

- `SOURCE`: The source (optional)
- `DESTINATION`: The destination (optional)

**Options:**

## Source Selection

| Name | Type | Description | Default |
| ---- | ---- | ----------- | ------- |
| `--source` | text | Source specification: AGENT, AGENT:PATH, or PATH | None |
| `--source-agent` | text | Source agent name or ID | None |
| `--source-host` | text | Source host name or ID [future] | None |
| `--source-path` | text | Path within the agent's work directory | None |

## Destination

| Name | Type | Description | Default |
| ---- | ---- | ----------- | ------- |
| `--destination` | path | Local destination directory [default: .] | None |

## Sync Options

| Name | Type | Description | Default |
| ---- | ---- | ----------- | ------- |
| `--dry-run` | boolean | Show what would be transferred without actually transferring | `False` |
| `--stop` | boolean | Stop the agent after pulling (for state consistency) | `False` |
| `--delete`, `--no-delete` | boolean | Delete files in destination that don't exist in source | `False` |
| `--sync-mode` | choice (`files` &#x7C; `git` &#x7C; `full`) | What to sync: files (working directory via rsync), git (merge git branches), or full (everything) [future] | `files` |
| `--exclude` | text | Patterns to exclude from sync [repeatable] [future] | None |

## Target (for agent-to-agent sync)

| Name | Type | Description | Default |
| ---- | ---- | ----------- | ------- |
| `--target` | text | Target specification: AGENT, AGENT.HOST, AGENT.HOST:PATH, or HOST:PATH [future] | None |
| `--target-agent` | text | Target agent name or ID [future] | None |
| `--target-host` | text | Target host name or ID [future] | None |
| `--target-path` | text | Path within target to sync to [future] | None |

## Multi-source

| Name | Type | Description | Default |
| ---- | ---- | ----------- | ------- |
| `--stdin` | boolean | Read source agents/hosts from stdin, one per line [future] | `False` |

## File Filtering

| Name | Type | Description | Default |
| ---- | ---- | ----------- | ------- |
| `--include` | text | Include files matching glob pattern [repeatable] [future] | None |
| `--include-gitignored` | boolean | Include files that match .gitignore patterns [future] | `False` |
| `--include-file` | path | Read include patterns from file [future] | None |
| `--exclude-file` | path | Read exclude patterns from file [future] | None |

## Rsync Options

| Name | Type | Description | Default |
| ---- | ---- | ----------- | ------- |
| `--rsync-arg` | text | Additional argument to pass to rsync [repeatable] [future] | None |
| `--rsync-args` | text | Additional arguments to pass to rsync (as a single string) [future] | None |

## Git Sync Options

| Name | Type | Description | Default |
| ---- | ---- | ----------- | ------- |
| `--branch` | text | Pull a specific branch [repeatable] [future] | None |
| `--target-branch` | text | Branch to merge into (git mode only) [default: current branch] | None |
| `--all-branches`, `--all` | boolean | Pull all remote branches [future] | `False` |
| `--tags` | boolean | Include git tags in sync [future] | `False` |
| `--force-git` | boolean | Force overwrite local git state (use with caution) [future]. Without this flag, the command fails if local and remote history have diverged (e.g. after a force-push) and the user must resolve manually. | `False` |
| `--merge` | boolean | Merge remote changes with local changes [future] | `False` |
| `--rebase` | boolean | Rebase local changes onto remote changes [future] | `False` |
| `--uncommitted-source` | choice (`warn` &#x7C; `error`) | Warn or error if source has uncommitted changes [future] | None |
| `--uncommitted-changes` | choice (`stash` &#x7C; `clobber` &#x7C; `merge` &#x7C; `fail`) | How to handle uncommitted changes in the destination: stash (stash and leave stashed), clobber (overwrite), merge (stash, pull, unstash), fail (error if changes exist) | `fail` |

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

## Multi-target Behavior

See [multi_target](../generic/multi_target.md) for options controlling behavior when some agents cannot be processed.

## See Also

- [mngr create](./create.md) - Create a new agent
- [mngr list](./list.md) - List agents to find one to pull from
- [mngr connect](./connect.md) - Connect to an agent interactively
- [mngr push](./push.md) - Push files or git commits to an agent

## Examples

**Pull from agent to current directory**

```bash
$ mngr pull my-agent
```

**Pull to specific local directory**

```bash
$ mngr pull my-agent ./local-copy
```

**Pull specific subdirectory**

```bash
$ mngr pull my-agent:src ./local-src
```

**Preview what would be transferred**

```bash
$ mngr pull my-agent --dry-run
```

**Pull git commits**

```bash
$ mngr pull my-agent --sync-mode=git
```
---


---

<!-- This file is auto-generated. Do not edit directly. -->
<!-- To modify, edit the command's help metadata and run: uv run python scripts/make_cli_docs.py -->

# mngr push

**Synopsis:**

```text
mngr push [TARGET] [SOURCE] [--target-agent <AGENT>] [--dry-run] [--stop]
```


Push files or git commits from local machine to an agent.

Syncs files or git state from a local directory to an agent's working directory.
Default behavior uses rsync for efficient incremental file transfer.
Use --sync-mode=git to push git branches instead of syncing files.

If no target is specified, shows an interactive selector to choose an agent.

IMPORTANT: The source (host) workspace is never modified. Only the target
(agent workspace) may be modified.

Examples:
  mngr push my-agent
  mngr push my-agent ./local-dir
  mngr push my-agent:subdir ./local-src
  mngr push my-agent --source ./local-dir
  mngr push my-agent --sync-mode=git
  mngr push my-agent --sync-mode=git --mirror

**Usage:**

```text
mngr push [OPTIONS] TARGET SOURCE
```

## Arguments

- `TARGET`: The target (optional)
- `SOURCE`: The source (optional)

**Options:**

## Target Selection

| Name | Type | Description | Default |
| ---- | ---- | ----------- | ------- |
| `--target` | text | Target specification: AGENT, AGENT:PATH, or PATH | None |
| `--target-agent` | text | Target agent name or ID | None |
| `--target-host` | text | Target host name or ID [future] | None |
| `--target-path` | text | Path within the agent's work directory | None |

## Source

| Name | Type | Description | Default |
| ---- | ---- | ----------- | ------- |
| `--source` | path | Local source directory [default: .] | None |

## Sync Options

| Name | Type | Description | Default |
| ---- | ---- | ----------- | ------- |
| `--dry-run` | boolean | Show what would be transferred without actually transferring | `False` |
| `--stop` | boolean | Stop the agent after pushing (for state consistency) | `False` |
| `--delete`, `--no-delete` | boolean | Delete files in destination that don't exist in source | `False` |
| `--sync-mode` | choice (`files` &#x7C; `git` &#x7C; `full`) | What to sync: files (working directory via rsync), git (push git branches), or full (everything) [future] | `files` |
| `--exclude` | text | Patterns to exclude from sync [repeatable] [future] | None |
| `--source-branch` | text | Branch to push from (git mode only) [default: current branch] | None |
| `--uncommitted-changes` | choice (`stash` &#x7C; `clobber` &#x7C; `merge` &#x7C; `fail`) | How to handle uncommitted changes in the agent workspace: stash (stash and leave stashed), clobber (overwrite), merge (stash, push, unstash), fail (error if changes exist) | `fail` |

## Git Options

| Name | Type | Description | Default |
| ---- | ---- | ----------- | ------- |
| `--mirror` | boolean | Force the agent's git state to match the source, overwriting all refs (branches, tags) and resetting the working tree (dangerous). Any commits or branches that exist only in the agent will be lost. Only applies to --sync-mode=git. Required when the agent and source have diverged (non-fast-forward). For remote agents, uses git push --mirror [future]. | `False` |
| `--rsync-only` | boolean | Use rsync even if git is available in both source and destination | `False` |

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

- [mngr create](./create.md) - Create a new agent
- [mngr list](./list.md) - List agents to find one to push to
- [mngr pull](./pull.md) - Pull files or git commits from an agent
- [mngr pair](./pair.md) - Continuously sync files between agent and local

## Examples

**Push to agent from current directory**

```bash
$ mngr push my-agent
```

**Push from specific local directory**

```bash
$ mngr push my-agent ./local-dir
```

**Push to specific subdirectory**

```bash
$ mngr push my-agent:subdir ./local-src
```

**Preview what would be transferred**

```bash
$ mngr push my-agent --dry-run
```

**Push git commits**

```bash
$ mngr push my-agent --sync-mode=git
```

**Mirror all refs to agent**

```bash
$ mngr push my-agent --sync-mode=git --mirror
```
---


---

# mngr rename [future] - CLI Options Reference

Rename an agent or host.

If an in-progress rename failed, will attempt to finish it.

## Usage

```
mngr rename <current> <new-name>
```

## Arguments

- `current`: Current name or ID of the agent/host to rename
- `new-name`: New name for the agent/host

## Options

- `--dry-run`: Show what would be renamed without actually renaming
---


---

# mngr start - CLI Options Reference

Starts one or more stopped agents.

For remote hosts, this restores from the most recent snapshot and starts the container/instance. If multiple agents share the host, they will be started if their "start on boot" bit is set (when specifying a host to start), or if they are specified directly (e.g., when specifying an agent to start).

## Usage

```
mngr start [[--agent] AGENT ...]
```

Agent IDs can be specified as positional arguments for convenience. The following are equivalent:

```
mngr start my-agent
mngr start --agent my-agent
mngr start my-agent another-agent
mngr start --agent my-agent --agent another-agent
```

## General

- `--agent AGENT`: Agent(s) to start. Positional arguments are also accepted as a shorthand. [repeatable]
- `--host HOST`: Host(s) to start all stopped agents on [repeatable]
- `-a, --all, --all-agents`: Start all stopped agents.
- `--include FILTER`: Filter agents and hosts to start by tags, names, types, hosts, etc.
- `--exclude FILTER`: Exclude agents and hosts matching filter from starting
- `--stdin`: Read agents and hosts (ids or names) from stdin (one per line)
- `--dry-run`: Show what would be started without actually starting

## Single agent mode

- `--[no-]connect`: Connect to the agent after starting. Only makes sense to connect if there is a single agent [default: no connect]
- `--snapshot SNAPSHOT_ID`: Start from a specific snapshot instead of the most recent
- `--latest`: Start from the most recent snapshot or state [default]

## Connection Options

See [connect options](./connect.md) (only applies if `--connect` is specified)
---


---

# mngr stop - CLI Options Reference

Stops the host(s) associated with one or more running agents. The agent(s) can be started again later with `mngr start`.

For remote hosts, this creates a snapshot and stops the container/instance to save resources. If multiple agents share the host, all agents on that host are stopped together.

For local agents, this stops the agent's tmux session. The local host itself cannot be stopped (if you want that, shut down your computer).

**Alias:** `s`

## Usage

```
mngr stop [[--agent] agent ...]
```

Agents can be specified as positional arguments for convenience. The following are equivalent:

```
mngr stop my-agent
mngr stop --agent my-agent
mngr stop my-agent another-agent
mngr stop --agent my-agent --agent another-agent
```

## General

- `--agent AGENT`: Agent(s) to stop. Positional arguments are also accepted as a shorthand. [repeatable]
- `-a, --all, --all-agents`: Stop all running agents
- `--include FILTER`: Filter agents to stop by tags, names, types, hosts, etc.
- `--exclude FILTER`: Exclude agents matching filter from stopping
- `--stdin`: Read agents and hosts (ids or names) from stdin (one per line)
- `--dry-run`: Show what would be stopped without actually stopping

## Snapshot Behavior

- `--snapshot-mode MODE`: Control snapshot creation when stopping [choices: `auto`, `always`, `never`; default: `auto`]
  - `auto`: Create a snapshot if necessary to save the agent's state
  - `always`: Always create a snapshot, even if not strictly necessary
  - `never`: Do not create a snapshot (faster, but state may be lost)

## Behavior

- `--[no-]graceful`: Wait for agent to reach a clean state (finish processing messages) before stopping [default: graceful]
- `--graceful-timeout DURATION`: Timeout for graceful stop (e.g., `30s`, `5m`) [default: 30s]
---


---

<!-- This file is auto-generated. Do not edit directly. -->
<!-- To modify, edit the command's help metadata and run: uv run python scripts/make_cli_docs.py -->

# mngr ask

**Synopsis:**

```text
mngr ask [--execute] QUERY...
```


Chat with mngr for help.

Ask mngr a question and it will generate the appropriate CLI command.
If no query is provided, shows general help.

Examples:

  mngr ask "how do I create an agent?"

  mngr ask start a container with claude code

  mngr ask --execute forward port 8080 to the public internet

**Usage:**

```text
mngr ask [OPTIONS] [QUERY]...
```

## Arguments

- `QUERY`: The query (optional)

**Options:**

## Behavior

| Name | Type | Description | Default |
| ---- | ---- | ----------- | ------- |
| `--execute` | boolean | Execute the generated CLI command instead of just printing it | `False` |

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

- [mngr create](../primary/create.md) - Create an agent
- [mngr list](../primary/list.md) - List existing agents
- [mngr connect](../primary/connect.md) - Connect to an agent

## Examples

**Ask a question**

```bash
$ mngr ask "how do I create an agent?"
```

**Ask without quotes**

```bash
$ mngr ask start a container with claude code
```

**Execute the generated command**

```bash
$ mngr ask --execute forward port 8080 to the public internet
```
---


---

# mngr cleanup [future] - CLI Options Reference

Destroy or stop agents and hosts in order to free up resources.

When running in a pty, defaults to providing an interactive interface for reviewing running agents and hosts and selecting which ones to destroy or stop.

When running in a non-interactive setting (or if `--yes` or `--no-interactive` is provided), will destroy all selected agents/hosts without prompting.

For automatic garbage collection of unused resources without interaction, see `mngr gc`.

**Alias:** `clean`

## Usage

```
mngr cleanup
```

## General

- `-f, --force, --yes`: Skip confirmation prompts
- `--dry-run`: Show what would be destroyed or stopped without executing

## Filtering

- `--include FILTER`: Include only agents/hosts matching this filter
- `--exclude FILTER`: Exclude agents/hosts matching this filter
- `--older-than DURATION`: Select agents/hosts older than specified (e.g., `7d`, `24h`)
- `--idle-for DURATION`: Select agents idle for at least this duration
- `--tag TAG`: Select agents/hosts with this tag [repeatable]
- `--provider PROVIDER`: Select hosts from this provider [repeatable]
- `--agent-type AGENT`: Select this agent type (e.g., `claude`, `codex`) [repeatable]

## Actions

- `--destroy`: Destroy selected agents/hosts (default)
- `--stop`: Stop selected agents/hosts instead of destroying
- `--snapshot-before`: Create snapshots before destroying or stopping. When destroying, only makes sense with --keep-snapshots

## Resource Cleanup

See [resource cleanup options](../generic/resource_cleanup.md) to control which associated resources are also destroyed (defaults to all).
---


---

<!-- This file is auto-generated. Do not edit directly. -->
<!-- To modify, edit the command's help metadata and run: uv run python scripts/make_cli_docs.py -->

# mngr config

**Synopsis:**

```text
mngr [config|cfg] <subcommand> [OPTIONS]
```


Manage mngr configuration.

View, edit, and modify mngr configuration settings at the user, project,
or local scope.

Examples:

  mngr config list

  mngr config get prefix

  mngr config set --scope project commands.create.connect false

  mngr config unset commands.create.connect

  mngr config edit --scope user

**Usage:**

```text
mngr config [OPTIONS] COMMAND [ARGS]...
```

**Options:**

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
| `--scope` | choice (`user` &#x7C; `project` &#x7C; `local`) | Config scope: user (~/.mngr/profiles/<profile_id>/), project (.mngr/), or local (.mngr/settings.local.toml) | None |

## mngr config list

List all configuration values.

Shows all configuration settings from the specified scope, or from the
merged configuration if no scope is specified.

Examples:

  mngr config list

  mngr config list --scope user

  mngr config list --format json

**Usage:**

```text
mngr config list [OPTIONS]
```

**Options:**

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
| `--scope` | choice (`user` &#x7C; `project` &#x7C; `local`) | Config scope: user (~/.mngr/profiles/<profile_id>/), project (.mngr/), or local (.mngr/settings.local.toml) | None |

## mngr config get

Get a configuration value.

Retrieves the value of a specific configuration key. Use dot notation
for nested keys (e.g., 'commands.create.connect').

Examples:

  mngr config get prefix

  mngr config get commands.create.connect

  mngr config get logging.console_level --scope user

**Usage:**

```text
mngr config get [OPTIONS] KEY
```

**Options:**

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
| `--scope` | choice (`user` &#x7C; `project` &#x7C; `local`) | Config scope: user (~/.mngr/profiles/<profile_id>/), project (.mngr/), or local (.mngr/settings.local.toml) | None |

## mngr config set

Set a configuration value.

Sets a configuration value at the specified scope. Use dot notation
for nested keys (e.g., 'commands.create.connect').

Values are parsed as JSON if possible, otherwise as strings.
Use 'true'/'false' for booleans, numbers for integers/floats.

Examples:

  mngr config set prefix "my-"

  mngr config set commands.create.connect false

  mngr config set logging.console_level DEBUG --scope user

**Usage:**

```text
mngr config set [OPTIONS] KEY VALUE
```

**Options:**

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
| `--scope` | choice (`user` &#x7C; `project` &#x7C; `local`) | Config scope: user (~/.mngr/profiles/<profile_id>/), project (.mngr/), or local (.mngr/settings.local.toml) | `project` |

## mngr config unset

Remove a configuration value.

Removes a configuration value from the specified scope. Use dot notation
for nested keys (e.g., 'commands.create.connect').

Examples:

  mngr config unset commands.create.connect

  mngr config unset logging.console_level --scope user

**Usage:**

```text
mngr config unset [OPTIONS] KEY
```

**Options:**

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
| `--scope` | choice (`user` &#x7C; `project` &#x7C; `local`) | Config scope: user (~/.mngr/profiles/<profile_id>/), project (.mngr/), or local (.mngr/settings.local.toml) | `project` |

## mngr config edit

Open configuration file in editor.

Opens the configuration file for the specified scope in your default
editor (from $EDITOR or $VISUAL environment variable, or 'vi' as fallback).

If the config file doesn't exist, it will be created with an empty template.

Examples:

  mngr config edit

  mngr config edit --scope user

  mngr config edit --scope local

**Usage:**

```text
mngr config edit [OPTIONS]
```

**Options:**

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
| `--scope` | choice (`user` &#x7C; `project` &#x7C; `local`) | Config scope: user (~/.mngr/profiles/<profile_id>/), project (.mngr/), or local (.mngr/settings.local.toml) | `project` |

## mngr config path

Show configuration file paths.

Shows the paths to configuration files. If --scope is specified, shows
only that scope's path. Otherwise shows all paths and whether they exist.

Examples:

  mngr config path

  mngr config path --scope user

**Usage:**

```text
mngr config path [OPTIONS]
```

**Options:**

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
| `--scope` | choice (`user` &#x7C; `project` &#x7C; `local`) | Config scope: user (~/.mngr/profiles/<profile_id>/), project (.mngr/), or local (.mngr/settings.local.toml) | None |

## See Also

- [mngr create](../primary/create.md) - Create a new agent with configuration

## Examples

**List all configuration values**

```bash
$ mngr config list
```

**Get a specific value**

```bash
$ mngr config get provider.docker.image
```

**Set a value at user scope**

```bash
$ mngr config set --user provider.docker.image my-image:latest
```

**Edit config in your editor**

```bash
$ mngr config edit
```

**Show config file paths**

```bash
$ mngr config path
```
---


---

# mngr enforce [future] - CLI Options Reference

Ensure that no hosts have exceeded their idle timeouts, etc.

In order to ensure that *untrusted* hosts cannot exceed their idle timeout, this command must be periodically.
It also helps ensure that no hosts have become stuck during state transitions (building, starting, stopping, etc.)

This command should be run from a single location, and should be aware of *all* valid state signing keys.

## Usage

```
mngr enforce
```

## General

- `--[no-]check-idle`: Check for hosts that have exceeded their timeouts [default: check-idle]
- `--[no-]check-timeouts`: Check for hosts that have exceeded their timeouts for some (transitory) state. See the config for more details. [default: check-timeouts]
- `-w, --watch SECONDS`: Re-run enforcement checks at the specified interval
---


---

<!-- This file is auto-generated. Do not edit directly. -->
<!-- To modify, edit the command's help metadata and run: uv run python scripts/make_cli_docs.py -->

# mngr gc

**Synopsis:**

```text
mngr gc [OPTIONS]
```


Garbage collect unused resources.

Automatically removes unused resources from providers and mngr itself.

Examples:

  mngr gc --work-dirs --dry-run

  mngr gc --all-agent-resources

  mngr gc --machines --snapshots --provider docker

  mngr gc --logs --build-cache

**Usage:**

```text
mngr gc [OPTIONS]
```

**Options:**

## What to Clean - Agent Resources

| Name | Type | Description | Default |
| ---- | ---- | ----------- | ------- |
| `--all-agent-resources` | boolean | Clean all agent resource types (machines, snapshots, volumes, work dirs) | `False` |
| `--machines` | boolean | Remove unused containers, instances, and sandboxes | `False` |
| `--snapshots` | boolean | Remove unused snapshots | `False` |
| `--volumes` | boolean | Remove unused volumes | `False` |
| `--work-dirs` | boolean | Remove work directories (git worktrees/clones) not in use by any agent | `False` |

## What to Clean - Mngr Resources

| Name | Type | Description | Default |
| ---- | ---- | ----------- | ------- |
| `--logs` | boolean | Remove log files from destroyed agents/hosts | `False` |
| `--build-cache` | boolean | Remove build cache entries | `False` |
| `--machine-cache` | boolean | Remove machine cache entries (per-provider) [future] | `False` |

## Filtering

| Name | Type | Description | Default |
| ---- | ---- | ----------- | ------- |
| `--include` | text | Only clean resources matching CEL filter (repeatable) | None |
| `--exclude` | text | Exclude resources matching CEL filter (repeatable) | None |

## Scope

| Name | Type | Description | Default |
| ---- | ---- | ----------- | ------- |
| `--all-providers` | boolean | Clean resources across all providers | `False` |
| `--provider` | text | Clean resources for a specific provider (repeatable) | None |

## Safety

| Name | Type | Description | Default |
| ---- | ---- | ----------- | ------- |
| `--dry-run` | boolean | Show what would be cleaned without actually cleaning | `False` |
| `--on-error` | choice (`abort` &#x7C; `continue`) | What to do when errors occur: abort (stop immediately) or continue (keep going) | `abort` |
| `-w`, `--watch` | integer | Re-run garbage collection at the specified interval (seconds) | None |

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

CEL filters let you control which resources are cleaned.

**For snapshots, use `recency_idx` to filter by age:**
- `recency_idx == 0` - the most recent snapshot
- `recency_idx < 5` - the 5 most recent snapshots
- To keep only the 5 most recent: `--exclude "recency_idx < 5"`

**Filter by resource properties:**
- `name.contains("test")` - resources with "test" in the name
- `provider_name == "docker"` - Docker resources only


## See Also

- [mngr destroy](../primary/destroy.md) - Destroy agents (includes automatic GC)
- [mngr list](../primary/list.md) - List agents to find unused resources

## Examples

**Preview what would be cleaned (dry run)**

```bash
$ mngr gc --work-dirs --dry-run
```

**Clean all agent resources**

```bash
$ mngr gc --all-agent-resources
```

**Clean machines and snapshots for Docker**

```bash
$ mngr gc --machines --snapshots --provider docker
```

**Clean logs and build cache**

```bash
$ mngr gc --logs --build-cache
```

**Keep only the 5 most recent snapshots**

```bash
$ mngr gc --snapshots --exclude "recency_idx < 5"
```
---


---

# mngr limit [future] - CLI Options Reference

Configure limits for agents and hosts: idle timeout, permissions, port forwarding, etc.

Agents effectively have permissions that are equivalent to the *union* of all permissions on the same host.

Changing permissions for agents requires them to be restarted.

Changes to some limits for hosts (e.g. CPU, RAM, disk space, network, etc.) are handled by the provider.

**Alias:** `lim`

## Usage

```
mngr limit [[--agent] AGENT ...] [options]
```

Agent IDs can be specified as positional arguments for convenience. The following are equivalent:

```
mngr limit my-agent --idle-timeout 30m
mngr limit --agent my-agent --idle-timeout 30m
mngr limit my-agent another-agent --idle-timeout 30m
mngr limit --agent my-agent --agent another-agent --idle-timeout 30m
```

## General

- `--agent AGENT`: Agent(s) to configure. Positional arguments are also accepted as a shorthand. [repeatable]
- `--host HOST`: Host(s) to configure. [repeatable]
- `-a, --all, --all-agents`: Apply limits to all agents
- `--include FILTER`: Filter agents to configure by tags, names, types, hosts, etc.
- `--exclude FILTER`: Exclude agents matching filter from configuration
- `--stdin`: Read agents and hosts (ids or names) from stdin (one per line)
- `--dry-run`: Show what limits would be changed without actually changing them

## Lifecycle

- `--[no-]start-on-boot`: Automatically restart agent when host restarts. When adding the persist bit to a local agent, you may be prompted to install the post-boot-handler [default: no-persist for local, persist otherwise]
- `--idle-timeout DURATION`: Shutdown after idle for specified duration (e.g., `30s`, `5m`, `1h`)
- `--idle-mode MODE`: When to consider host idle [default: `io` (remote) or `disabled` (local), choices: `io`, `user`, `agent`, `ssh`, `create`, `boot`, `start`, `run`, `disabled`]
- `--activity-sources SOURCES`: Set activity sources for idle detection (comma-separated). Available sources: `create`, `boot`, `start`, `ssh`, `process`, `agent`, `user` [default: everything except process]
- `--add-activity-source SOURCE`: Add an activity source for idle detection [repeatable]
- `--remove-activity-source SOURCE`: Remove an activity source from idle detection [repeatable]

**Idle modes:**
- `io` - Time since there was any activity (user, agent, ssh, etc.)
- `user` - Time since the last user input or SSH activity
- `agent` - Time since the last agent output or SSH activity
- `ssh` - Time since an SSH connection was last active
- `create` - Time since the agent was created
- `boot` - Time since the host was booted
- `start` - Time since the agent was started
- `run` - Time since the agent process exited
- `disabled` - Never automatically idle (manual shutdown only)

## Permissions

- `--grant PERMISSION`: Grant a permission to the agent [repeatable]
- `--revoke PERMISSION`: Revoke a permission from the agent [repeatable]

## SSH Keys

- `--refresh-ssh-keys`: Refresh the SSH keys for the host
- `--add-ssh-key FILE`: Add an SSH public key to the host for access [repeatable]
- `--remove-ssh-key FILE`: Remove an SSH public key from the host [repeatable]
---


---

<!-- This file is auto-generated. Do not edit directly. -->
<!-- To modify, edit the command's help metadata and run: uv run python scripts/make_cli_docs.py -->

# mngr message

**Synopsis:**

```text
mngr [message|msg] [AGENTS...] [--agent <AGENT>] [--all] [-m <MESSAGE>]
```


Send a message to one or more agents.

Agent IDs can be specified as positional arguments for convenience.
The message is sent to the agent's stdin.

If no message is specified with --message, reads from stdin (if not a tty)
or opens an editor (if interactive).

Examples:

  mngr message my-agent --message "Hello"

  mngr message agent1 agent2 --message "Hello to all"

  mngr message --agent my-agent --agent another-agent --message "Hello"

  mngr message --all --message "Hello everyone"

  echo "Hello" | mngr message my-agent

**Usage:**

```text
mngr message [OPTIONS] [AGENTS]...
```

## Arguments

- `AGENTS`: The agents (optional)

**Options:**

## Target Selection

| Name | Type | Description | Default |
| ---- | ---- | ----------- | ------- |
| `--agent` | text | Agent name or ID to send message to (can be specified multiple times) | None |
| `-a`, `--all`, `--all-agents` | boolean | Send message to all agents | `False` |
| `--include` | text | Include agents matching CEL expression (repeatable) | None |
| `--exclude` | text | Exclude agents matching CEL expression (repeatable) | None |
| `--stdin` | boolean | Read agent and host IDs or names from stdin (one per line) | `False` |

## Message Content

| Name | Type | Description | Default |
| ---- | ---- | ----------- | ------- |
| `-m`, `--message` | text | The message content to send | None |

## Error Handling

| Name | Type | Description | Default |
| ---- | ---- | ----------- | ------- |
| `--on-error` | choice (`abort` &#x7C; `continue`) | What to do when errors occur: abort (stop immediately) or continue (keep going) | `continue` |

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

## Related Documentation

- [Multi-target Options](../generic/multi_target.md) - Behavior when some agents fail to receive the message

## See Also

- [mngr connect](../primary/connect.md) - Connect to an agent interactively
- [mngr list](../primary/list.md) - List available agents

## Examples

**Send a message to an agent**

```bash
$ mngr message my-agent --message "Hello"
```

**Send to multiple agents**

```bash
$ mngr message agent1 agent2 --message "Hello to all"
```

**Send to all agents**

```bash
$ mngr message --all --message "Hello everyone"
```

**Pipe message from stdin**

```bash
$ echo "Hello" | mngr message my-agent
```
---


---

# mngr plugin [future] - CLI Options Reference

Manage available and active plugins.

Right now, only `list` is implemented; other commands are placeholders for future functionality.

**Alias:** `plug`

## Usage

```
mngr plugin [ls|list|add|rm|remove|enable|disable] [options]
```

## General

- `--all`: Select all available plugins [default]
- `--active`: Select only currently enabled plugins

## ls, list

- `--format FORMAT`: Output format [default: `human`, choices: `human`, `json`, `jsonl`]. Mutually exclusive with `--json` and `--jsonl` (see [common options](../generic/common.md))
- `--fields FIELDS`: Which fields to include (comma-separated). Available: `name`, `version`, `description`, `enabled`
---


---

# mngr provision [future] - CLI Options Reference

Ensures that an agent has the required packages, libraries, environment variables, and configuration files to run properly.

These are mostly specified via plugins, but custom provisioning steps can also be defined using the options below.

Provisioning is done per agent, but obviously any changes from one agent will be visible to other agents on the same host.
Be careful to avoid conflicts when provisioning multiple agents on the same host.

**Alias:** `prov`

## Usage

```
mngr provision [[--agent] agent]
```

## General

- `--bootstrap / --bootstrap-and-warn / --no-bootstrap` [future]: Whether to auto-install any required tools that are missing [default: `--bootstrap-and-warn` on remote hosts, `--no-bootstrap` on local]
- `--[no-]destroy-on-fail` [future]: Destroy the host if provisioning fails [default: no]

## Simple configuration

- `--user-command TEXT`: Run a custom shell command during provisioning [repeatable]
- `--sudo-command TEXT`: Run a custom shell command during provisioning as root [repeatable]
- `--upload-file LOCAL:REMOTE`: Upload a local file to the agent at the specified remote path [repeatable]
- `--env KEY=VALUE`: Set an environment variable KEY=VALUE on the agent [repeatable]
- `--pass-env KEY`: Forward an environment variable from your current shell to the agent [repeatable]
- `--append-to-file REMOTE:TEXT`: Append TEXT to a file on the agent at the specified remote path [repeatable]
- `--prepend-to-file REMOTE:TEXT`: Prepend TEXT to a file on the agent at the specified remote path [repeatable]
- `--create-directory REMOTE`: Create a directory on the agent at the specified remote path [repeatable]
---


---

# mngr snapshot [future] - CLI Options Reference

Create, destroy, and list snapshots of agents.

Snapshots capture the complete state of the agent's host, allowing it to be restored later. Because the snapshot includes the filesystem, the state of all agents on the host will be saved. 

Useful for checkpointing work, creating restore points, or managing disk space.

**Alias:** `snap`

## Usage

```
mngr snapshot [create|list|destroy] [args]
```

See [multi-target](../generic/multi_target.md) options for behavior when some agents cannot be snapshotted.

## create

Agent IDs can be specified as positional arguments for convenience:

```
mngr snapshot create my-agent
mngr snapshot create --agent my-agent
mngr snapshot create my-agent another-agent
mngr snapshot create --agent my-agent --agent another-agent
```

- `--agent AGENT`: Agent(s) to snapshot. Positional arguments are also accepted as a shorthand. [repeatable]
- `--host HOST`: Host(s) to snapshot. [repeatable]
- `--stdin`: Read agents and hosts (ids or names) from stdin (one per line)
- `-a, --all, --all-agents`: Snapshot all running agents
- `--include FILTER`: Filter agents to snapshot by tags, names, types, hosts, etc.
- `--exclude FILTER`: Exclude agents matching filter from snapshotting
- `--name NAME`: Custom name for the snapshot
- `--description DESC`: Description or notes for the snapshot
- `--tag KEY=VALUE`: Metadata tag for the snapshot [repeatable]
- `--restart-if-larger-than SIZE`: Automatically restart the host if snapshot is larger than specified size (e.g., `5G`, `500M`). Useful for preventing Docker snapshots from growing too large.
- `--[no-]pause-during`: Pause the agent during snapshot creation (more consistent state) [default: pause]
- `--[no-]wait`: Wait for snapshot to complete before returning [default: wait]

## list

- `--agent AGENT`: Agent(s) to list snapshots for. [repeatable]
- `-a, --all, --all-agents`: List snapshots for all agents
- `--include FILTER`: Filter snapshots by name, tag, or date
- `--exclude FILTER`: Exclude snapshots matching filter
- `--after DATE`: Show only snapshots created after this date
- `--before DATE`: Show only snapshots created before this date
- `--limit N`: Limit number of results
- `--format FORMAT`: Output format as a string template, see docs. Mutually exclusive with `--json` and `--jsonl` (see [common options](../generic/common.md))

## destroy

- `--agent AGENT`: Agent(s) whose snapshots to destroy. [repeatable]
- `--stdin`: Read agents and hosts (ids or names) from stdin (one per line)
- `--snapshot SNAPSHOT_ID`: ID of the snapshot to destroy. [repeatable]
- `--all-snapshots`: Destroy all snapshots for the specified agent(s)
- `--include FILTER`: Filter snapshots to destroy by name, tag, or date
- `--exclude FILTER`: Exclude snapshots matching filter from destruction
- `-f, --force`: Skip confirmation prompts
- `--dry-run`: Show which snapshots would be destroyed without actually deleting them
---

