# Plugins

Plugins extend `mngr` with new agent types, providers, commands, and behaviors. They're Python packages using the [pluggy](https://pluggy.readthedocs.io/) framework.

## Managing Plugins

Only install plugins from sources you trust. Built-in plugins are maintained as part of mngr itself.

```bash
mngr plugin list              # Show installed plugins
mngr plugin add <name>        # Install a plugin (pip/uv install) [future]
mngr plugin remove <name>     # Uninstall a plugin [future]
```

Plugins can be enabled/disabled without uninstalling:

```bash
mngr plugin enable modal             # Enable a plugin
mngr plugin disable modal            # Disable a plugin
mngr plugin disable modal --scope user  # Disable at user scope

# Or disable for a single command
mngr create --disable-plugin modal ...
```

## Hooks

Plugins register callbacks for various events, organized into a few different categories:

### Program lifecycle hooks

Called at various points in the execution of any `mngr` command:

| Hook                       | Description                                                                                                                                             |
|----------------------------|---------------------------------------------------------------------------------------------------------------------------------------------------------|
| `on_post_install`          | Runs after the plugin is installed or upgraded. Good for setup tasks like prompting the user or downloading models.                                     |
| `on_load_config`           | Runs when loading the global config. Receives the current config dict and can modify it before use.                                                     |
| `on_validate_permissions`  | Runs when validating permissions. Should ensure that the correct environment variables and files are accessible. [future]                               |
| `on_startup`               | Runs when `mngr` starts up. Good for registering other callbacks. See [the `mngr` API](./api.md) for more details on registration hooks.                |
| `on_before_<command>`      | Runs before any command executes. One hook per command. Receives the parsed args. Can modify args or abort execution.                                   |
| `on_after_<command>`       | Runs after any command completes. One hook per command. Receives the args and result. Useful for logging, cleanup, or post-processing.                  |
| `override_command_options` | Called after argument parsing. Receives the command name and parsed args. Use this to validate or transform extended arguments before the command runs.|
| `on_before_custom_command` | Runs for custom commands defined by plugins. Receives the command name and parsed args. Can modify args or abort execution.                             |
| `on_after_custom_command`  | Runs after custom commands defined by plugins complete. Receives the command name, args, and result. Useful for logging, cleanup, or post-processing.   |
| `on_error`                 | Runs if any command raises an exception. Receives the args and exception. Good for custom error handling or reporting.                                  |
| `on_shutdown`              | Runs when `mngr` is shutting down. Good for cleaning up global state or resources.                                                                      |

Some commands expose additional hooks for finer-grained control. See the documentation of each command for details.

### Host lifecycle Hooks [future]

Except for `on_host_collected` (which is called by any command that observes a host), these are mostly called during `mngr create` and `mngr destroy` operations:

| Hook                          | Description                                                                         |
|-------------------------------|-------------------------------------------------------------------------------------|
| `on_host_collected`           | Called once per host (per command where we collect this host.)                      |
| `on_before_host_create`       | Before creating a host                                                              |
| `on_after_host_create`        | After all steps have been completed to create a host                                |
| `on_before_machine_create`    | Before creating the underlying environment (machine, container, sandbox) for a host |
| `on_after_machine_create`     | After creating the underlying environment (machine, container, sandbox) for a host  |
| `on_host_state_dir_created`   | When creating the host's state directory                                            |
| `on_before_initial_file_copy` | Before copying files to a host                                                      |
| `on_after_initial_file_copy`  | After copying files to a host                                                       |
| `on_before_agent_creation`    | Before creating agents on a host                                                    |
| `on_after_agent_creation`     | After creating agents on a host                                                     |
| `on_before_apply_permissions` | Before applying permissions to a host                                               |
| `on_after_apply_permissions`  | After applying permissions to a host                                                |
| `on_before_provisioning`      | Before provisioning a host                                                          |
| `on_after_provisioning`       | After provisioning a host                                                           |
| `on_before_host_destroy`      | Before destroying a host                                                            |
| `on_after_host_destroy`       | After destroying a host                                                             |
| `get_offline_agent_state`     | Use this to provide state for an offline agent                                      |

Note that we cannot have callbacks for most host lifecycle events because they can happen outside the control of `mngr`. To implement such functionality, you should provision shell scripts into the appropriate location:

- `$MNGR_HOST_DIR/hooks/boot/`: runs when the host is booted. Blocks service startup until complete.
- `$MNGR_HOST_DIR/hooks/post_services/`: runs after services have been started. Blocks agent startup until complete.
- `$MNGR_HOST_DIR/hooks/stop/`: runs when the host is stopped. Blocks stopping until complete.

### Agent lifecycle Hooks [future]

These hooks can be used to customize behavior when interacting with individual agents:

| Hook                                | Description                                                                                           |
|-------------------------------------|-------------------------------------------------------------------------------------------------------|
| `on_agent_collected`                | Called once per agent (per command where we collect this agent.)                                      |
| `on_agent_created`                  | Called after an agent has been created                                                                 |
| `on_agent_state_dir_created`        | When creating the agent's state directory                                                             |
| `on_before_apply_agent_permissions` | Before applying permissions to an agent                                                               |
| `on_after_apply_agent_permissions`  | After applying permissions to an agent                                                                |
| `on_agent_destroyed`                | Called before an agent is destroyed                                                                    |

### Agent Provisioning Methods

Agent provisioning is handled through methods on the agent class itself, not hooks. This allows agent types to define their own provisioning behavior through inheritance:

| Method                        | Description                                                                                           |
|-------------------------------|-------------------------------------------------------------------------------------------------------|
| `on_before_provisioning()`    | Called before provisioning. Validate preconditions (env vars, required files). Raise on failure.      |
| `get_provision_file_transfers()` | Return file transfer specs (local_path, remote_path, is_required) for files to copy during provision. |
| `provision()`                 | Perform agent-type-specific provisioning (install packages, create configs, etc.)                     |
| `on_after_provisioning()`     | Called after all provisioning completes. Finalization and verification.                               |

To customize provisioning for a new agent type, subclass `BaseAgent` and override these methods. The `ClaudeAgent` class demonstrates this pattern.

If you want to run scripts *whenever* an agent is started (not just the first time), you can put a script in the following hook directory [future]:

- `$MNGR_AGENT_STATE_DIR/hooks/start/`: runs after an agent is started. Does not block in any way.

### Field Hooks [future]

Called when collecting data for hosts and agents. These allow plugins to compute additional attributes:

| Hook                       | Description                                                                                                                                     |
|----------------------------|-------------------------------------------------------------------------------------------------------------------------------------------------|
| `host_field_generators` | Return functions for computing additional fields for hosts (and their dependencies). Fields are namespaced under `host.plugin.<plugin_name>`.   |
| `agent_field_generators`   | Return functions for computing additional fields for agents (and their dependencies). Fields are namespaced under `plugin.<plugin_name>`.       |

**Dependency ordering:** The return types for the above hooks are complex: they should return structured types that express both the way of calculating the fields, and the dependencies for those calculations. This allows plugin A's fields to depend on values computed by plugin B.

## Built-in Plugins

`mngr` ships with built-in plugins for common agent types:

- **claude**: Claude Code with default configuration
- **code-guardian**: Claude Code with a skill for identifying code-level inconsistencies
- **codex**: OpenAI Codex integration

And for the basic provider backends:

- **local**: Local host backend
- **docker** [future]: Docker-based host backend
- **modal**: Modal cloud host backend
- **ssh**: SSH-based host backend (connects to pre-configured hosts)

Utility plugins [future] for additional features:

- **[local_port_forwarding_via_frp_and_nginx](../core_plugins/local_port_forwarding_via_frp_and_nginx.md)**: Expose services via frp and nginx
- **[default_url_for_cli_agents_via_ttyd](../core_plugins/default_url_for_cli_agents_via_ttyd.md)**: Web terminal access via ttyd
- **[user_activity_tracking_via_web](../core_plugins/user_activity_tracking_via_web.md)**: Track user activity in web interfaces
- **recursive_modal**: Allow recursive invocations of modal agents
- **recursive_mngr**: Allow invocation of mngr itself from within an agent
- **[offline_mngr_state](../core_plugins/offline_mngr_state.md)**: Cache mngr state for use when a host is offline
- **chat_history**: Persistent, globally accessible chat history

These are enabled by default but can be disabled like any other plugin.

## Plugin Dependencies

Plugins are Python packages and use standard dependency management. A plugin can depend on other plugins by listing them as package dependencies.
