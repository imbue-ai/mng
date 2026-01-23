# Local Provider

The Local provider manages agents running directly on your local machine. It represents your local computer as a single host that cannot be stopped or destroyed.

## Usage

```bash
mngr create my-agent --in local
```

If no provider is specified, local is the default.

## Configuration

The local provider accepts a `host_dir` parameter for the base directory where mngr data is stored:

```yaml
providers:
  local:
    host_dir: ~/.local/share/mngr
```

If no host_dir is specified, mngr uses the global `default_host_dir` setting.

## Host Management

The local provider represents your local machine as a persistent host with a stable ID:

- **Host ID** is generated once and stored in `{host_dir}/providers/local/host_id`
- **Host tags** are stored in `{host_dir}/providers/local/labels.json`
- The host cannot be stopped or destroyed (raises `LocalHostNotStoppableError` and `LocalHostNotDestroyableError`)
- The host is always considered "running"

## Agent Execution

Agents run in tmux sessions for easy terminal access:

- Sessions are named `{prefix}{agent-name}` (default prefix: `mngr-`)
- Use `mngr connect <agent-name>` to attach to an agent's tmux session
- Agent metadata is stored in `{host_dir}/agents/<agent-id>/data.json`

## Agent Discovery

mngr discovers agents on the local host by listing directories in `{host_dir}/agents/` and reading their `data.json` files.

## Resource Detection

The local provider uses psutil to detect system resources:

- CPU count and frequency
- Available memory
- Disk space

## Limitations

- **Snapshots are not supported** - `supports_snapshots` returns `False`
- **Volumes are not supported** - `supports_volumes` returns `False`
- **The host cannot be stopped or destroyed** - Operations raise errors

## TODO

The following features from the specification are not yet implemented:

- Host discovery via listing tmux sessions with `mngr-*` prefix (currently discovers by reading agent directories only)
- Snapshot support via directory copies for copy/clone modes
- Agent metadata storage at exact spec path `~/.local/share/mngr/agents/<agent-id>/metadata.json` (currently uses `{host_dir}/agents/<agent-id>/data.json`)
