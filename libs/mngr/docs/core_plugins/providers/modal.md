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
| `region` | Region to run the sandbox in (e.g., `us-east`, `us-west`, `eu-west`) | auto |
| `context-dir` | Build context directory for Dockerfile COPY/ADD instructions | Dockerfile's directory |
| `secret` | Environment variable name to pass as a secret during image build (can be specified multiple times) | None |
| `block-network` | Block all network access from the sandbox | off |
| `cidr-allowlist` | Allow network access only to the specified CIDR range (can be specified multiple times, implies `block-network`) | None |

### Examples

```bash
# Create with an H100 GPU
mngr create my-agent --in modal -b gpu=h100

# Create with more resources
mngr create my-agent --in modal -b cpu=4 -b memory=16

# Create with custom image and longer timeout
mngr create my-agent --in modal -b image=python:3.11-slim -b timeout=3600

# Create with network blocked
mngr create my-agent --in modal -b block-network

# Create with network restricted to specific CIDR ranges
mngr create my-agent --in modal -b cidr-allowlist=203.0.113.0/24 -b cidr-allowlist=10.0.0.0/8
```

### Using Secrets During Image Build

The `secret` build argument allows passing environment variables as secrets to the image build process. This is useful for installing private packages or accessing authenticated resources during the Dockerfile build:

```bash
# Pass a single secret
mngr create my-agent --in modal -b dockerfile=./Dockerfile -b secret=NPM_TOKEN

# Pass multiple secrets
mngr create my-agent --in modal -b dockerfile=./Dockerfile -b secret=NPM_TOKEN -b secret=GITHUB_TOKEN
```

In your Dockerfile, access the secret using `--mount=type=secret`:

```dockerfile
FROM python:3.11-slim

# Install a private npm package using NPM_TOKEN
RUN --mount=type=secret,id=NPM_TOKEN \
    npm config set //registry.npmjs.org/:_authToken=$(cat /run/secrets/NPM_TOKEN) && \
    npm install -g @myorg/private-package

# Install a private pip package using GITHUB_TOKEN
RUN --mount=type=secret,id=GITHUB_TOKEN \
    pip install git+https://$(cat /run/secrets/GITHUB_TOKEN)@github.com/myorg/private-repo.git
```

## Snapshots

Modal sandboxes support filesystem snapshots for preserving state:

```bash
# Create a snapshot
mngr snapshot create my-host

# List snapshots
mngr snapshot list my-host

# Start from a snapshot (restores the sandbox state)
mngr start my-host --snapshot <snapshot-id>
```

Snapshots are stored as Modal images and persist even after the sandbox is terminated.

## Limitations

- Sandboxes have a maximum lifetime (timeout) after which they are automatically terminated by Modal. It is useful as a hard restriction on agent lifetime, but cannot be longer than 24 hours (currently)
- Sandboxes cannot be stopped and resumed directly. Instead, snapshots are used to preserve state before termination. Snapshots are taken periodically
