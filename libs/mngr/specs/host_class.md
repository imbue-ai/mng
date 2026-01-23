# Host Class Spec

The `Host` class provides a minimal interface for executing operations on a running host. It wraps pyinfra's host abstraction, which exposes only three primitives: command execution, file reading, and file writing.

For the host data model (fields, storage locations, certified vs. reported data), see [host.md](./host.md).

## Design Philosophy

The Host class follows a deliberately minimal design:

- **Thin wrapper**: The class holds only a reference to the underlying pyinfra connector. No caching, no derived state, only a collection of convenience methods for accessing the properties of the host in terms of those three primitives.
- **Three primitives**: All host interactions reduce to `execute_command`, `read_file`, and `write_file`. Higher-level operations (activity detection, state queries, process management) are built elsewhere using these primitives.
- **Concrete class**: There are no different "types" of hosts. Local and remote hosts use the same interface—pyinfra handles the transport differences internally.
- **Stateless**: Each method call is independent. The class does not track command history, cache file contents, or maintain connection state beyond what pyinfra manages.

This design ensures that the Host class remains simple, testable, and easy to reason about.

## pyinfra Foundation

The Host class wraps a pyinfra connector. pyinfra handles transport differences (SSH for remote hosts, direct execution for local) so the Host class presents a uniform interface regardless of where the host runs.

| Transport | When Used | Notes |
|-----------|-----------|-------|
| `@local` | Local provider | Direct execution, no SSH |
| `@ssh` | Docker, Modal, remote providers | Requires SSH access |

The provider instance creates the appropriate pyinfra connector; the Host class wraps whatever connector it receives. See [pyinfra documentation](https://pyinfra.com/) for connector details.

## Interface Specification

### Construction

Like all of our classes, the Host class is a pydantic model.

In this case, it needs only a very small number of fields:

```python
id: HostId
connector: PyinfraHost
provider: ProviderInstance
```

**Notes:**
- The caller (typically a provider instance) is responsible for configuring SSH keys, ports, and other connection parameters in the pyinfra connector. If configured incorrectly, connection attempts will fail.
- Connection attempts can always fail at runtime (e.g., host unreachable, auth failure). This is one of the main reasons for the Host class existing at all: to encapsulate connection errors and provide a uniform error handling interface (ex: by retrying "get" calls).

### Methods

The Host class exposes methods for accessing host attributes. Methods fall into two categories:

1. **Primitive methods**: The three core operations that all other host interactions build upon.
2. **Convenience methods**: Higher-level operations that use the primitives to read/write specific host data.

Some host attributes (name, tags, limits, snapshots) are stored by the provider rather than on the host filesystem. For these, the Host class delegates to its `provider` reference rather than using the primitives.

## What the Host Class Does NOT Do

The Host class intentionally excludes:

- **Agent management**: Creating, starting, or stopping agents. Handled by higher-level mngr code using the Host primitives.
- **Provisioning**: Installing packages or configuring services. Handled by pyinfra operations using the Host as a target.
- **File sync**: Synchronizing files between local and remote. Handled by mngr commands.
- **Lifecycle management**: Creating, pausing, resuming, or destroying hosts. Handled by [ProviderInstance](./provider_instance.md).
- **Caching**: File contents and command results are not cached. Each method call queries the host fresh.
- **Connection pooling**: The class does not maintain persistent connections beyond what pyinfra manages.

## TODOs

The current implementation includes functionality that contradicts the minimal design philosophy:

- **Remove agent management methods**: `create_agent_work_dir`, `create_agent_state`, `provision_agent`, `destroy_agent`, `start_agents`, `stop_agents` should be moved to higher-level code that uses Host primitives
- **Remove provisioning logic**: The `provision_agent` method and related helpers (`_execute_agent_file_transfers`, `_append_to_file`, `_prepend_to_file`, `_run_sudo_command`, `_collect_agent_env_vars`, `_write_agent_env_file`) should be moved out of Host
- **Remove file sync operations**: File upload/transfer functionality in `provision_agent` should be handled by mngr commands
- **Remove agent-specific helpers**: Methods like `_build_env_shell_command`, `_create_host_tmux_config`, `_get_agent_by_id`, `_get_agent_command`, `_get_all_descendant_pids`, `_determine_branch_name` belong in higher-level agent management code
- **Evaluate additional functionality**: Activity management, cooperative locking, certified data, plugin state, environment variables, and tags methods are not described in this spec and should be documented or moved if they don't align with the minimal design philosophy
- **Rename provider field**: The implementation uses `provider_instance` but the spec describes `provider`
