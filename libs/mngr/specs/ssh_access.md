sshd is started inside the agent host as soon as it is created, and all access to the host is done via SSH.

Keys are deleted from `~/.ssh/mngr/` when the host is destroyed [future]

See [agent conventions](../docs/conventions.md) for more details about SSH key locations. [future: Modal provider uses single shared key instead of per-host keys at `~/.ssh/mngr/<host_id>`, and stores keys in `~/.mngr/providers/modal/` instead]

Note: The following features are planned but not yet documented: remote provider SSH support (see `specs/providers/remote.md`).
