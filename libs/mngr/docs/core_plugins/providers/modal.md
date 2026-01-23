# Modal Provider

The Modal provider creates agents in [Modal](https://modal.com) sandboxes. Each sandbox runs sshd and is accessed via SSH.

## Usage

```bash
mngr create my-agent --in modal
```

## Build Arguments

Build arguments configure the Modal sandbox. Pass them using `-b` or `--build-args`:

```bash
# Key-value format (recommended)
mngr create my-agent --in modal -b gpu=h100 -b cpu=2 -b memory=8

# Flag format (also supported)
mngr create my-agent --in modal -b --gpu=h100 -b --cpu=2

# Bulk format
mngr create my-agent --in modal --build-args "gpu=h100 cpu=2 memory=8"
```

### Available Build Arguments

| Argument | Description | Default |
|----------|-------------|---------|
| `gpu` | GPU type (e.g., `h100`, `a100`, `t4`) | None |
| `cpu` | Number of CPU cores | 1.0 |
| `memory` | Memory in GB | 1.0 |
| `image` | Base container image | debian:bookworm-slim |
| `timeout` | Sandbox timeout in seconds | 900 (15 minutes) |

### Examples

```bash
# Create with an H100 GPU
mngr create my-agent --in modal -b gpu=h100

# Create with more resources
mngr create my-agent --in modal -b cpu=4 -b memory=16

# Create with custom image and longer timeout
mngr create my-agent --in modal -b image=python:3.11-slim -b timeout=3600
```

## Snapshots

The Modal provider supports snapshots via Modal's `sandbox.snapshot_filesystem()` API. Snapshots capture the complete filesystem state and allow restoration after sandbox termination.

```bash
# Create a snapshot
mngr snapshot create my-agent

# List snapshots
mngr snapshot list my-agent

# Restore from snapshot
mngr start my-agent --snapshot snapshot-name
```

Snapshot metadata is persisted on a Modal Volume, allowing snapshots to survive sandbox termination and be shared across mngr installations.

## Limitations

- Sandboxes have a maximum lifetime (timeout) after which they are automatically terminated by Modal
- Sandboxes cannot be stopped and resumed - they can only be terminated
- Volumes (persistent storage) are not supported

## TODOs

- Document `--dockerfile` build argument for custom Dockerfile-based images
- Document host tag management capabilities (get/set/add/remove tags)
- Document host renaming functionality
- Add examples for snapshot workflows
- Add troubleshooting section for common Modal authentication issues
