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
- `-a, --all, --all-agents`: Snapshot all running agents
- `--name NAME`: Custom name for the snapshot
- `--dry-run`: Show what would be snapshotted without actually creating snapshots
- `--stdin`: Read agents and hosts (ids or names) from stdin (one per line) [future]
- `--include FILTER`: Filter agents to snapshot by tags, names, types, hosts, etc. [future]
- `--exclude FILTER`: Exclude agents matching filter from snapshotting [future]
- `--description DESC`: Description or notes for the snapshot [future]
- `--tag KEY=VALUE`: Metadata tag for the snapshot [repeatable] [future]
- `--restart-if-larger-than SIZE`: Automatically restart the host if snapshot is larger than specified size (e.g., `5G`, `500M`). Useful for preventing Docker snapshots from growing too large. [future]
- `--[no-]pause-during`: Pause the agent during snapshot creation (more consistent state) [default: pause] [future]
- `--[no-]wait`: Wait for snapshot to complete before returning [default: wait] [future]

## list

Agent IDs can be specified as positional arguments for convenience:

```
mngr snapshot list my-agent
mngr snapshot list --agent my-agent
```

- `--agent AGENT`: Agent(s) to list snapshots for. Positional arguments are also accepted as a shorthand. [repeatable]
- `-a, --all, --all-agents`: List snapshots for all agents
- `--limit N`: Limit number of results
- `--include FILTER`: Filter snapshots by name, tag, or date [future]
- `--exclude FILTER`: Exclude snapshots matching filter [future]
- `--after DATE`: Show only snapshots created after this date [future]
- `--before DATE`: Show only snapshots created before this date [future]

See [common options](../generic/common.md) for output format options (`--format`).

## destroy

Agent IDs can be specified as positional arguments for convenience:

```
mngr snapshot destroy my-agent --snapshot snap-abc123 --force
mngr snapshot destroy --agent my-agent --all-snapshots --force
```

- `--agent AGENT`: Agent(s) whose snapshots to destroy. Positional arguments are also accepted as a shorthand. [repeatable]
- `--snapshot SNAPSHOT_ID`: ID of the snapshot to destroy. [repeatable]
- `--all-snapshots`: Destroy all snapshots for the specified agent(s)
- `-f, --force`: Skip confirmation prompts
- `--dry-run`: Show which snapshots would be destroyed without actually deleting them
- `--stdin`: Read agents and hosts (ids or names) from stdin (one per line) [future]
- `--include FILTER`: Filter snapshots to destroy by name, tag, or date [future]
- `--exclude FILTER`: Exclude snapshots matching filter from destruction [future]
