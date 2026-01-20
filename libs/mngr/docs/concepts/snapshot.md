# Snapshots

Snapshots capture the complete filesystem state of a [host](./hosts.md). They enable:

- **Stop/start**: State is saved when stopping, restored when starting
- **Backups**: Create manual checkpoints via `mngr snapshot`
- **Forking**: Create a new agent from an existing one via `mngr copy`

## Creating Snapshots

`mngr` creates snapshots automatically when stopping an agent. You can also create them manually:

```bash
mngr snapshot create --agent my-agent
mngr snapshot create --agent my-agent --name "before-refactor"
```

## Using Snapshots

Snapshots are restored automatically when starting a stopped agent. You can also:

```bash
mngr start --snapshot <id>                          # Start from specific snapshot
mngr create --from-agent my-agent --snapshot <id>   # New agent from snapshot
mngr copy my-agent new-agent                           # Fork from latest snapshot
```

## Consistency

Snapshot semantics are "hard power off": in-flight writes may not be captured. For databases or other stateful applications, this is usually fine since they're designed to survive power loss.

By default, hosts are stopped during snapshotting to improve consistency. This can be disabled via the `--no-stop-during` flag, but doing so may lead to corrupted files in the snapshot.

## Provider Support

Snapshot support varies by [provider](./providers.md):

- **Local**: Not supported
- **Docker**: `docker commit` (incremental relative to container start, can be slow for large containers)
- **Modal**: Native snapshots (fast, fully incremental since the last snapshot)

## Managing Snapshots

List and clean up snapshots:

```bash
mngr snapshot list --agent my-agent
mngr snapshot destroy --agent my-agent --snapshot-id <id>
```

See [`mngr snapshot`](../commands/secondary/snapshot.md) for all options.
