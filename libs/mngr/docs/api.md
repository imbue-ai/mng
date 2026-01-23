# mngr API

The following methods are available for plugins:

| Function                  | Description                                                                                                                                                   |
|---------------------------|---------------------------------------------------------------------------------------------------------------------------------------------------------------|
| `register_agent_type`     | Register a new agent type (e.g., `claude`, `codex`, `opencode`)                                                                                               |
| `register_provider_backend`  | Register a new provider backend (e.g., cloud platforms)                                                                                                       |
| `register_provider`       | Register a new concrete provider of hosts                                                                                                                  |
| `register_custom_command` | Define an entirely new CLI command                                                                                                                            |
| `extend_command_schema`   | Add arguments to any existing command's schema so that they appear in `--help`. Be sure to register a hook via `process_command_args` to handle the new args. |

## TODOs

The following API functions are documented above but not yet implemented:

- `register_provider` - No hookspec or implementation exists (note: providers are currently registered via `register_provider_backend`)
- `register_custom_command` - Not implemented (note: `register_cli_commands()` hook exists but differs from documented API)
- `extend_command_schema` - Not implemented (note: `register_cli_options()` and `override_command_options()` hooks exist but differ from documented API)
