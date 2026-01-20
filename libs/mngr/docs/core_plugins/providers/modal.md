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

## Limitations

- Sandboxes have a maximum lifetime (timeout) after which they are automatically terminated by Modal
- Sandboxes cannot be stopped and resumed - they can only be terminated
- Snapshots are not currently supported (planned for future)
