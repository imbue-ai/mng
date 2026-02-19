# Docker Provider Spec [future]

## Metadata Storage

Agent metadata is stored as Docker container labels. When an agent is created, mng sets labels on the container:

```
com.imbue.mng.agent-id=<agent-id>
com.imbue.mng.agent-name=<name>
com.imbue.mng.agent-type=<type>
com.imbue.mng.tags=<json-encoded-tags>
com.imbue.mng.parent-id=<parent-agent-id>
com.imbue.mng.created-at=<iso-timestamp>
```

Labels are preserved across container stop/start cycles and are included in committed images (for snapshots).

Docker labels have a size limit. If metadata exceeds this limit, mng will warn and truncate tags.

Docker labels cannot be changed after being set. If a user attempts to mutate them, mng will raise an error.

## Host Discovery

mng discovers Docker hosts by listing containers with the `com.imbue.mng.agent-id` label.

## Agent Self-Management

Unlike Modal sandboxes, Docker containers have a simpler mechanism for self-stopping. An agent running inside a Docker container can stop the container by killing the process with PID 1 (the container's init process).

When PID 1 terminates, Docker automatically stops the container. This provides a straightforward way for agents to stop themselves without requiring external API access.

## Snapshots

Snapshots are created via `docker commit`. The resulting image is tagged with:

```
mng-snapshot:<agent-id>-<snapshot-id>
```

### Snapshot Constraints

Certain Docker configurations are incompatible with snapshotting or make snapshots unreliable:

- **Bind mounts**: Snapshots only capture the container's filesystem layers, not bind-mounted host directories. If critical state is stored in bind mounts, it will be lost.
- **GPU access**: Containers using GPU resources may have hardware-specific state that cannot be captured in snapshots.
- **Shared volumes**: Like bind mounts, volumes shared between containers are not included in snapshots.
- **Network-attached storage**: Any external storage mounted into the container will not be captured.

When any of these configurations are detected, mng should either:
1. Disable snapshotting automatically and warn the user, or
2. Warn the user that snapshots may be incomplete and allow them to proceed

The user should be able to explicitly disable snapshot warnings via configuration if they understand the risks.
