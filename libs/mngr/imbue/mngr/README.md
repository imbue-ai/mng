This is the layered import order for the mngr packages (from high-level to low-level):

- main
- cli
- api
- agents
- providers
- hosts
- errors
- interfaces
- config
- utils
- primitives

Note: The following features are planned but not yet documented inline:

**CLI Commands:**
- `connect`: --message, --message-file, --message-delay, --retry, --attach-command, --no-reconnect, remote agent connections
- `list`: custom format templates, field selection, watch mode, custom filter aliases, custom sorting, result limiting
- `pull`: --sync-mode (non-files), --exclude, --source-host

**API:**
- Provider name filtering in list_agents
- Snapshot source agent creation

**Providers:**
- Modal: volume support
- Remote host cooperative locking
