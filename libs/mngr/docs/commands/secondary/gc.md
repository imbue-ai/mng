# mngr gc - CLI Options Reference

Garbage collect unused resources.

Automatically removes containers, old snapshots, unused hosts, cached images, and any resources that are associated with destroyed hosts and agents.

`mngr destroy` automatically cleans up resources when an agent is deleted. `mngr gc` can be used to manually trigger garbage collection of unused resources at any time.

For interactive cleanup (e.g. to help you decide which agents and hosts to destroy), see `mngr cleanup`.

## Usage

```
mngr gc
```

## What to Clean

Agent resources:

- `--all-agent-resources`: Clean all the below resource types (machines, snapshots, volumes, work dirs)
- `--machines`: Remove unused containers, instances, and sandboxes
- `--snapshots`: Remove unused snapshots
- `--volumes`: Remove unused volumes
- `--work-dirs`: Remove work directories (git worktrees/clones) not in use by any agent

Mngr resources:

- `--logs`: Remove log files from destroyed agents/hosts (global)
- `--build-cache`: Remove build cache entries (per-provider)
- `--machine-cache`: Remove build cache entries (per-provider)

## Filtering

- `--include FILTER`: Only clean resources matching CEL filter (use "x.type == '...' && ..." to filter down to specific resources if matching multiple) [repeatable]
- `--exclude FILTER`: Exclude resources from cleanup that match a CEL filter (use "x.type != '...' || ..." to filter down to specific resources if matching multiple) [repeatable]

For snapshots, you can use `x.recency_idx` in filters to select based on snapshot age within each host:
- `x.recency_idx == 0` matches the most recent snapshot
- `x.recency_idx < 5` matches the 5 most recent snapshots
- To keep only the 5 most recent snapshots, use: `--exclude "x.recency_idx < 5"`

## Scope

- `--all-providers`: Clean resources across all providers
- `--provider PROVIDER`: Clean resources for a specific provider (e.g., `docker`, `modal`) [repeatable]

## Safety

- `--dry-run`: Show what would be cleaned without actually cleaning
- `-w, --watch SECONDS`: Re-run garbage collection at the specified interval
