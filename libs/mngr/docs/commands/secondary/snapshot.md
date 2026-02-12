# mngr snapshot - CLI Options Reference

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
