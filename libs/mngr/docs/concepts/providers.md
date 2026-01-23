# Provider Instances

A **provider instance** creates and manages [hosts](./hosts.md). Each provider instance is a configured endpoint of a [provider backend](./provider_backends.md).

From the perspective of `[pyinfra](https://pyinfra.com/)` (the tool we suggest for [provisioning](./provisioning.md)), you can think of provider instances as "something that mutates the inventory" (eg, create, destroy, stop, start, etc.)

There are some built-in provider instances (`local` and `local_docker`), but you generally define your own in your `mngr` settings:

```toml
[[providers]]
name = "my-aws-prod"
backend = "aws"
region = "us-east-1"
profile = "production"

[[providers]]
name = "my-aws-dev"
backend = "aws"
region = "us-west-2"
profile = "development"

[[providers]]
name = "remote-docker"
backend = "docker"
host = "ssh://user@server"

[[providers]]
name = "team-mngr"
backend = "mngr"
url = "https://mngr.internal.company.com"
```

## Built-in Provider Instances

### local

A special provider instance that is always available. Runs agents directly on your machine with no isolation. Automatically available--no configuration required.

### local_docker

Runs agents in Docker containers on your local machine. Automatically available as long as `docker` is installed.

Provides container isolation while keeping everything local. Uses `docker` commands directly to manage containers.

## Responsibilities

Provider instances must handle:

- **Create** — Build images, allocate resources, start the host
- **Stop** — Stop the host, optionally create a snapshot
- **Start** — Restore from snapshot, restart the host
- **Destroy** — Clean up all resources associated with the host
- **Snapshot** — Capture filesystem state for backup/restore (optional, not supported by all providers)
- **List** — Discover all mngr-managed hosts
- **CLI args** — Register provider-specific flags (e.g., `--gpu`, `--memory`)

`mngr` handles higher-level concerns: agent lifecycle, idle detection, port forwarding, and file sync.

See [`imbue/mngr/interfaces/provider.py`](../../imbue/mngr/interfaces/provider.py) for the full provider interface.

## State Storage

Each provider instance stores its own state about the hosts it manages. This is typically accomplished via tags and other metadata.

This keeps `mngr` stateless (it reconstructs the necessary state for any given command by querying provider instances).

## TODOs

The following features described in this document are not yet implemented:

- **local_docker** built-in provider instance
- **AWS** provider backend (shown in configuration examples)
- **Docker** provider backend for remote Docker hosts
- **mngr** provider backend for remote mngr instances

Note: The **modal** provider backend is implemented but not documented here.
