# Architecture

## Overview

`mngr` provides a CLI for managing AI [agents](./concepts/agents.md). Multiple agents can run on a single [host](./concepts/hosts.md).

[Hosts](./concepts/hosts.md) are created by [providers](./concepts/providers.md).

Different [agent types](./concepts/agent_types.md) (Claude, Codex, etc.) and [provider backends](./concepts/provider_backends.md) can be defined via configuration or by [plugins](./concepts/plugins.md).

## Agent-centric state model

Agents fully contain their own state.

`mngr` itself has no persistent processes and stores almost no persistent state. Instead, everything is reconstructed from:

1. Queries to **providers** (which inspect Docker labels, Modal tags, local state files, etc.)
2. Queries to **hosts** (to answer "Is SSH responding?" and "Is the process alive?" and read state from the agent filesystem to understand the state of remote **agents**)
3. Configuration files (settings, enabled plugins, etc.)

This means no database, no state corruption, and multiple `mngr` instances can manage the same agents.

Some interactions are gated via cooperative locking (using `flock` on known lock files) to avoid race conditions. See [locking spec](../specs/locking.md) for details.

## Conventions

`mngr` relies on conventions to identify managed resources.

Prefixing a host, tmux session, or Docker container with `mngr-` is enough for `mngr` to recognize and manage it. This prefix can be customized via `MNGR_PREFIX`.

See the [conventions doc](./conventions.md) for full details.

## Responsibilities

mngr is responsible for:
- implementing the [core CLI commands](../README.md) (create, connect, stop, list, push, pull, pair, etc.)
- enforcing the [host lifecycle](./concepts/hosts.md#Lifecycle), including automatically stopping a host when all its agents are idle
- configuring/enabling/disabling [plugins](./concepts/plugins.md)
- handling [permissions](./concepts/permissions.md) for remote hosts
- detecting hangs and failures (via the [`mngr enforce` command](./commands/secondary/enforce.md))

## Multi-user support

`mngr` typically runs as a single user on a host (it stores its data at `~/.mngr/` by convention, for example).

While it's possible to run as multiple users (esp locally), no data is shared between different users on the same machine.
This means that, when connecting to remote hosts, we need to be careful to expand the "~" in paths only once we know the user that we are running as.

## TODOs

Features described above but not yet implemented:

- **CLI commands**: `stop`, `push`, `pair` (spec exists but no implementation)
- **Hang/failure detection**: `mngr enforce` command not implemented
- **Host lifecycle**: Auto-stop daemon/background process for idle enforcement
- **Provider backends**: Docker provider (spec exists, no implementation)
- **Permissions**: Enforcement/validation logic not fully wired to CLI
- **Locking**: Remote host locking not implemented (raises NotImplementedError)
