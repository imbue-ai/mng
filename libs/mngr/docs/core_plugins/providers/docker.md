# Docker Provider

The Docker provider allows mngr to manage agents running in Docker containers on local or remote Docker hosts.

## Configuration

The Docker provider accepts a `host` parameter for connecting to remote Docker daemons via SSH:

```yaml
providers:
  docker:
    host: ssh://user@remote-host
```

If no host is specified, mngr connects to the local Docker daemon.

## Metadata Storage

Agent metadata is stored as Docker container labels with the `com.imbue.mngr.*` prefix:

- `com.imbue.mngr.agent-id` - Unique agent identifier
- `com.imbue.mngr.agent-name` - Agent name
- `com.imbue.mngr.agent-type` - Agent type
- `com.imbue.mngr.tags` - JSON-encoded tags
- `com.imbue.mngr.parent-id` - Parent agent ID
- `com.imbue.mngr.created-at` - ISO timestamp

Labels persist across container stop/start cycles and are preserved in snapshots.

## Host Discovery

mngr discovers Docker-based agents by listing containers with the `com.imbue.mngr.agent-id` label.

## Agent Self-Management

Agents running inside Docker containers can stop themselves by killing PID 1 (the container's init process). When PID 1 terminates, Docker automatically stops the container.

## Snapshots

Snapshots capture the container's filesystem state via `docker commit`. Images are tagged as:

```
mngr-snapshot:<agent-id>-<snapshot-id>
```

### Snapshot Limitations

Snapshots only capture container filesystem layers. The following are not included:

- Bind-mounted host directories
- Shared volumes
- Network-attached storage
- GPU-specific hardware state

mngr warns when these configurations are detected and may disable snapshotting to prevent data loss.

## TODO

The following features from the specification are not yet implemented:

- Backend implementation (DockerProviderBackend class)
- Provider instance implementation (DockerProviderInstance class)
- Container lifecycle management (create, start, stop, destroy)
- Metadata storage via Docker labels
- Host discovery by listing labeled containers
- Snapshot creation via docker commit
- Snapshot constraint detection and warnings
- Remote Docker host support via SSH
- Resource limit configuration
- GPU detection and handling
