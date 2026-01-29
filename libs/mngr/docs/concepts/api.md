# mngr API

The following methods are available for plugins:

| Function                  | Description                                                                                                                                                   |
|---------------------------|---------------------------------------------------------------------------------------------------------------------------------------------------------------|
| `register_agent_type`     | Register a new agent type (e.g., `claude`, `codex`, `opencode`)                                                                                               |
| `register_provider_backend`  | Register a new provider backend (e.g., cloud platforms)                                                                                                       |
| `register_provider` [future]       | Register a new concrete provider of hosts (alternative: `register_provider_config` is available)                                                                                                                  |
| `register_custom_command` [future] | Define an entirely new CLI command (alternative: `register_cli_commands` is available)                                                                                                                            |
| `extend_command_schema` [future]   | Add arguments to any existing command's schema so that they appear in `--help`. Be sure to register a hook via `process_command_args` to handle the new args. (alternatives: `register_cli_options` and `override_command_options` are available) |

