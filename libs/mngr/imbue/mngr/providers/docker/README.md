# Docker Provider -- Architecture

This document describes the internal architecture of the Docker provider.
For user-facing documentation, see `docs/core_plugins/providers/docker.md`.

## Overview

The Docker provider manages Docker containers as mngr hosts. Each container
runs sshd and is accessed via pyinfra's SSH connector, following the same
pattern as the Modal provider. The key difference is that Docker supports
native stop/start (containers are stopped, not destroyed) and snapshots are
implemented via `docker commit`.

## Module Layout

```
providers/docker/
    __init__.py          # Empty (per style guide)
    backend.py           # ProviderBackendInterface implementation; hookimpl for plugin registration
    config.py            # DockerProviderConfig (pydantic model for provider config)
    host_store.py        # DockerHostStore: host record and agent data persistence on the state volume
    instance.py          # DockerProviderInstance: core provider logic
    volume.py            # DockerVolume: Volume implementation via exec into a state container
    testing.py           # Test helpers (make_docker_provider, cleanup fixtures)
    README.md            # This file
```

## State Container and State Volume

All provider-level metadata (host records, agent data, per-host volumes) is
stored on a Docker named volume. This volume is mounted into a singleton
"state container" -- a small Alpine container that stays running and acts
as a file server. All file operations against the state volume are performed
by exec-ing commands (`cat`, `ls`, `mkdir`, `rm`) in this container, or by
using `put_archive` for writes.

```
Docker Named Volume: <prefix>docker-state-<user_id>
    mounted at /mngr-state inside the state container

State Container: <prefix>docker-state-<user_id>
    image: alpine:latest
    restart: unless-stopped
    purpose: provides exec target for all volume I/O
```

The state container is created lazily by `ensure_state_container()` in
`volume.py` the first time the provider instance accesses `_state_volume`.

### Why a state container instead of direct filesystem access?

The state volume may live on a remote Docker daemon (`ssh://user@server`).
By exec-ing into a container that mounts the volume, we get uniform
read/write access regardless of whether Docker is local or remote. This is
analogous to how the Modal provider accesses its Modal Volume via the Modal
API.

## State Volume Directory Layout

```
/mngr-state/
    host_state/
        <host_id>.json              # HostRecord (SSH info, config, certified data)
        <host_id>/
            <agent_id>.json         # Persisted agent data (for offline listing)
    volumes/
        <host_id>/                  # Per-host volume directory
            .volume                 # Marker file (created during host creation)
            agents/
                <agent_id>/         # Per-agent scoped data
                    ...
```

### host_state/

The `host_state/` directory contains `HostRecord` JSON files. Each record
stores everything needed to reconnect to a host:

- `certified_host_data`: the canonical host metadata (name, tags, snapshots,
  failure reason, timestamps, idle config)
- `ssh_host`, `ssh_port`, `ssh_host_public_key`: SSH connection info
- `config`: `ContainerConfig` (start_args, image) for replay on snapshot restore
- `container_id`: Docker container ID

For failed hosts (creation failure), only `certified_host_data` is populated;
the SSH fields and config are `None`.

Agent data is persisted alongside host records at
`host_state/<host_id>/<agent_id>.json` so agents can be listed even when
the host is offline.

### volumes/

The `volumes/` directory contains per-host volume directories. Each host
gets a subdirectory at `volumes/<host_id>/` that is created during
`create_host()`. This directory is accessible via `get_volume_for_host()`
and provides persistent storage that survives container stop/start and is
readable even when the container is offline.

This is analogous to how Modal creates a per-host Modal Volume that is
bind-mounted into the sandbox. The Docker equivalent stores this data on the
shared state volume and provides it as a scoped `DockerVolume`.

When a host is destroyed via `destroy_host()`, the volume directory is
cleaned up.

## SSH Architecture

Each Docker container runs sshd for pyinfra access. The SSH setup uses:

1. **Client keypair** (`docker_ssh_key` / `docker_ssh_key.pub`): stored in
   the profile directory at `~/.mngr/<profile>/providers/docker/<instance>/keys/`.
   One keypair is shared across all containers for a given provider instance.

2. **Host keypair** (`host_key` / `host_key.pub`): also stored in the profile
   directory. Injected into each container so we can pre-trust the host key
   and avoid host key verification prompts.

3. **known_hosts**: maintained at the same keys directory. Updated each time
   a container is created or reconnected.

SSH setup is performed via `docker exec` (not SSH itself -- that would be
circular). The shared helpers in `providers/ssh_host_setup.py` generate shell
commands that:
- Install openssh-server, tmux, python3, rsync if missing
- Configure the SSH authorized_keys and host key
- Start sshd in the background

## Container Lifecycle

### Creation

```
create_host(name, image, ...)
    1. Pull base image (or build from Dockerfile)
    2. Run container: docker run -d --name <prefix><name> -p :22 ...
    3. Install packages via docker exec
    4. Configure SSH via docker exec
    5. Start sshd via docker exec (detached)
    6. Wait for sshd to accept connections
    7. Create pyinfra Host object
    8. Write HostRecord to state volume
    9. Create host volume directory at volumes/<host_id>/
    10. Create shutdown.sh script on the host
    11. Start activity watcher
```

### Stop

```
stop_host(host, create_snapshot=True)
    1. Optionally create snapshot (docker commit)
    2. docker stop (SIGTERM to PID 1, which traps and exits cleanly)
    3. Update host record with stop_reason
```

### Start (native restart)

```
start_host(host_id)
    1. docker start (restarts stopped container, filesystem preserved)
    2. Re-run SSH setup (sshd, keys, etc.)
    3. Return new Host object
```

### Start (from snapshot)

```
start_host(host_id, snapshot_id)
    1. Remove old container
    2. docker run from committed image (snapshot)
    3. Re-run SSH setup
    4. Return new Host object
```

### Destroy

```
destroy_host(host, delete_snapshots=True)
    1. Stop container (no snapshot)
    2. docker rm -f
    3. Delete snapshot images
    4. Delete host record from state volume
    5. Delete host volume directory
```

## Container Entrypoint

All containers (both host containers and the state container) use the same
entrypoint:

```sh
trap 'exit 0' TERM; tail -f /dev/null & wait
```

This keeps PID 1 alive (via `tail -f /dev/null`) and responds to SIGTERM
with a clean exit (exit code 0). This is important because `docker stop`
sends SIGTERM, and we want containers to exit cleanly.

## Container Labels

Docker containers are labeled with mngr metadata for discovery:

- `com.imbue.mngr.host-id`: the HostId
- `com.imbue.mngr.host-name`: the HostName
- `com.imbue.mngr.provider`: the provider instance name
- `com.imbue.mngr.tags`: JSON-encoded user tags

These labels are used by `_find_container_by_host_id()` and
`_find_container_by_name()` for fast container lookup via Docker API
filters. Tags are immutable after creation (Docker does not support
label mutation).

## Snapshots

Snapshots use `docker commit` to create a new image from a running
container. The committed image ID is stored in the host record's
`certified_host_data.snapshots` list. Restoring from a snapshot creates
a new container from the committed image (the old container is removed).

Note: Docker volume mounts are NOT captured in snapshots. Only the
container's filesystem layers are committed.

## Relationship to Other Providers

The Docker provider follows the same patterns as the Modal provider:

| Concept | Modal | Docker |
|---------|-------|--------|
| State storage | Modal Volume | Docker named volume via state container |
| Host record store | `ModalHostStore` | `DockerHostStore` |
| Volume impl | `ModalVolume` | `DockerVolume` |
| SSH setup | SSH into sandbox | docker exec into container |
| Stop/start | Terminate + snapshot | Native docker stop/start |
| Snapshots | Modal snapshots | docker commit |
| Per-host volume | Modal Volume per host | Sub-folder on state volume |
