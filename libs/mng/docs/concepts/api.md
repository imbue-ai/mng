# mng API

The following methods are available for plugins:

| Function                     | Description                                                                                                                                                |
|------------------------------|------------------------------------------------------------------------------------------------------------------------------------------------------------|
| `register_agent_type`        | Register a new agent type (e.g., `claude`, `codex`, `opencode`)                                                                                            |
| `register_provider_backend`  | Register a new provider backend (e.g., cloud platforms)                                                                                                    |
| `register_cli_commands`      | Define an entirely new CLI command                                                                                                                         |
| `register_cli_options`       | Add custom CLI options to any existing command's schema so that they appear in `--help`                                                                    |
| `override_command_options`   | Override or modify command options after CLI parsing and config defaults, but before the command options object is created                                 |
