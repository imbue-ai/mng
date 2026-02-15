# Docker Provider

The Docker provider creates agents in Docker containers with SSH access. Each container runs sshd and is accessed via pyinfra's SSH connector, following the same pattern as the Modal provider.

## Usage

```bash
mngr create my-agent --in docker
```

## Build Arguments

Build arguments configure the Docker container. Pass them using `-b` or `--build-args`:

```bash
# Key-value format (recommended)
mngr create my-agent --in docker -b cpu=2 -b memory=4

# Flag format (also supported)
mngr create my-agent --in docker -b --cpu=2 -b --memory=4

# Bulk format
mngr create my-agent --in docker --build-args "cpu=2 memory=4"
```

### Available Build Arguments

| Argument | Description | Default |
|----------|-------------|---------|
| `cpu` | Number of CPU cores | 1.0 |
| `memory` | Memory in GB | 1.0 |
| `gpu` | GPU access (e.g., `all`, `0`, `nvidia`) | None |
| `image` | Base Docker image | debian:bookworm-slim |
| `dockerfile` | Path to Dockerfile for custom image build | None |
| `context-dir` | Build context directory for Dockerfile | Dockerfile's directory |
| `network` | Docker network to attach to | bridge |
| `volume` | Additional volume mount (host:container[:mode]). Can be repeated | None |
| `port` | Additional port mapping (host:container). Can be repeated | None |

### Examples

```bash
# Create with more resources
mngr create my-agent --in docker -b cpu=4 -b memory=16

# Create with GPU access
mngr create my-agent --in docker -b gpu=all

# Create with a custom image
mngr create my-agent --in docker -b image=python:3.11-slim

# Create with a custom Dockerfile
mngr create my-agent --in docker -b dockerfile=./Dockerfile

# Create with a volume mount
mngr create my-agent --in docker -b volume=/host/data:/container/data
```

## Snapshots

Docker containers support snapshots via `docker commit`:

```bash
# Create a snapshot
mngr snapshot create my-host

# List snapshots
mngr snapshot list my-host

# Start from a snapshot (creates a new container from the committed image)
mngr start my-host --snapshot <snapshot-id>
```

Snapshots capture the container's filesystem layers. Volume mounts are not included in snapshots.

## Stop and Start

Unlike Modal, Docker supports native stop/start. Stopping a container preserves its filesystem state:

```bash
# Stop a container (filesystem is preserved)
mngr stop my-host

# Start the stopped container (filesystem state is restored)
mngr start my-host
```

## Tags

Tags are stored as Docker container labels and are immutable after creation. Set tags when creating a host:

```bash
mngr create my-agent --in docker --tag env=test --tag team=infra
```

Attempting to modify tags after creation will produce an error.

## Configuration

Configure the Docker provider in your mngr config file:

```toml
[providers.docker]
backend = "docker"
host = ""                    # Docker host URL (empty = local daemon)
default_image = "debian:bookworm-slim"
default_cpu = 1.0
default_memory = 1.0
default_idle_timeout = 800
network = ""                 # Docker network name
```

Set `host` to connect to a remote Docker daemon (e.g., `ssh://user@server` or `tcp://host:2376`).

## Limitations

- Tags are immutable after container creation (stored as Docker labels)
- Volume mounts are not captured in snapshots
- Docker volumes are managed externally; the provider does not support volume lifecycle management
