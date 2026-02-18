# mngr API

The following methods are available for plugins:

| Function                     | Description                                                                                                                                                |
|------------------------------|------------------------------------------------------------------------------------------------------------------------------------------------------------|
| `register_agent_type`        | Register a new agent type (e.g., `claude`, `codex`, `opencode`)                                                                                            |
| `register_provider_backend`  | Register a new provider backend (e.g., cloud platforms)                                                                                                    |
| `register_cli_commands`      | Define an entirely new CLI command                                                                                                                         |
| `register_cli_options`       | Add custom CLI options to any existing command's schema so that they appear in `--help`                                                                    |
| `override_command_options`   | Override or modify command options after CLI parsing and config defaults, but before the command options object is created                                 |
| `on_load_config`             | Called when loading configuration, before final validation. Receives the current config dict and can modify it.                                            |
| `on_before_create` [future]  | Called at the start of `create()`, before any work is done                                                                                                 |
| `on_agent_created`           | Called after an agent has been created                                                                                                                      |
| `on_agent_destroyed` [future]| Called before an agent is destroyed                                                                                                                        |
| `on_host_created` [future]   | Called after a host has been created                                                                                                                       |
| `on_host_destroyed` [future] | Called before a host is destroyed                                                                                                                          |
