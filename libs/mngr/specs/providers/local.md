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

- Agent metadata storage with `agent_id`, `agent_name`, `agent_type`, `created_at`, `work_dir` fields
- Host discovery via tmux sessions matching `mngr-*` prefix
- Host discovery via reading metadata files from `~/.local/share/mngr/agents/`
- Snapshots functionality (directory copies)
