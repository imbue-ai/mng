# Conventions

The `mngr` tool prefixes the names of many resources with `mngr-` (this can be customized via `MNGR_PREFIX` environment variable).

Unless otherwise specified, `mngr` assumes:
- the user is `root` (override via config or CLI args for most commands) 
- host names are formatted as `mngr-<host_name>`, where `<host_name>` is the unique identifier for the host (a host can contain multiple agents).
- tmux sessions are named `mngr-<agent_name>`
- SSH keys are created for each remote host and stored at `~/.ssh/mngr/<host_id>` and `~/.ssh/mngr/<host_id>.pub` (or access to the host is handled by ssh-agent or similar)
- agent data exists at `$MNGR_AGENT_STATE_DIR` (i.e., `$MNGR_HOST_DIR/agents/$MNGR_AGENT_ID/`)
- there are `logs` and `events` subdirectories inside `$MNGR_HOST_DIR` and each `$MNGR_AGENT_STATE_DIR` for storing logs and event data
- environment variables for hosts and agents are stored in `$MNGR_HOST_DIR/env` and `$MNGR_AGENT_STATE_DIR/env` respectively
- IDs are base16-encoded UUID4s
- Names are human-readable strings that can contain letters, numbers, and hyphens (no underscores, spaces, etc because they are used for DNS)

`mngr` automatically sets these additional environment variables inside agent tmux sessions:

- `MNGR_HOST_DIR` — The base directory for all mngr data within the host where the agent is running. See [host spec](../specs/host.md) for data layout (default: `~/.mngr`).
- `MNGR_AGENT_ID` — The agent's unique identifier
- `MNGR_AGENT_NAME` — The agent's human-readable name
- `MNGR_AGENT_STATE_DIR` — The per-agent directory for status, activity, plugins. See [agent spec](../specs/agent.md) for data layout (default: `$MNGR_HOST_DIR/agents/$MNGR_AGENT_ID/`)
- `MNGR_AGENT_WORK_DIR` — The directory in which the agent is started, which contains your project files

See [environment variables](./concepts/environment_variables.md) for the full list and how to set custom variables.
