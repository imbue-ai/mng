# Docker Provider Implementation Plan

This document describes the implementation plan for the Docker provider, which manages [hosts](../../docs/concepts/hosts.md) as Docker containers with SSH access via pyinfra. The Docker provider provides container isolation on local or remote Docker daemons, with support for snapshots via `docker commit`, native stop/start, and the same SSH-based host access pattern used by the [Modal provider](./modal.md).

## Overview

The Docker provider sits between the local provider (no isolation, no snapshots) and the Modal provider (full cloud isolation, native snapshots) in terms of complexity. It provides container-level isolation without cloud costs, making it ideal for running untrusted agents on your own machine or a remote Docker host.

**Key characteristics:**

- Uses the Docker Engine API via the `docker` Python SDK
- SSH-based host access (same pattern as Modal: sshd inside the container, SSH port exposed via Docker port mapping)
- Snapshots via `docker commit` / `docker run` from committed image
- Native `docker stop` / `docker start` for stop/start (unlike Modal which must terminate and recreate from snapshots)
- Metadata stored in Docker container labels (immutable, for discovery and tags) and a local JSON file store (for host records)
- Reuses `ssh_host_setup.py` for package installation, SSH key setup, known_hosts configuration, and activity watcher setup
- Supports local and remote Docker daemons via `DOCKER_HOST` or the `host` config field

## File Structure

```
providers/docker/
    __init__.py          # blank (exists already)
    config.py            # DockerProviderConfig (exists, needs expansion)
    backend.py           # DockerProviderBackend + register_provider_backend hookimpl
    instance.py          # DockerProviderInstance
    host_store.py        # JSON file-based host record storage
```

## Dependencies

- **`docker`** Python SDK (pip package `docker`): For all Docker Engine API interactions (container lifecycle, image management, exec). This is a well-established, officially maintained library.
- **Existing shared utilities**: `ssh_host_setup.py` (package installation, SSH key configuration, activity watcher), `modal/ssh_utils.py` (SSH keypair generation and management -- these should be refactored to a shared location).

## Configuration: `DockerProviderConfig`

Extends `ProviderInstanceConfig`. Expands the existing config at `docker/config.py`.

```python
class DockerProviderConfig(ProviderInstanceConfig):
    backend: ProviderBackendName = Field(default=ProviderBackendName("docker"))
    host: str = Field(
        default="",
        description="Docker host URL (e.g., 'ssh://user@server', 'tcp://host:2376'). "
                    "Empty string means local Docker daemon.",
    )
    host_dir: Path | None = Field(
        default=None,
        description="Base directory for mngr data inside containers (defaults to /mngr)",
    )
    default_image: str | None = Field(
        default=None,
        description="Default base image. None uses debian:bookworm-slim.",
    )
    default_cpu: float = Field(
        default=1.0,
        description="Default CPU cores (maps to Docker --cpus)",
    )
    default_memory: float = Field(
        default=1.0,
        description="Default memory in GB (maps to Docker --memory)",
    )
    default_gpu: str | None = Field(
        default=None,
        description="Default GPU configuration. None means no GPU.",
    )
    default_idle_timeout: int = Field(
        default=800,
        description="Default host idle timeout in seconds",
    )
    default_idle_mode: IdleMode = Field(
        default=IdleMode.IO,
        description="Default idle mode for hosts",
    )
    default_activity_sources: tuple[ActivitySource, ...] = Field(
        default_factory=lambda: tuple(ActivitySource),
        description="Default activity sources",
    )
    network: str | None = Field(
        default=None,
        description="Docker network to attach containers to. None uses the default bridge.",
    )
    extra_hosts: dict[str, str] = Field(
        default_factory=dict,
        description="Extra /etc/hosts entries (maps to Docker --add-host)",
    )
```

**Note:** The `host` field allows connecting to remote Docker daemons. The `docker` SDK reads `DOCKER_HOST`, `DOCKER_TLS_VERIFY`, and `DOCKER_CERT_PATH` environment variables by default, so the config field provides an explicit override while the env vars provide a fallback. When `host` is non-empty, it is passed to `docker.DockerClient(base_url=host)`.

## Backend: `DockerProviderBackend`

Stateless factory registered via the `register_provider_backend` pluggy hook (same pattern as `local/backend.py` and `modal/backend.py`).

```python
DOCKER_BACKEND_NAME = ProviderBackendName("docker")

class DockerProviderBackend(ProviderBackendInterface):
    @staticmethod
    def get_name() -> ProviderBackendName:
        return DOCKER_BACKEND_NAME

    @staticmethod
    def get_description() -> str:
        return "Runs agents in Docker containers with SSH access"

    @staticmethod
    def get_config_class() -> type[ProviderInstanceConfig]:
        return DockerProviderConfig

    @staticmethod
    def get_build_args_help() -> str:
        # Documents: --cpu, --memory, --gpu, --image, --dockerfile,
        #            --context-dir, --network, --volume, --port
        ...

    @staticmethod
    def get_start_args_help() -> str:
        return "No start arguments are supported for the docker provider."

    @staticmethod
    def build_provider_instance(
        name: ProviderInstanceName,
        config: ProviderInstanceConfig,
        mngr_ctx: MngrContext,
    ) -> ProviderInstanceInterface:
        assert isinstance(config, DockerProviderConfig)
        host_dir = config.host_dir if config.host_dir is not None else Path("/mngr")
        return DockerProviderInstance(
            name=name,
            host_dir=host_dir,
            mngr_ctx=mngr_ctx,
            config=config,
        )

@hookimpl
def register_provider_backend():
    return (DockerProviderBackend, DockerProviderConfig)
```

## Host Record Store: `host_store.py`

The Modal provider stores host records (SSH info, config, snapshots, certified_host_data) on a Modal Volume. Docker needs an equivalent persistent store that survives container destruction. This is implemented as a local JSON file store under the mngr profile directory.

```
~/.mngr/profiles/<profile>/providers/docker/<provider_name>/
    hosts/
        <host_id>.json        # HostRecord (same structure as Modal's HostRecord)
        <host_id>/
            <agent_id>.json   # Persisted agent data (same as Modal's volume layout)
    keys/
        docker_ssh_key        # Client SSH private key
        docker_ssh_key.pub    # Client SSH public key
        host_key              # Host SSH private key
        host_key.pub          # Host SSH public key
        known_hosts           # Known hosts file for SSH connections
```

The `HostRecord` model is identical to Modal's:

```python
class ContainerConfig(HostConfig):
    """Configuration parsed from build arguments."""
    gpu: str | None = None
    cpu: float = 1.0
    memory: float = 1.0
    image: str | None = None
    dockerfile: str | None = None
    context_dir: str | None = None
    network: str | None = None
    volumes: tuple[str, ...] = ()
    ports: tuple[str, ...] = ()

class HostRecord(FrozenModel):
    """Host metadata stored in the local file store."""
    certified_host_data: CertifiedHostData
    ssh_host: str | None = None
    ssh_port: int | None = None
    ssh_host_public_key: str | None = None
    config: ContainerConfig | None = None
    container_id: str | None = None  # Docker container ID for reconnection
```

The `DockerHostStore` class provides methods mirroring the Modal provider's volume operations:

- `write_host_record(host_record)` -- Write a host record to disk
- `read_host_record(host_id)` -- Read a host record from disk (with caching)
- `delete_host_record(host_id)` -- Delete a host record and associated agent data
- `list_all_host_records()` -- List all host records
- `persist_agent_data(host_id, agent_data)` -- Write agent data for offline listing
- `list_persisted_agent_data_for_host(host_id)` -- Read persisted agent data
- `remove_persisted_agent_data(host_id, agent_id)` -- Remove persisted agent data

**Note:** Unlike Modal's Volume which is remote, this store is local to the machine running mngr. This means state is not shared between different machines. This is acceptable because Docker containers are also local (or at least tied to a specific Docker host). If the Docker host is remote (via `host` config), the host record store still lives on the mngr machine since it needs to persist even when the Docker host is unreachable.

## Instance: `DockerProviderInstance`

The main implementation. Extends `BaseProviderInstance` (same as Modal and SSH providers).

### Capability Properties

```python
@property
def supports_snapshots(self) -> bool:
    return True

@property
def supports_shutdown_hosts(self) -> bool:
    return True  # Docker supports native stop/start

@property
def supports_volumes(self) -> bool:
    return False  # Docker volumes are managed externally

@property
def supports_mutable_tags(self) -> bool:
    return False  # Tags stored in Docker labels, which are immutable after creation
```

**Note on `supports_mutable_tags`:** Docker container labels are immutable after creation. Tags are stored as labels on the container, so they are set at host creation time and cannot be changed afterward. This avoids the need for a sync mechanism between external state and the container. If a user attempts to mutate tags, mngr raises an error.

### Docker Client Management

The `DockerProviderInstance` lazily creates a `docker.DockerClient` and caches it for the instance lifetime.

```python
@cached_property
def _docker_client(self) -> docker.DockerClient:
    if self.config.host:
        return docker.DockerClient(base_url=self.config.host)
    return docker.from_env()
```

Error handling wraps `docker.errors.DockerException` at the boundary (similar to Modal's `handle_modal_auth_error` decorator) to produce user-friendly `MngrError` messages, particularly for "Cannot connect to Docker daemon" errors.

### Container Labels (Discovery)

Docker container labels are used for discovery and metadata. They are immutable after container creation.

```
com.imbue.mngr.host-id=<host_id>
com.imbue.mngr.host-name=<host_name>
com.imbue.mngr.provider=<provider_instance_name>
com.imbue.mngr.tags=<json-encoded tag dict>
```

The label prefix `com.imbue.mngr.` follows Docker label naming conventions. The `provider` label scopes discovery to the current provider instance (important when multiple Docker provider instances exist, e.g., one local and one remote). The `tags` label stores the user-specified tags as a JSON-encoded dictionary, set at creation time. Tags are also stored in the host record's `certified_host_data` for offline access (e.g., when a container has been destroyed but the record persists).

### SSH Access Pattern

The Docker provider follows the same SSH access pattern as Modal, reusing `ssh_host_setup.py`:

1. **Create container** with SSH port (22) exposed via Docker port mapping (random host port)
2. **Execute setup commands** inside the container via `docker exec` (using the Docker SDK's `container.exec_run()`):
   - `build_check_and_install_packages_command()` -- Check for and install sshd, tmux, curl, rsync, git, jq
   - `build_configure_ssh_command()` -- Configure SSH keys (authorized_keys, host key)
   - `build_add_known_hosts_command()` -- Add known_hosts entries for outbound SSH
3. **Start sshd** via `container.exec_run("/usr/sbin/sshd -D", detach=True)`
4. **Get SSH connection info** from Docker port mapping: `container.ports['22/tcp']` gives `(host_ip, host_port)`
5. **Add to known_hosts** via `add_host_to_known_hosts()` (from `ssh_utils.py`)
6. **Wait for sshd** via TCP socket polling (same `_wait_for_sshd` as Modal)
7. **Create pyinfra connector** via `_create_pyinfra_host()` (same pattern as Modal)
8. **Start activity watcher** via `build_start_activity_watcher_command()`

**Note on SSH host for local Docker:** When Docker runs locally, the SSH host is `127.0.0.1` (or `host.docker.internal` on macOS). When Docker runs remotely (via `host` config), the SSH host is the remote Docker host's address, extracted from the `host` config URL.

### Container Entrypoint

Docker containers need a long-running PID 1 process. The existing `resources/Dockerfile` uses:

```sh
CMD ["sh", "-c", "trap 'exit 0' TERM; tail -f /dev/null & wait"]
```

This ensures the container stays alive and responds to `SIGTERM` (from `docker stop`). For the Docker provider, containers are always started with this entrypoint pattern regardless of the user's image, by overriding the `command` at container creation time.

### Shutdown Script

The shutdown script for Docker is simpler than Modal's. Instead of calling a remote endpoint, it directly stops the container by killing PID 1:

```bash
#!/bin/bash
# Auto-generated shutdown script for mngr Docker host
# Kills PID 1 to stop the container

LOG_FILE="$HOST_DIR/logs/shutdown.log"
mkdir -p "$(dirname "$LOG_FILE")"
log() { echo "$(date '+%Y-%m-%d %H:%M:%S') $*" >> "$LOG_FILE"; echo "$*"; }

log "=== Shutdown script started ==="
log "STOP_REASON: ${1:-PAUSED}"

# Kill PID 1 to stop the container
# The entrypoint traps SIGTERM and exits cleanly
kill -TERM 1
```

This is possible because killing PID 1 in a Docker container causes the container to stop (as noted in the existing future spec). The `SIGTERM` is handled by the entrypoint's `trap`, ensuring a clean exit.

### Core Lifecycle Methods

#### `create_host()`

1. Generate `host_id` via `HostId.generate()`
2. Parse `build_args` into `ContainerConfig` (using argparse, same pattern as Modal)
3. Build or pull the Docker image:
   - If `--dockerfile` specified: `docker build` with the Dockerfile
   - If `--image` or `image` parameter specified: `docker pull` the image
   - Otherwise: use `debian:bookworm-slim`
4. Create the container:
   ```python
   container = client.containers.run(
       image=image_name,
       name=f"{prefix}{name}",
       command=["sh", "-c", "trap 'exit 0' TERM; tail -f /dev/null & wait"],
       detach=True,
       ports={"22/tcp": None},  # Random host port
       labels=build_container_labels(host_id, name),
       cpu_count=int(config.cpu),
       mem_limit=f"{int(config.memory * 1024)}m",
       # GPU support via device_requests if config.gpu is set
   )
   ```
5. Set up SSH and create Host object (shared helper `_setup_container_ssh_and_create_host()`, mirrors Modal's `_setup_sandbox_ssh_and_create_host()`)
6. Write host record to store
7. Create shutdown script on host
8. Start activity watcher

On failure, save a failed host record (same as Modal) so the user can see what happened via `mngr list`.

**Container naming:** Containers are named `{prefix}{host_name}` (e.g., `mngr-andromeda`). This enables `docker ps` to show recognizable names. If a name collision occurs, the container creation fails with a clear error.

#### `stop_host()`

1. Optionally create a snapshot via `docker commit` (if `create_snapshot=True`)
2. Disconnect SSH connection (same pattern as Modal)
3. Stop the container: `container.stop(timeout=timeout_seconds)`
4. Update host record with `stop_reason=STOPPED`
5. Clear caches

**Note:** Unlike Modal, Docker supports native stop/start, so we do NOT need to terminate and recreate from a snapshot. The container's filesystem is preserved across stop/start cycles.

#### `start_host()`

1. If the container is already running, return the existing host
2. If `snapshot_id` is provided, create a new container from the snapshot image (similar to Modal's snapshot-based restart)
3. Otherwise, start the stopped container: `container.start()`
4. Re-run SSH setup (sshd needs to be restarted after container start since processes don't survive stop/start)
5. Create Host object and update host record

**Note on restart vs snapshot restore:** Docker's native `container.start()` preserves the filesystem exactly as it was when stopped (including all modifications). This is different from Modal where stop always means "terminate + recreate from snapshot" and some state may be lost. When the user explicitly requests a snapshot-based restart (via `--snapshot`), a new container is created from the committed image.

#### `destroy_host()`

1. Stop the host (calls `stop_host()`)
2. Remove the container: `container.remove(force=True)`
3. Optionally delete snapshot images (if `delete_snapshots=True`)
4. Delete host record from store

#### `on_connection_error()`

Clear all caches for the host (container cache, host cache, host record cache). Same pattern as Modal.

### Discovery Methods

#### `get_host()`

1. Check host-by-id cache
2. By HostId: look up container by label filter, then fall back to host record store (for stopped containers)
3. By HostName: look up container by label filter, then fall back to host record store
4. Return `Host` (online) or `OfflineHost` (stopped/failed)

#### `list_hosts()`

1. List all Docker containers with `com.imbue.mngr.provider=<name>` label (includes stopped containers via `all=True` filter)
2. List all host records from the file store
3. Merge: running containers produce `Host` objects; stopped containers with snapshots or host records produce `OfflineHost` objects
4. Cache results

The Docker SDK supports label-based filtering via `client.containers.list(filters={"label": ...})`, which is efficient even with many containers.

#### `get_host_resources()`

Read from the `ContainerConfig` in the host record (CPU, memory). For running containers, can also query `container.attrs` for actual resource limits.

### Snapshot Methods

#### `create_snapshot()`

1. Find the running container for the host
2. Commit the container: `container.commit(repository="mngr-snapshot", tag=f"{host_id}-{snapshot_name}")`
3. Record the snapshot in the host record (image ID as snapshot ID, same as Modal)
4. Return the snapshot ID

The committed image ID is used as the snapshot ID, exactly matching Modal's pattern where the Modal image ID is the snapshot ID.

#### `list_snapshots()`

Read snapshot metadata from the host record in the file store. Same structure as Modal (`SnapshotRecord` with id, name, created_at).

#### `delete_snapshot()`

1. Remove the snapshot from the host record
2. Remove the Docker image: `client.images.remove(image_id)`

Unlike Modal (which can't delete images via API), Docker supports explicit image deletion.

### Tag Methods

Tags are stored in Docker container labels (immutable). They are set at host creation time and cannot be changed afterward.

- `get_host_tags()` -- Read from the container's `com.imbue.mngr.tags` label (parsed from JSON). For offline hosts, read from the host record's `certified_host_data.user_tags`.
- `set_host_tags()` -- Raises `MngrError` ("Docker provider does not support mutable tags")
- `add_tags_to_host()` -- Raises `MngrError` ("Docker provider does not support mutable tags")
- `remove_tags_from_host()` -- Raises `MngrError` ("Docker provider does not support mutable tags")

### Rename Method

Update the host record's `certified_host_data.host_name`. Docker container names cannot be changed after creation, so only the logical name in the host record is updated (the physical container name remains the original).

### Connector Method

`get_connector()` returns a pyinfra SSH connector configured with the SSH connection info from the host record (same pattern as Modal).

### Close Method

`close()` closes the Docker client connection.

## Shared Utilities Refactoring

The SSH keypair management utilities currently live in `modal/ssh_utils.py` but are provider-agnostic. As part of this implementation, these should be moved to a shared location:

**Move from `modal/ssh_utils.py` to `providers/ssh_utils.py`:**
- `generate_ssh_keypair()`
- `save_ssh_keypair()`
- `load_or_create_ssh_keypair()`
- `generate_ed25519_host_keypair()`
- `load_or_create_host_keypair()`
- `add_host_to_known_hosts()`

The Modal provider's imports would be updated to point to the new location. The key names should be parameterized (currently hardcoded as `modal_ssh_key`).

## Build Arguments

Supported build arguments (parsed via argparse, same pattern as Modal):

```
--cpu COUNT       Number of CPU cores. Default: 1.0
--memory GB       Memory in GB. Default: 1.0
--gpu TYPE        GPU access (e.g., "all", "0", "nvidia"). Default: no GPU
--image NAME      Base Docker image. Default: debian:bookworm-slim
--dockerfile PATH Path to Dockerfile for custom image build
--context-dir DIR Build context directory for Dockerfile. Default: Dockerfile's directory
--network NAME    Docker network to attach to. Default: bridge
--volume SPEC     Additional volume mount (host:container[:mode]). Can be repeated.
--port SPEC       Additional port mapping (host:container). Can be repeated.
```

## Error Handling

Docker-specific errors are caught at the provider boundary and converted to `MngrError`:

- `docker.errors.NotFound` -> `HostNotFoundError`
- `docker.errors.APIError` (connection refused) -> `MngrError` with "Cannot connect to Docker daemon" guidance
- `docker.errors.ImageNotFound` -> `MngrError` with image pull guidance
- `docker.errors.BuildError` -> `MngrError` with build log

Failed host creation saves a failed host record (with `failure_reason` and `build_log`) so it appears in `mngr list`, matching Modal's behavior.

## Snapshot Constraints

Certain Docker configurations are incompatible with snapshotting or make snapshots unreliable:

- **Bind mounts / volumes**: `docker commit` only captures the container's filesystem layers, not mounted volumes or bind mounts. If `--volume` build args are used, snapshot creation logs a warning.
- **GPU access**: Containers using GPU resources may have hardware-specific state that cannot be captured. A warning is logged.

When these configurations are detected during `create_snapshot()`, the provider logs a warning but proceeds with the snapshot. Users can inspect the warning in `mngr` logs.

## Testing Strategy

Tests follow the project conventions: unit tests in `*_test.py` files (same directory as code under test), integration/acceptance/release tests in `test_*.py` files. All tests use the shared fixtures (`temp_host_dir`, `temp_mngr_ctx`, `cg`, `plugin_manager`) from `conftest.py`.

### Test Fixtures

Docker-specific fixtures, defined in the test files themselves (following the Modal pattern):

- `docker_provider` -- Creates a `DockerProviderInstance` with a mocked `docker.DockerClient` for unit tests. Uses `model_construct()` to bypass Pydantic validation (same pattern as `make_modal_provider_with_mocks`).
- `real_docker_provider` -- Creates a `DockerProviderInstance` connected to a real Docker daemon for acceptance tests. Yields the instance and cleans up all containers/images on teardown.
- `docker_container` -- Creates a real Docker container with a unique name, yields it, and force-removes it on teardown. For integration tests that need a running container without the full provider lifecycle.

Helper functions:

- `make_docker_provider_with_mocks(mngr_ctx, instance_name)` -- Factory for unit test providers with mocked Docker client.
- `make_docker_provider_real(mngr_ctx, instance_name)` -- Factory for acceptance test providers with real Docker.
- `_make_host_record(host_id, host_name, ...)` -- Create a `HostRecord` for testing (same pattern as Modal).
- `_make_snapshot_record(name)` -- Create a `SnapshotRecord` for testing.

### Unit Tests

#### `backend_test.py`

Tests for `DockerProviderBackend` (follows `local/backend_test.py` pattern):

```
test_backend_name
    DockerProviderBackend.get_name() returns DOCKER_BACKEND_NAME ("docker")

test_backend_description
    get_description() returns a non-empty string containing "docker"

test_backend_build_args_help
    get_build_args_help() returns non-empty string documenting --cpu, --memory, etc.

test_backend_start_args_help
    get_start_args_help() returns non-empty string

test_backend_get_config_class
    get_config_class() returns DockerProviderConfig

test_build_provider_instance_returns_docker_provider_instance
    build_provider_instance() returns a DockerProviderInstance

test_build_provider_instance_with_custom_host_dir
    Custom host_dir in config is respected

test_build_provider_instance_uses_default_host_dir
    Default host_dir (/mngr) is used when not specified

test_build_provider_instance_uses_name
    Provider instance name is correctly set
```

#### `host_store_test.py`

Tests for `DockerHostStore` (the JSON file-based host record store):

```
test_write_and_read_host_record
    Write a HostRecord, read it back, verify all fields match

test_read_host_record_returns_none_for_nonexistent
    Reading a nonexistent host_id returns None

test_read_host_record_caching
    Second read returns cached result without re-reading file

test_delete_host_record
    Delete removes the JSON file and associated agent data directory

test_delete_host_record_nonexistent_is_noop
    Deleting a nonexistent record does not raise

test_list_all_host_records_empty
    Returns empty list when no records exist

test_list_all_host_records_returns_all_records
    Returns all stored host records

test_list_all_host_records_skips_corrupt_files
    Skips malformed JSON files with a warning rather than crashing

test_persist_agent_data
    Writes agent data JSON under hosts/<host_id>/<agent_id>.json

test_persist_agent_data_without_id_is_noop
    Agent data missing "id" field does not write anything

test_list_persisted_agent_data_for_host
    Returns all agent data dicts for a given host

test_list_persisted_agent_data_for_host_empty
    Returns empty list when no agent data exists

test_remove_persisted_agent_data
    Removes the agent JSON file

test_remove_persisted_agent_data_nonexistent_is_noop
    Removing nonexistent agent data does not raise

test_host_record_store_directory_structure
    Verify the store creates the expected directory layout under the profile dir

test_write_host_record_creates_parent_dirs
    Writing a record to a fresh store creates all necessary parent directories
```

#### `instance_test.py`

Tests for `DockerProviderInstance` (follows `modal/instance_test.py` pattern):

**Capability properties (no Docker required):**

```
test_docker_provider_name
    provider.name matches the configured ProviderInstanceName

test_docker_provider_supports_snapshots
    supports_snapshots is True

test_docker_provider_supports_shutdown_hosts
    supports_shutdown_hosts is True

test_docker_provider_does_not_support_volumes
    supports_volumes is False

test_docker_provider_does_not_support_mutable_tags
    supports_mutable_tags is False

test_list_volumes_returns_empty_list
    list_volumes() returns []
```

**Container label helpers (no Docker required):**

```
test_build_container_labels_with_no_tags
    Labels include host-id, host-name, provider; tags label is "{}"

test_build_container_labels_with_tags
    Tags are JSON-encoded in the com.imbue.mngr.tags label

test_parse_container_labels_extracts_host_id_and_name
    Extracts HostId, HostName, and provider name from labels

test_parse_container_labels_extracts_tags
    Parses the tags JSON label back to a dict

test_build_and_parse_container_labels_roundtrip
    Build labels then parse them; all values match originals

test_parse_container_labels_handles_missing_tags_label
    Missing tags label returns empty dict (backward compatibility)

test_parse_container_labels_handles_invalid_tags_json
    Invalid JSON in tags label returns empty dict with warning
```

**Build args parsing (no Docker required):**

```
test_parse_build_args_empty
    None or [] returns ContainerConfig with defaults from provider config

test_parse_build_args_key_value_format
    Parses cpu=2, memory=8, gpu=nvidia format

test_parse_build_args_flag_equals_format
    Parses --cpu=2, --memory=8, --gpu=nvidia format

test_parse_build_args_flag_space_format
    Parses --cpu 2, --memory 8 format (two separate args)

test_parse_build_args_mixed_formats
    Parses mixed key=value and --flag formats in same call

test_parse_build_args_image
    Parses --image=python:3.11-slim

test_parse_build_args_dockerfile
    Parses --dockerfile=/path/to/Dockerfile

test_parse_build_args_context_dir
    Parses --context-dir=/path/to/context

test_parse_build_args_network
    Parses --network=my-network

test_parse_build_args_volume_single
    Parses single --volume=/host:/container

test_parse_build_args_volume_multiple
    Parses multiple --volume args; collected as tuple

test_parse_build_args_port_single
    Parses single --port=8080:80

test_parse_build_args_port_multiple
    Parses multiple --port args; collected as tuple

test_parse_build_args_unknown_raises_error
    Unknown arg like --foobar raises MngrError

test_parse_build_args_invalid_type_raises_error
    Non-numeric value for --cpu raises MngrError

test_parse_build_args_uses_config_default_gpu
    When config.default_gpu is set, empty build_args uses it

test_parse_build_args_uses_config_default_image
    When config.default_image is set, empty build_args uses it

test_parse_build_args_explicit_args_override_config_defaults
    Explicit --gpu overrides config.default_gpu
```

**Tag methods (no Docker required):**

```
test_set_host_tags_raises_mngr_error
    set_host_tags() raises MngrError with "does not support mutable tags"

test_add_tags_to_host_raises_mngr_error
    add_tags_to_host() raises MngrError with "does not support mutable tags"

test_remove_tags_from_host_raises_mngr_error
    remove_tags_from_host() raises MngrError with "does not support mutable tags"

test_get_host_tags_reads_from_container_labels
    Mocked container returns labels; get_host_tags parses the tags label

test_get_host_tags_falls_back_to_host_record_for_offline_host
    When container is not found, reads tags from host record's certified_host_data
```

**Shutdown script generation (no Docker required):**

```
test_create_shutdown_script_generates_correct_content
    Script contains #!/bin/bash, kill -TERM 1, LOG_FILE, STOP_REASON

test_create_shutdown_script_is_executable
    Script is written with mode 755
```

**list_hosts unit tests (mocked Docker client):**

```
test_list_hosts_returns_running_containers_as_hosts
    Mocked containers.list returns containers; list_hosts returns Host objects

test_list_hosts_returns_stopped_containers_as_offline_hosts
    Stopped containers (status=exited) returned as OfflineHost

test_list_hosts_merges_containers_with_host_records
    Running container takes precedence over host record for same host_id

test_list_hosts_returns_host_record_only_hosts
    Host records without matching containers still appear (destroyed but recorded)

test_list_hosts_excludes_destroyed_hosts_by_default
    Host records with no snapshots and no container are excluded by default

test_list_hosts_includes_destroyed_hosts_when_requested
    include_destroyed=True includes host records with no container and no snapshots

test_list_hosts_filters_by_provider_label
    Only containers with matching com.imbue.mngr.provider label are returned
```

**Agent data persistence (no Docker required):**

```
test_persist_agent_data_writes_to_host_store
    Calls host_store.persist_agent_data with correct args

test_persist_agent_data_without_id_is_noop
    Agent data without "id" field does not call host_store

test_remove_persisted_agent_data_removes_from_store
    Calls host_store.remove_persisted_agent_data

test_remove_persisted_agent_data_handles_not_found
    Missing agent data does not raise

test_list_persisted_agent_data_for_host_delegates_to_store
    Returns data from host_store.list_persisted_agent_data_for_host
```

### Integration Tests (`test_docker_lifecycle.py`)

These tests require a running Docker daemon but do NOT use the `mngr` CLI. They test the provider instance methods directly with real Docker containers. Each test cleans up its containers on teardown.

```
test_create_host_creates_container_with_ssh
    create_host() creates a running container, sets up SSH, returns a Host with
    a working SSH connector. Verify: container is running, SSH port is mapped,
    host.execute_command("echo hello") succeeds.

test_create_host_with_tags
    create_host(tags={"env": "test"}) stores tags in container labels.
    Verify: container labels include com.imbue.mngr.tags with {"env": "test"}.
    get_host_tags() returns {"env": "test"}.

test_create_host_with_custom_image
    create_host(build_args=["--image=python:3.11-slim"]) uses the specified image.
    Verify: container.image matches, python3 is available via SSH.

test_create_host_with_dockerfile
    create_host(build_args=["--dockerfile=<path>"]) builds a custom image.
    Verify: marker file from Dockerfile exists in the container.

test_create_host_with_resource_limits
    create_host(build_args=["--cpu=2", "--memory=2"]) applies resource limits.
    Verify: get_host_resources() returns matching values.

test_stop_host_stops_container
    stop_host() stops the container (not removes). Verify: container status is
    "exited", SSH no longer works.

test_stop_host_with_snapshot
    stop_host(create_snapshot=True) commits the container before stopping.
    Verify: snapshot appears in list_snapshots().

test_start_host_restarts_stopped_container
    After stop_host(), start_host() restarts the same container. Verify: SSH
    reconnects, filesystem changes from before stop are preserved.

test_start_host_filesystem_preserved_across_stop_start
    Write a marker file, stop, start. Verify: marker file still exists. This
    is a key difference from Modal, where stop always means snapshot-restore.

test_start_host_from_snapshot_creates_new_container
    After stop, start_host(snapshot_id=...) creates a NEW container from the
    committed image. Verify: marker file from snapshot is present, the container
    is a different container (different container_id).

test_start_host_on_running_host_returns_same_host
    start_host() on an already-running host returns the same host without error.

test_destroy_host_removes_container
    destroy_host() force-removes the container. Verify: container no longer
    exists, get_host() raises HostNotFoundError.

test_destroy_host_with_delete_snapshots
    destroy_host(delete_snapshots=True) removes both the container and its
    snapshot images.

test_destroy_host_without_delete_snapshots
    destroy_host(delete_snapshots=False) removes the container but preserves
    snapshot images.

test_get_host_by_id
    create_host(), then get_host(host_id). Verify: returns matching host.

test_get_host_by_name
    create_host(name), then get_host(name). Verify: returns matching host.

test_get_host_not_found_raises_error
    get_host(random_id) raises HostNotFoundError.

test_get_host_by_name_not_found_raises_error
    get_host(HostName("nonexistent")) raises HostNotFoundError.

test_list_hosts_includes_created_host
    create_host(), then list_hosts(). Verify: host appears in list.

test_list_hosts_includes_stopped_hosts
    create_host(), stop_host(), list_hosts(). Verify: stopped host appears as
    OfflineHost with appropriate state.

test_get_host_resources
    Verify get_host_resources() returns cpu/memory matching build args.

test_create_snapshot
    create_snapshot() commits the container and returns a SnapshotId.
    Verify: the committed image exists, list_snapshots() includes it.

test_create_and_list_snapshots
    Create multiple snapshots with names. list_snapshots() returns all with
    correct names and ordering.

test_delete_snapshot
    Create a snapshot, delete it. Verify: list_snapshots() is empty,
    Docker image has been removed.

test_delete_nonexistent_snapshot_raises_error
    delete_snapshot(fake_id) raises SnapshotNotFoundError.

test_get_host_tags_returns_creation_tags
    create_host(tags={"k": "v"}). get_host_tags() returns {"k": "v"}.

test_set_host_tags_raises_mngr_error
    set_host_tags() raises MngrError. Verify error message mentions immutable.

test_add_tags_to_host_raises_mngr_error
    add_tags_to_host() raises MngrError.

test_remove_tags_from_host_raises_mngr_error
    remove_tags_from_host() raises MngrError.

test_rename_host
    rename_host(host, new_name). Verify: get_host(new_name) works, the container
    name is unchanged (only the logical name in host record changes).

test_get_connector_returns_ssh_connector
    get_connector() returns a PyinfraHost with SSHConnector.

test_on_connection_error_clears_caches
    Verify on_connection_error(host_id) clears internal caches so the next
    get_host() fetches fresh state.

test_create_host_failure_records_failed_host
    Force a failure during container creation (e.g., bad image). Verify: the
    failed host record is saved and appears in list_hosts() with failure info.

test_snapshot_warns_on_volume_mounts
    create_host with --volume, then create_snapshot(). Verify: a warning is
    logged about volumes not being captured.

test_close_closes_docker_client
    close() closes the underlying Docker client connection.
```

### Acceptance Tests (`test_docker_create.py`)

End-to-end tests that use the `mngr` CLI as a subprocess, verifying the full user-facing flow. Marked with `@pytest.mark.acceptance`. Each test requires a running Docker daemon.

```
@pytest.mark.acceptance
test_mngr_create_echo_command_on_docker
    Run `uv run mngr create <name> echo --in docker --no-connect --await-ready -- hello`.
    Verify: exit code 0, "Done." in stdout.

@pytest.mark.acceptance
test_mngr_create_with_build_args_on_docker
    Run `uv run mngr create ... --in docker -b --cpu -b 2 -b --memory -b 2 -- hello`.
    Verify: exit code 0.

@pytest.mark.acceptance
test_mngr_create_with_dockerfile_on_docker
    Create a Dockerfile with a marker file. Run `uv run mngr create ... --in docker
    -b --dockerfile=<path> -- cat /marker.txt`. Verify: exit code 0.

@pytest.mark.acceptance
test_mngr_create_with_failing_dockerfile_shows_build_failure
    Create a Dockerfile with `RUN exit 1`. Run mngr create. Verify: non-zero
    exit code, build failure is visible in output.

@pytest.mark.acceptance
test_mngr_create_with_tags_on_docker
    Run `uv run mngr create ... --in docker --tag env=test -- echo hello`.
    Verify: exit code 0, `mngr list --format json` shows the tags.

@pytest.mark.acceptance
test_mngr_create_with_worktree_flag_on_docker_raises_error
    Run `uv run mngr create ... --in docker --worktree`. Verify: non-zero exit,
    error about worktree mode not being supported on remote providers.

@pytest.mark.acceptance
test_mngr_create_transfers_git_repo
    Use temp_git_repo fixture. Run mngr create with --source pointing to the
    git repo. Verify: exit code 0, agent created successfully.
```

### Release Tests (`test_docker_create.py`)

Slower, more comprehensive tests that run only on pushes to main.

```
@pytest.mark.release
test_mngr_create_stop_start_destroy_lifecycle
    Full lifecycle via CLI: create agent, verify running; stop it via
    `mngr stop`, verify stopped in `mngr list`; start it via `mngr start`,
    verify running again; destroy via `mngr destroy`, verify gone.

@pytest.mark.release
test_mngr_create_snapshot_and_restore
    Create agent, write a marker file, create snapshot, stop, restore from
    snapshot, verify marker file exists on restored host.
```

## Implementation Order

The implementation should proceed in this order, with each step producing a working (testable) increment:

1. **Shared SSH utilities refactoring**: Move SSH utilities from `modal/ssh_utils.py` to `providers/ssh_utils.py`. Update Modal imports. All existing tests must pass.

2. **Host record store (`host_store.py`)**: Implement the JSON file-based host record store with full CRUD operations. Unit test thoroughly.

3. **Config expansion (`config.py`)**: Add all configuration fields to `DockerProviderConfig`.

4. **Backend (`backend.py`)**: Implement `DockerProviderBackend` with the hookimpl registration.

5. **Instance core lifecycle (`instance.py`)**: Implement `create_host()`, `stop_host()`, `start_host()`, `destroy_host()`, `close()`. This is the largest step and includes:
   - Docker client management
   - Container label management
   - SSH setup (reusing `ssh_host_setup.py` and the shared SSH utilities)
   - Build arg parsing
   - Shutdown script creation
   - Error handling

6. **Instance discovery (`instance.py`)**: Implement `get_host()`, `list_hosts()`, `get_host_resources()`.

7. **Instance snapshots (`instance.py`)**: Implement `create_snapshot()`, `list_snapshots()`, `delete_snapshot()`.

8. **Instance tags and mutation (`instance.py`)**: Implement tag reading (from labels), tag mutation error methods, `rename_host()`, `get_connector()`.

9. **Instance agent data persistence (`instance.py`)**: Implement `list_persisted_agent_data_for_host()`, `persist_agent_data()`, `remove_persisted_agent_data()`.

10. **Integration and acceptance tests**: Full end-to-end testing with a real Docker daemon.

## Comparison with Modal Provider

| Aspect | Modal | Docker |
|--------|-------|--------|
| Container runtime | Modal sandbox | Docker container |
| SSH access | sshd in sandbox, tunneled port | sshd in container, mapped port |
| Host record storage | Modal Volume (remote) | Local JSON files |
| Discovery | Sandbox.list() with tags | containers.list() with label filters |
| Snapshots | sandbox.snapshot_filesystem() | docker commit |
| Stop/Start | Terminate + recreate from snapshot | Native docker stop/start |
| Shutdown mechanism | Curl to deployed Modal function | Kill PID 1 (SIGTERM) |
| Remote access | Always (cloud) | Via DOCKER_HOST or ssh:// URL |
| Resource limits | Modal native | Docker --cpus, --memory, device_requests |
| Image build | Modal Image API | docker build |
| SDK | modal Python SDK | docker Python SDK |
| SSH key location | `~/.mngr/profiles/<p>/providers/modal/` | `~/.mngr/profiles/<p>/providers/docker/<name>/keys/` |
| SSH utilities | `modal/ssh_utils.py` (to be shared) | Shared `providers/ssh_utils.py` |
| Setup commands | `ssh_host_setup.py` (shared) | `ssh_host_setup.py` (shared) |

## Design Decisions and Rationale

### Why SSH instead of `docker exec`?

The rest of mngr (provisioning, file sync, agent management) is built around pyinfra's SSH connector. Using SSH for Docker containers means all existing functionality works without modification. `docker exec` would require a separate code path for every operation.

### Why a local file store in addition to Docker labels?

Docker container labels are immutable after creation. Host records need to be updated (snapshots added, certified data updated). A local file store provides the mutability needed for these fields while Docker labels provide efficient discovery and store immutable identity metadata and tags. Tags are intentionally immutable on Docker -- this avoids the complexity of keeping external state in sync with the container lifecycle. Labels are atomic with the container: if the container exists, so do its labels; if the container is destroyed, the labels are gone. Labels are also preserved across `docker stop`/`docker start` and included in committed images (`docker commit`), so they survive snapshot/restore cycles automatically.

### Why not Docker volumes for host record storage?

Docker volumes are tied to the Docker daemon and would not survive daemon migration. The local file store lives on the mngr machine, which is the natural location for mngr state. Additionally, Docker volumes add complexity (creation, mounting, cleanup) without clear benefit over simple file I/O.

### Why override the container entrypoint?

User images may have entrypoints that exit immediately or do other things. The Docker provider needs a long-running PID 1 that handles SIGTERM for clean shutdown. Overriding the command ensures consistent behavior regardless of the base image.

### Why re-run SSH setup on `start_host()`?

Docker's `docker stop` sends SIGTERM to PID 1, which terminates all processes including sshd. When the container is restarted with `docker start`, PID 1 restarts but sshd does not. The SSH keys and configuration are preserved in the filesystem, but sshd must be explicitly restarted. The full SSH setup is re-run for robustness (it is idempotent).
