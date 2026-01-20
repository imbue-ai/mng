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
