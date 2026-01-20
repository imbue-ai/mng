# mngr destroy - CLI Options Reference

Destroys existing agent(s) and their associated resources.

When the last agent on a host is destroyed, the host itself is also destroyed (including containers, volumes, snapshots, and any remote infrastructure).

Use with caution! This operation is irreversible.

**Alias:** `rm`

## Usage

```
mngr destroy [options] [[--agent] agent ...]
```

Agents can be specified as positional arguments for convenience. The following are equivalent:

```
mngr destroy my-agent
mngr destroy --agent my-agent
mngr destroy my-agent another-agent
mngr destroy --agent my-agent --agent another-agent
```

## General

- `--agent AGENT`: Specify agent(s) to destroy. Positional arguments are also accepted as a shorthand. [repeatable]
- `-f, --force`: Skip confirmation prompts and override safety checks (e.g., automatically stop a running agent before destroying)
- `-a, --all, --all-agents`: Destroy all agents
- `--session SESSION`: Destroy the agent by specifying its tmux session name. The agent name is extracted by stripping the configured prefix (e.g., "mngr-") from the session name. This is used by the Ctrl-q hotkey binding to destroy the correct agent. [repeatable]
- `--include FILTER`: Filter agents to destroy by tags, names, types, hosts, etc.
- `--exclude FILTER`: Exclude agents matching filter from destruction
- `--stdin`: Read agents and hosts (ids or names) from stdin (one per line)
- `--dry-run`: Show what would be destroyed without actually destroying

## Resource Cleanup

See [resource cleanup options](../generic/resource_cleanup.md) to control which associated resources are also destroyed (defaults to all).
