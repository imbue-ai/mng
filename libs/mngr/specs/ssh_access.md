sshd is started inside the agent host as soon as it is created, and all access to the host is done via SSH.

Keys are deleted from `~/.ssh/mngr/` when the host is destroyed

See [agent conventions](../docs/conventions.md) for more details about SSH key locations.

## TODOs

- **SSH key deletion on host destruction**: `destroy_host()` does not clean up SSH keys from disk
- **Per-host key isolation**: Modal provider uses single shared key for all hosts instead of per-host keys
- **Convention-compliant key storage**: Keys stored in `~/.mngr/providers/modal/` instead of `~/.ssh/mngr/<host_id>`
- **Remote provider SSH support**: All SSH functionality for remote provider not yet implemented (see `specs/providers/remote.md`)
