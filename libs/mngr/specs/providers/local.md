# Local Provider Spec

## Metadata Storage

For local hosts, agent metadata is stored in a JSON file:

```
~/.local/share/mngr/agents/<agent-id>/metadata.json
```

This file contains:

```json
{
  "agent_id": "<agent-id>",
  "agent_name": "<name>",
  "agent_type": "<type>",
  "tags": {"key": "value"},
  "created_at": "<iso-timestamp>",
  "work_dir": "/path/to/work_dir"
}
```

## Host Discovery

mngr discovers local hosts by:
1. Listing tmux sessions matching the `mngr-*` prefix
2. Reading metadata files from `~/.local/share/mngr/agents/`

## Snapshots

Local snapshots are directory copies. Not supported for in-place mode; only available for copy/clone modes.

## TODOs

The following features from this spec are not yet implemented:

- Metadata storage: Uses `data.json` instead of `metadata.json`; missing `tags` field; uses `{host_dir}/agents/` instead of `~/.local/share/mngr/agents/`
- Host discovery via tmux sessions matching `mngr-*` prefix
- Snapshots functionality (directory copies for clone/copy modes)
