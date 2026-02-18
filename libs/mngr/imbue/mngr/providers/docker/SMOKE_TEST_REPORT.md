# Docker Provider Smoke Test Report

Date: 2026-02-18

## Summary

All Docker provider functionality has been smoke tested and is working correctly.
No bugs were found in the Docker provider implementation.

## Test Results

### Existing Test Suites (all passing)

- **Unit tests** (46 tests): All pass. Tests cover data types, labels, config, SSH
  host extraction, docker run command building.
- **Integration tests** (27 tests): All pass against real Docker daemon. Tests cover
  container creation/labels, discovery by ID/name, exec, image pull/build, stop/start,
  snapshots, host store, tags, DockerVolume operations.
- **Lifecycle tests** (26 acceptance + 7 release tests): All pass. Tests cover
  create_host with SSH, tags, custom images, resource limits; stop/start; filesystem
  persistence; destroy; get_host by ID/name; list_hosts; snapshots (create/delete/restore);
  immutable tags; rename; agent data persistence; Dockerfile builds.
- **CLI tests** (4 acceptance + 1 release): All pass. Tests cover `mngr create --in docker`
  with echo commands, start args, tags, Dockerfiles, and full lifecycle.
- **Full monorepo** (2242 tests): All pass, 81.13% coverage.

### Manual CLI Smoke Tests (all passing)

1. **`mngr create --in docker`**: Creates a Docker container host, installs packages,
   sets up SSH, copies work directory, starts tmux session. Works with both plain
   directories and git repos.

2. **`mngr list`**: Docker agents appear correctly with state (WAITING/STOPPED),
   host name, provider (docker), and labels.

3. **`mngr stop`**: Stops agent tmux sessions inside the container. Container
   remains running (agent stop != host stop).

4. **`mngr start`**: Restarts stopped agents, re-creates tmux sessions.

5. **`mngr destroy --force`**: Destroys agents, garbage-collects Docker containers,
   removes host records and volume directories.

6. **Host volume persistence**: Verified that `/mngr` inside the container is a
   symlink to `/mngr-state/volumes/<host-id>`, and data written there persists
   across stop/start cycles. The state volume (`/mngr-state`) contains both
   `host_state/` (host records) and `volumes/` (per-host persistent data).

7. **SSH connectivity**: SSH is properly configured with generated keypairs.
   Commands can be executed remotely via pyinfra after host creation.

8. **Package installation**: Required packages (openssh-server, tmux, curl, rsync,
   git, jq) are correctly detected as missing and installed at runtime when using
   the default `debian:bookworm-slim` image.

## Architecture Observations

The implementation follows the same SSH-based architecture as the Modal provider,
which gives good code reuse via shared utilities in `ssh_utils.py` and
`ssh_host_setup.py`.

Key design decisions that work well:
- State container pattern (singleton Alpine container for metadata) avoids needing
  a database while allowing multi-client access.
- Container labels for discovery enable fast lookups without scanning the state volume.
- Host volume symlink pattern keeps data accessible even when the container is stopped.
- Shared SSH host key across containers simplifies known_hosts management.

## Not Tested (out of scope per instructions)

- Snapshot functionality (create/restore from snapshots via CLI)
- Remote Docker daemon (`host` config pointing to ssh:// or tcp:// endpoints)
- GPU passthrough (`--gpus` start arg)
- Custom Dockerfile builds through the CLI (tested at API level only)
