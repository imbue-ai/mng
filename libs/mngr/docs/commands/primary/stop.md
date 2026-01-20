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
