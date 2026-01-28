# mngr

Initial entry point for mngr CLI commands.

Makes the plugin manager available in the command context.

**Usage:**

```text
mngr [OPTIONS] COMMAND [ARGS]...
```

**Options:**

| Name | Type | Description | Default |
| ---- | ---- | ----------- | ------- |
| `--version` | boolean | Show the version and exit. | `False` |
| `--help` | boolean | Show this message and exit. | `False` |

## config

Manage mngr configuration.

View, edit, and modify mngr configuration settings at the user, project,
or local scope.

Examples:

  mngr config list

  mngr config get prefix

  mngr config set --scope project commands.create.connect false

  mngr config unset commands.create.connect

  mngr config edit --scope user

**Usage:**

```text
mngr config [OPTIONS] COMMAND [ARGS]...
```

**Options:**

| Name | Type | Description | Default |
| ---- | ---- | ----------- | ------- |
| `--scope` | choice (`user` &#x7C; `project` &#x7C; `local`) | Config scope: user (~/.config/mngr/), project (.mngr/), or local (.mngr/settings.local.toml) | None |
| `--format` | choice (`human` &#x7C; `json` &#x7C; `jsonl`) | Output format for command results | `human` |
| `-q`, `--quiet` | boolean | Suppress all console output | `False` |
| `-v`, `--verbose` | integer range (`0` and above) | Increase verbosity (default: BUILD); -v for DEBUG, -vv for TRACE | `0` |
| `--log-file` | path | Path to log file (overrides default ~/.mngr/logs/<timestamp>-<pid>.json) | None |
| `--log-commands` / `--no-log-commands` | boolean | Log commands that were executed | None |
| `--log-command-output` / `--no-log-command-output` | boolean | Log stdout/stderr from commands | None |
| `--log-env-vars` / `--no-log-env-vars` | boolean | Log environment variables (security risk) | None |
| `--context` | path | Project context directory (for build context and loading project-specific config) [default: local .git root] | None |
| `--plugin`, `--enable-plugin` | text | Enable a plugin [repeatable] | None |
| `--disable-plugin` | text | Disable a plugin [repeatable] | None |
| `--help` | boolean | Show this message and exit. | `False` |

### edit

Open configuration file in editor.

Opens the configuration file for the specified scope in your default
editor (from $EDITOR or $VISUAL environment variable, or 'vi' as fallback).

If the config file doesn't exist, it will be created with an empty template.

Examples:

  mngr config edit

  mngr config edit --scope user

  mngr config edit --scope local

**Usage:**

```text
mngr config edit [OPTIONS]
```

**Options:**

| Name | Type | Description | Default |
| ---- | ---- | ----------- | ------- |
| `--scope` | choice (`user` &#x7C; `project` &#x7C; `local`) | Config scope: user (~/.config/mngr/), project (.mngr/), or local (.mngr/settings.local.toml) | `project` |
| `--format` | choice (`human` &#x7C; `json` &#x7C; `jsonl`) | Output format for command results | `human` |
| `-q`, `--quiet` | boolean | Suppress all console output | `False` |
| `-v`, `--verbose` | integer range (`0` and above) | Increase verbosity (default: BUILD); -v for DEBUG, -vv for TRACE | `0` |
| `--log-file` | path | Path to log file (overrides default ~/.mngr/logs/<timestamp>-<pid>.json) | None |
| `--log-commands` / `--no-log-commands` | boolean | Log commands that were executed | None |
| `--log-command-output` / `--no-log-command-output` | boolean | Log stdout/stderr from commands | None |
| `--log-env-vars` / `--no-log-env-vars` | boolean | Log environment variables (security risk) | None |
| `--context` | path | Project context directory (for build context and loading project-specific config) [default: local .git root] | None |
| `--plugin`, `--enable-plugin` | text | Enable a plugin [repeatable] | None |
| `--disable-plugin` | text | Disable a plugin [repeatable] | None |
| `--help` | boolean | Show this message and exit. | `False` |

### get

Get a configuration value.

Retrieves the value of a specific configuration key. Use dot notation
for nested keys (e.g., 'commands.create.connect').

Examples:

  mngr config get prefix

  mngr config get commands.create.connect

  mngr config get logging.console_level --scope user

**Usage:**

```text
mngr config get [OPTIONS] KEY
```

**Options:**

| Name | Type | Description | Default |
| ---- | ---- | ----------- | ------- |
| `--scope` | choice (`user` &#x7C; `project` &#x7C; `local`) | Config scope: user (~/.config/mngr/), project (.mngr/), or local (.mngr/settings.local.toml) | None |
| `--format` | choice (`human` &#x7C; `json` &#x7C; `jsonl`) | Output format for command results | `human` |
| `-q`, `--quiet` | boolean | Suppress all console output | `False` |
| `-v`, `--verbose` | integer range (`0` and above) | Increase verbosity (default: BUILD); -v for DEBUG, -vv for TRACE | `0` |
| `--log-file` | path | Path to log file (overrides default ~/.mngr/logs/<timestamp>-<pid>.json) | None |
| `--log-commands` / `--no-log-commands` | boolean | Log commands that were executed | None |
| `--log-command-output` / `--no-log-command-output` | boolean | Log stdout/stderr from commands | None |
| `--log-env-vars` / `--no-log-env-vars` | boolean | Log environment variables (security risk) | None |
| `--context` | path | Project context directory (for build context and loading project-specific config) [default: local .git root] | None |
| `--plugin`, `--enable-plugin` | text | Enable a plugin [repeatable] | None |
| `--disable-plugin` | text | Disable a plugin [repeatable] | None |
| `--help` | boolean | Show this message and exit. | `False` |

### list

List all configuration values.

Shows all configuration settings from the specified scope, or from the
merged configuration if no scope is specified.

Examples:

  mngr config list

  mngr config list --scope user

  mngr config list --format json

**Usage:**

```text
mngr config list [OPTIONS]
```

**Options:**

| Name | Type | Description | Default |
| ---- | ---- | ----------- | ------- |
| `--scope` | choice (`user` &#x7C; `project` &#x7C; `local`) | Config scope: user (~/.config/mngr/), project (.mngr/), or local (.mngr/settings.local.toml) | None |
| `--format` | choice (`human` &#x7C; `json` &#x7C; `jsonl`) | Output format for command results | `human` |
| `-q`, `--quiet` | boolean | Suppress all console output | `False` |
| `-v`, `--verbose` | integer range (`0` and above) | Increase verbosity (default: BUILD); -v for DEBUG, -vv for TRACE | `0` |
| `--log-file` | path | Path to log file (overrides default ~/.mngr/logs/<timestamp>-<pid>.json) | None |
| `--log-commands` / `--no-log-commands` | boolean | Log commands that were executed | None |
| `--log-command-output` / `--no-log-command-output` | boolean | Log stdout/stderr from commands | None |
| `--log-env-vars` / `--no-log-env-vars` | boolean | Log environment variables (security risk) | None |
| `--context` | path | Project context directory (for build context and loading project-specific config) [default: local .git root] | None |
| `--plugin`, `--enable-plugin` | text | Enable a plugin [repeatable] | None |
| `--disable-plugin` | text | Disable a plugin [repeatable] | None |
| `--help` | boolean | Show this message and exit. | `False` |

### path

Show configuration file paths.

Shows the paths to configuration files. If --scope is specified, shows
only that scope's path. Otherwise shows all paths and whether they exist.

Examples:

  mngr config path

  mngr config path --scope user

**Usage:**

```text
mngr config path [OPTIONS]
```

**Options:**

| Name | Type | Description | Default |
| ---- | ---- | ----------- | ------- |
| `--scope` | choice (`user` &#x7C; `project` &#x7C; `local`) | Config scope: user (~/.config/mngr/), project (.mngr/), or local (.mngr/settings.local.toml) | None |
| `--format` | choice (`human` &#x7C; `json` &#x7C; `jsonl`) | Output format for command results | `human` |
| `-q`, `--quiet` | boolean | Suppress all console output | `False` |
| `-v`, `--verbose` | integer range (`0` and above) | Increase verbosity (default: BUILD); -v for DEBUG, -vv for TRACE | `0` |
| `--log-file` | path | Path to log file (overrides default ~/.mngr/logs/<timestamp>-<pid>.json) | None |
| `--log-commands` / `--no-log-commands` | boolean | Log commands that were executed | None |
| `--log-command-output` / `--no-log-command-output` | boolean | Log stdout/stderr from commands | None |
| `--log-env-vars` / `--no-log-env-vars` | boolean | Log environment variables (security risk) | None |
| `--context` | path | Project context directory (for build context and loading project-specific config) [default: local .git root] | None |
| `--plugin`, `--enable-plugin` | text | Enable a plugin [repeatable] | None |
| `--disable-plugin` | text | Disable a plugin [repeatable] | None |
| `--help` | boolean | Show this message and exit. | `False` |

### set

Set a configuration value.

Sets a configuration value at the specified scope. Use dot notation
for nested keys (e.g., 'commands.create.connect').

Values are parsed as JSON if possible, otherwise as strings.
Use 'true'/'false' for booleans, numbers for integers/floats.

Examples:

  mngr config set prefix "my-"

  mngr config set commands.create.connect false

  mngr config set logging.console_level DEBUG --scope user

**Usage:**

```text
mngr config set [OPTIONS] KEY VALUE
```

**Options:**

| Name | Type | Description | Default |
| ---- | ---- | ----------- | ------- |
| `--scope` | choice (`user` &#x7C; `project` &#x7C; `local`) | Config scope: user (~/.config/mngr/), project (.mngr/), or local (.mngr/settings.local.toml) | `project` |
| `--format` | choice (`human` &#x7C; `json` &#x7C; `jsonl`) | Output format for command results | `human` |
| `-q`, `--quiet` | boolean | Suppress all console output | `False` |
| `-v`, `--verbose` | integer range (`0` and above) | Increase verbosity (default: BUILD); -v for DEBUG, -vv for TRACE | `0` |
| `--log-file` | path | Path to log file (overrides default ~/.mngr/logs/<timestamp>-<pid>.json) | None |
| `--log-commands` / `--no-log-commands` | boolean | Log commands that were executed | None |
| `--log-command-output` / `--no-log-command-output` | boolean | Log stdout/stderr from commands | None |
| `--log-env-vars` / `--no-log-env-vars` | boolean | Log environment variables (security risk) | None |
| `--context` | path | Project context directory (for build context and loading project-specific config) [default: local .git root] | None |
| `--plugin`, `--enable-plugin` | text | Enable a plugin [repeatable] | None |
| `--disable-plugin` | text | Disable a plugin [repeatable] | None |
| `--help` | boolean | Show this message and exit. | `False` |

### unset

Remove a configuration value.

Removes a configuration value from the specified scope. Use dot notation
for nested keys (e.g., 'commands.create.connect').

Examples:

  mngr config unset commands.create.connect

  mngr config unset logging.console_level --scope user

**Usage:**

```text
mngr config unset [OPTIONS] KEY
```

**Options:**

| Name | Type | Description | Default |
| ---- | ---- | ----------- | ------- |
| `--scope` | choice (`user` &#x7C; `project` &#x7C; `local`) | Config scope: user (~/.config/mngr/), project (.mngr/), or local (.mngr/settings.local.toml) | `project` |
| `--format` | choice (`human` &#x7C; `json` &#x7C; `jsonl`) | Output format for command results | `human` |
| `-q`, `--quiet` | boolean | Suppress all console output | `False` |
| `-v`, `--verbose` | integer range (`0` and above) | Increase verbosity (default: BUILD); -v for DEBUG, -vv for TRACE | `0` |
| `--log-file` | path | Path to log file (overrides default ~/.mngr/logs/<timestamp>-<pid>.json) | None |
| `--log-commands` / `--no-log-commands` | boolean | Log commands that were executed | None |
| `--log-command-output` / `--no-log-command-output` | boolean | Log stdout/stderr from commands | None |
| `--log-env-vars` / `--no-log-env-vars` | boolean | Log environment variables (security risk) | None |
| `--context` | path | Project context directory (for build context and loading project-specific config) [default: local .git root] | None |
| `--plugin`, `--enable-plugin` | text | Enable a plugin [repeatable] | None |
| `--disable-plugin` | text | Disable a plugin [repeatable] | None |
| `--help` | boolean | Show this message and exit. | `False` |

## config

Manage mngr configuration.

View, edit, and modify mngr configuration settings at the user, project,
or local scope.

Examples:

  mngr config list

  mngr config get prefix

  mngr config set --scope project commands.create.connect false

  mngr config unset commands.create.connect

  mngr config edit --scope user

**Usage:**

```text
mngr config [OPTIONS] COMMAND [ARGS]...
```

**Options:**

| Name | Type | Description | Default |
| ---- | ---- | ----------- | ------- |
| `--scope` | choice (`user` &#x7C; `project` &#x7C; `local`) | Config scope: user (~/.config/mngr/), project (.mngr/), or local (.mngr/settings.local.toml) | None |
| `--format` | choice (`human` &#x7C; `json` &#x7C; `jsonl`) | Output format for command results | `human` |
| `-q`, `--quiet` | boolean | Suppress all console output | `False` |
| `-v`, `--verbose` | integer range (`0` and above) | Increase verbosity (default: BUILD); -v for DEBUG, -vv for TRACE | `0` |
| `--log-file` | path | Path to log file (overrides default ~/.mngr/logs/<timestamp>-<pid>.json) | None |
| `--log-commands` / `--no-log-commands` | boolean | Log commands that were executed | None |
| `--log-command-output` / `--no-log-command-output` | boolean | Log stdout/stderr from commands | None |
| `--log-env-vars` / `--no-log-env-vars` | boolean | Log environment variables (security risk) | None |
| `--context` | path | Project context directory (for build context and loading project-specific config) [default: local .git root] | None |
| `--plugin`, `--enable-plugin` | text | Enable a plugin [repeatable] | None |
| `--disable-plugin` | text | Disable a plugin [repeatable] | None |
| `--help` | boolean | Show this message and exit. | `False` |

### edit

Open configuration file in editor.

Opens the configuration file for the specified scope in your default
editor (from $EDITOR or $VISUAL environment variable, or 'vi' as fallback).

If the config file doesn't exist, it will be created with an empty template.

Examples:

  mngr config edit

  mngr config edit --scope user

  mngr config edit --scope local

**Usage:**

```text
mngr config edit [OPTIONS]
```

**Options:**

| Name | Type | Description | Default |
| ---- | ---- | ----------- | ------- |
| `--scope` | choice (`user` &#x7C; `project` &#x7C; `local`) | Config scope: user (~/.config/mngr/), project (.mngr/), or local (.mngr/settings.local.toml) | `project` |
| `--format` | choice (`human` &#x7C; `json` &#x7C; `jsonl`) | Output format for command results | `human` |
| `-q`, `--quiet` | boolean | Suppress all console output | `False` |
| `-v`, `--verbose` | integer range (`0` and above) | Increase verbosity (default: BUILD); -v for DEBUG, -vv for TRACE | `0` |
| `--log-file` | path | Path to log file (overrides default ~/.mngr/logs/<timestamp>-<pid>.json) | None |
| `--log-commands` / `--no-log-commands` | boolean | Log commands that were executed | None |
| `--log-command-output` / `--no-log-command-output` | boolean | Log stdout/stderr from commands | None |
| `--log-env-vars` / `--no-log-env-vars` | boolean | Log environment variables (security risk) | None |
| `--context` | path | Project context directory (for build context and loading project-specific config) [default: local .git root] | None |
| `--plugin`, `--enable-plugin` | text | Enable a plugin [repeatable] | None |
| `--disable-plugin` | text | Disable a plugin [repeatable] | None |
| `--help` | boolean | Show this message and exit. | `False` |

### get

Get a configuration value.

Retrieves the value of a specific configuration key. Use dot notation
for nested keys (e.g., 'commands.create.connect').

Examples:

  mngr config get prefix

  mngr config get commands.create.connect

  mngr config get logging.console_level --scope user

**Usage:**

```text
mngr config get [OPTIONS] KEY
```

**Options:**

| Name | Type | Description | Default |
| ---- | ---- | ----------- | ------- |
| `--scope` | choice (`user` &#x7C; `project` &#x7C; `local`) | Config scope: user (~/.config/mngr/), project (.mngr/), or local (.mngr/settings.local.toml) | None |
| `--format` | choice (`human` &#x7C; `json` &#x7C; `jsonl`) | Output format for command results | `human` |
| `-q`, `--quiet` | boolean | Suppress all console output | `False` |
| `-v`, `--verbose` | integer range (`0` and above) | Increase verbosity (default: BUILD); -v for DEBUG, -vv for TRACE | `0` |
| `--log-file` | path | Path to log file (overrides default ~/.mngr/logs/<timestamp>-<pid>.json) | None |
| `--log-commands` / `--no-log-commands` | boolean | Log commands that were executed | None |
| `--log-command-output` / `--no-log-command-output` | boolean | Log stdout/stderr from commands | None |
| `--log-env-vars` / `--no-log-env-vars` | boolean | Log environment variables (security risk) | None |
| `--context` | path | Project context directory (for build context and loading project-specific config) [default: local .git root] | None |
| `--plugin`, `--enable-plugin` | text | Enable a plugin [repeatable] | None |
| `--disable-plugin` | text | Disable a plugin [repeatable] | None |
| `--help` | boolean | Show this message and exit. | `False` |

### list

List all configuration values.

Shows all configuration settings from the specified scope, or from the
merged configuration if no scope is specified.

Examples:

  mngr config list

  mngr config list --scope user

  mngr config list --format json

**Usage:**

```text
mngr config list [OPTIONS]
```

**Options:**

| Name | Type | Description | Default |
| ---- | ---- | ----------- | ------- |
| `--scope` | choice (`user` &#x7C; `project` &#x7C; `local`) | Config scope: user (~/.config/mngr/), project (.mngr/), or local (.mngr/settings.local.toml) | None |
| `--format` | choice (`human` &#x7C; `json` &#x7C; `jsonl`) | Output format for command results | `human` |
| `-q`, `--quiet` | boolean | Suppress all console output | `False` |
| `-v`, `--verbose` | integer range (`0` and above) | Increase verbosity (default: BUILD); -v for DEBUG, -vv for TRACE | `0` |
| `--log-file` | path | Path to log file (overrides default ~/.mngr/logs/<timestamp>-<pid>.json) | None |
| `--log-commands` / `--no-log-commands` | boolean | Log commands that were executed | None |
| `--log-command-output` / `--no-log-command-output` | boolean | Log stdout/stderr from commands | None |
| `--log-env-vars` / `--no-log-env-vars` | boolean | Log environment variables (security risk) | None |
| `--context` | path | Project context directory (for build context and loading project-specific config) [default: local .git root] | None |
| `--plugin`, `--enable-plugin` | text | Enable a plugin [repeatable] | None |
| `--disable-plugin` | text | Disable a plugin [repeatable] | None |
| `--help` | boolean | Show this message and exit. | `False` |

### path

Show configuration file paths.

Shows the paths to configuration files. If --scope is specified, shows
only that scope's path. Otherwise shows all paths and whether they exist.

Examples:

  mngr config path

  mngr config path --scope user

**Usage:**

```text
mngr config path [OPTIONS]
```

**Options:**

| Name | Type | Description | Default |
| ---- | ---- | ----------- | ------- |
| `--scope` | choice (`user` &#x7C; `project` &#x7C; `local`) | Config scope: user (~/.config/mngr/), project (.mngr/), or local (.mngr/settings.local.toml) | None |
| `--format` | choice (`human` &#x7C; `json` &#x7C; `jsonl`) | Output format for command results | `human` |
| `-q`, `--quiet` | boolean | Suppress all console output | `False` |
| `-v`, `--verbose` | integer range (`0` and above) | Increase verbosity (default: BUILD); -v for DEBUG, -vv for TRACE | `0` |
| `--log-file` | path | Path to log file (overrides default ~/.mngr/logs/<timestamp>-<pid>.json) | None |
| `--log-commands` / `--no-log-commands` | boolean | Log commands that were executed | None |
| `--log-command-output` / `--no-log-command-output` | boolean | Log stdout/stderr from commands | None |
| `--log-env-vars` / `--no-log-env-vars` | boolean | Log environment variables (security risk) | None |
| `--context` | path | Project context directory (for build context and loading project-specific config) [default: local .git root] | None |
| `--plugin`, `--enable-plugin` | text | Enable a plugin [repeatable] | None |
| `--disable-plugin` | text | Disable a plugin [repeatable] | None |
| `--help` | boolean | Show this message and exit. | `False` |

### set

Set a configuration value.

Sets a configuration value at the specified scope. Use dot notation
for nested keys (e.g., 'commands.create.connect').

Values are parsed as JSON if possible, otherwise as strings.
Use 'true'/'false' for booleans, numbers for integers/floats.

Examples:

  mngr config set prefix "my-"

  mngr config set commands.create.connect false

  mngr config set logging.console_level DEBUG --scope user

**Usage:**

```text
mngr config set [OPTIONS] KEY VALUE
```

**Options:**

| Name | Type | Description | Default |
| ---- | ---- | ----------- | ------- |
| `--scope` | choice (`user` &#x7C; `project` &#x7C; `local`) | Config scope: user (~/.config/mngr/), project (.mngr/), or local (.mngr/settings.local.toml) | `project` |
| `--format` | choice (`human` &#x7C; `json` &#x7C; `jsonl`) | Output format for command results | `human` |
| `-q`, `--quiet` | boolean | Suppress all console output | `False` |
| `-v`, `--verbose` | integer range (`0` and above) | Increase verbosity (default: BUILD); -v for DEBUG, -vv for TRACE | `0` |
| `--log-file` | path | Path to log file (overrides default ~/.mngr/logs/<timestamp>-<pid>.json) | None |
| `--log-commands` / `--no-log-commands` | boolean | Log commands that were executed | None |
| `--log-command-output` / `--no-log-command-output` | boolean | Log stdout/stderr from commands | None |
| `--log-env-vars` / `--no-log-env-vars` | boolean | Log environment variables (security risk) | None |
| `--context` | path | Project context directory (for build context and loading project-specific config) [default: local .git root] | None |
| `--plugin`, `--enable-plugin` | text | Enable a plugin [repeatable] | None |
| `--disable-plugin` | text | Disable a plugin [repeatable] | None |
| `--help` | boolean | Show this message and exit. | `False` |

### unset

Remove a configuration value.

Removes a configuration value from the specified scope. Use dot notation
for nested keys (e.g., 'commands.create.connect').

Examples:

  mngr config unset commands.create.connect

  mngr config unset logging.console_level --scope user

**Usage:**

```text
mngr config unset [OPTIONS] KEY
```

**Options:**

| Name | Type | Description | Default |
| ---- | ---- | ----------- | ------- |
| `--scope` | choice (`user` &#x7C; `project` &#x7C; `local`) | Config scope: user (~/.config/mngr/), project (.mngr/), or local (.mngr/settings.local.toml) | `project` |
| `--format` | choice (`human` &#x7C; `json` &#x7C; `jsonl`) | Output format for command results | `human` |
| `-q`, `--quiet` | boolean | Suppress all console output | `False` |
| `-v`, `--verbose` | integer range (`0` and above) | Increase verbosity (default: BUILD); -v for DEBUG, -vv for TRACE | `0` |
| `--log-file` | path | Path to log file (overrides default ~/.mngr/logs/<timestamp>-<pid>.json) | None |
| `--log-commands` / `--no-log-commands` | boolean | Log commands that were executed | None |
| `--log-command-output` / `--no-log-command-output` | boolean | Log stdout/stderr from commands | None |
| `--log-env-vars` / `--no-log-env-vars` | boolean | Log environment variables (security risk) | None |
| `--context` | path | Project context directory (for build context and loading project-specific config) [default: local .git root] | None |
| `--plugin`, `--enable-plugin` | text | Enable a plugin [repeatable] | None |
| `--disable-plugin` | text | Disable a plugin [repeatable] | None |
| `--help` | boolean | Show this message and exit. | `False` |

## connect

Connect to an existing agent via the terminal.

Attaches to the agent's tmux session, roughly equivalent to SSH'ing into
the agent's machine and attaching to the tmux session. Use `mngr open` to
open an agent's URLs in a web browser instead.

If no agent is specified, shows an interactive selector to choose from
available agents.

Alias: conn

**Usage:**

```text
mngr connect [OPTIONS] [AGENT]
```

**Options:**

| Name | Type | Description | Default |
| ---- | ---- | ----------- | ------- |
| `--agent` | text | The agent to connect to (by name or ID) | None |
| `--start` / `--no-start` | boolean | Automatically start the agent if stopped | `True` |
| `--reconnect` / `--no-reconnect` | boolean | Automatically reconnect if dropped | `True` |
| `--message` | text | Initial message to send after connecting | None |
| `--message-file` | path | File containing initial message to send | None |
| `--message-delay` | float | Seconds to wait before sending initial message | `1.0` |
| `--retry` | integer | Number of connection retries | `3` |
| `--retry-delay` | text | Delay between retries | `5s` |
| `--attach-command` | text | Command to run instead of attaching to main session | None |
| `--format` | choice (`human` &#x7C; `json` &#x7C; `jsonl`) | Output format for command results | `human` |
| `-q`, `--quiet` | boolean | Suppress all console output | `False` |
| `-v`, `--verbose` | integer range (`0` and above) | Increase verbosity (default: BUILD); -v for DEBUG, -vv for TRACE | `0` |
| `--log-file` | path | Path to log file (overrides default ~/.mngr/logs/<timestamp>-<pid>.json) | None |
| `--log-commands` / `--no-log-commands` | boolean | Log commands that were executed | None |
| `--log-command-output` / `--no-log-command-output` | boolean | Log stdout/stderr from commands | None |
| `--log-env-vars` / `--no-log-env-vars` | boolean | Log environment variables (security risk) | None |
| `--context` | path | Project context directory (for build context and loading project-specific config) [default: local .git root] | None |
| `--plugin`, `--enable-plugin` | text | Enable a plugin [repeatable] | None |
| `--disable-plugin` | text | Disable a plugin [repeatable] | None |
| `-h`, `--help` | boolean | Show this message and exit. | `False` |

## connect

Connect to an existing agent via the terminal.

Attaches to the agent's tmux session, roughly equivalent to SSH'ing into
the agent's machine and attaching to the tmux session. Use `mngr open` to
open an agent's URLs in a web browser instead.

If no agent is specified, shows an interactive selector to choose from
available agents.

Alias: conn

**Usage:**

```text
mngr connect [OPTIONS] [AGENT]
```

**Options:**

| Name | Type | Description | Default |
| ---- | ---- | ----------- | ------- |
| `--agent` | text | The agent to connect to (by name or ID) | None |
| `--start` / `--no-start` | boolean | Automatically start the agent if stopped | `True` |
| `--reconnect` / `--no-reconnect` | boolean | Automatically reconnect if dropped | `True` |
| `--message` | text | Initial message to send after connecting | None |
| `--message-file` | path | File containing initial message to send | None |
| `--message-delay` | float | Seconds to wait before sending initial message | `1.0` |
| `--retry` | integer | Number of connection retries | `3` |
| `--retry-delay` | text | Delay between retries | `5s` |
| `--attach-command` | text | Command to run instead of attaching to main session | None |
| `--format` | choice (`human` &#x7C; `json` &#x7C; `jsonl`) | Output format for command results | `human` |
| `-q`, `--quiet` | boolean | Suppress all console output | `False` |
| `-v`, `--verbose` | integer range (`0` and above) | Increase verbosity (default: BUILD); -v for DEBUG, -vv for TRACE | `0` |
| `--log-file` | path | Path to log file (overrides default ~/.mngr/logs/<timestamp>-<pid>.json) | None |
| `--log-commands` / `--no-log-commands` | boolean | Log commands that were executed | None |
| `--log-command-output` / `--no-log-command-output` | boolean | Log stdout/stderr from commands | None |
| `--log-env-vars` / `--no-log-env-vars` | boolean | Log environment variables (security risk) | None |
| `--context` | path | Project context directory (for build context and loading project-specific config) [default: local .git root] | None |
| `--plugin`, `--enable-plugin` | text | Enable a plugin [repeatable] | None |
| `--disable-plugin` | text | Disable a plugin [repeatable] | None |
| `-h`, `--help` | boolean | Show this message and exit. | `False` |

## create

Create and run an agent.

Sets up the agent's work_dir, optionally provisions a new host (or uses
an existing one), runs the specified agent, and connects to it (by default).

Alias: c

**Usage:**

```text
mngr create [OPTIONS] [POSITIONAL_NAME] [POSITIONAL_AGENT_TYPE]
            [AGENT_ARGS]...
```

**Options:**

| Name | Type | Description | Default |
| ---- | ---- | ----------- | ------- |
| `-n`, `--name` | text | Agent name (alternative to positional argument) [default: auto-generated] | None |
| `--name-style` | choice (`english` &#x7C; `fantasy` &#x7C; `scifi` &#x7C; `painters` &#x7C; `authors` &#x7C; `artists` &#x7C; `musicians` &#x7C; `animals` &#x7C; `scientists` &#x7C; `demons`) | Auto-generated name style | `english` |
| `--agent-type` | text | Which type of agent to run [default: claude] | None |
| `--agent-cmd`, `--agent-command` | text | Run a literal command using the generic agent type (mutually exclusive with --agent-type) | None |
| `-c`, `--add-cmd`, `--add-command` | text | Run extra command in additional window. Use name="command" to set window name. Note: ALL_UPPERCASE names (e.g., FOO="bar") are treated as env var assignments, not window names | None |
| `--user` | text | Override which user to run the agent as | None |
| `--in`, `--new-host` | text | Create a new host using provider (docker, modal, ...) | None |
| `--host`, `--target-host` | text | Use an existing host (by name or ID) [default: local] | None |
| `--target` | text | Target [HOST][:PATH]. Defaults to current dir if no other target args are given | None |
| `--target-path` | text | Directory to mount source inside agent host | None |
| `--in-place` | boolean | Run directly in source directory (no copy/clone/worktree) | `False` |
| `--project` | text | Project name for the agent [default: derived from git remote origin or folder name] | None |
| `--tag` | text | Metadata tag KEY=VALUE [repeatable] | None |
| `--host-name` | text | Name for the new host | None |
| `--host-name-style` | choice (`astronomy` &#x7C; `places` &#x7C; `cities` &#x7C; `fantasy` &#x7C; `scifi` &#x7C; `painters` &#x7C; `authors` &#x7C; `artists` &#x7C; `musicians` &#x7C; `scientists`) | Auto-generated host name style | `astronomy` |
| `--connect` / `--no-connect` | boolean | Connect to the agent after creation [default: connect] | `True` |
| `--await-ready` / `--no-await-ready` | boolean | Wait until agent is ready before returning [default: no-await-ready if --no-connect] | None |
| `--await-agent-stopped` / `--no-await-agent-stopped` | boolean | Wait until agent has completely finished running before exiting [default: no-await-agent-stopped] | None |
| `--ensure-clean` / `--no-ensure-clean` | boolean | Abort if working tree is dirty | `True` |
| `--snapshot-source` / `--no-snapshot-source` | boolean | Snapshot source agent first [default: yes if --source-agent and not local] | None |
| `--copy-work-dir` / `--no-copy-work-dir` | boolean | Copy source work_dir immediately [default: copy if --no-connect] | None |
| `--from`, `--source` | text | Directory to use as work_dir root [AGENT | AGENT.HOST | AGENT.HOST:PATH | HOST:PATH]. Defaults to current dir if no other source args are given | None |
| `--source-agent`, `--from-agent` | text | Source agent for cloning work_dir | None |
| `--source-host` | text | Source host | None |
| `--source-path` | text | Source path | None |
| `--rsync` / `--no-rsync` | boolean | Use rsync for file transfer [default: yes if rsync-args are present or if git is disabled] | None |
| `--rsync-args` | text | Additional arguments to pass to rsync | None |
| `--copy` | boolean | Copy source to isolated directory before running | `False` |
| `--clone` | boolean | Create a git clone that just shares objects with original repo | `False` |
| `--worktree` | boolean | Create a git worktree that shares objects and index with original repo. Requires --new-branch | `False` |
| `--include-git` / `--no-include-git` | boolean | Include .git directory | `True` |
| `--base-branch` | text | The starting point for the agent [default: current branch] | None |
| `--new-branch` | text | Create a fresh branch (named TEXT if provided, otherwise auto-generated) [default: new branch] | `` |
| `--no-new-branch` | text | Do not create a new branch; use the current branch directly. Incompatible with --worktree | None |
| `--new-branch-prefix` | text | Prefix for auto-generated branch names | `mngr/` |
| `--depth` | integer | Shallow clone depth [default: full] | None |
| `--shallow-since` | text | Shallow clone since date | None |
| `--include-unclean` / `--exclude-unclean` | boolean | Include uncommitted files [default: include if --no-ensure-clean] | None |
| `--include-gitignored` / `--no-include-gitignored` | boolean | Include gitignored files | `False` |
| `--env`, `--agent-env` | text | Set environment variable KEY=VALUE | None |
| `--env-file`, `--agent-env-file` | path | Load env | None |
| `--pass-env`, `--pass-agent-env` | text | Forward variable from shell | None |
| `--grant` | text | Grant a permission to the agent [repeatable] | None |
| `--user-command` | text | Run custom shell command during provisioning [repeatable] | None |
| `--sudo-command` | text | Run custom shell command as root during provisioning [repeatable] | None |
| `--upload-file` | text | Upload LOCAL:REMOTE file pair [repeatable] | None |
| `--append-to-file` | text | Append REMOTE:TEXT to file [repeatable] | None |
| `--prepend-to-file` | text | Prepend REMOTE:TEXT to file [repeatable] | None |
| `--create-directory` | text | Create directory on remote [repeatable] | None |
| `--host-env` | text | Set environment variable KEY=VALUE for host [repeatable] | None |
| `--host-env-file` | path | Load env file for host [repeatable] | None |
| `--pass-host-env` | text | Forward variable from shell for host [repeatable] | None |
| `--snapshot` | text | Use existing snapshot instead of building | None |
| `-b`, `--build`, `--build-arg` | text | Build argument as key=value or --key=value (e.g., -b gpu=h100 -b cpu=2) [repeatable] | None |
| `--build-args` | text | Space-separated build arguments (e.g., 'gpu=h100 cpu=2') | None |
| `-s`, `--start`, `--start-arg` | text | Argument for start [repeatable] | None |
| `--start-args` | text | Space-separated start arguments (alternative to -s) | None |
| `--idle-timeout` | integer | Shutdown after idle for N seconds [default: none] | None |
| `--idle-mode` | choice (`io` &#x7C; `user` &#x7C; `agent` &#x7C; `ssh` &#x7C; `create` &#x7C; `boot` &#x7C; `start` &#x7C; `run` &#x7C; `disabled`) | When to consider host idle [default: io if remote, disabled if local] | None |
| `--activity-sources` | text | Activity sources for idle detection (comma-separated) | None |
| `--start-on-boot` / `--no-start-on-boot` | boolean | Restart on host boot [default: no] | None |
| `--reconnect` / `--no-reconnect` | boolean | Automatically reconnect if dropped | `True` |
| `--interactive` / `--no-interactive` | boolean | Enable interactive mode [default: yes if TTY] | None |
| `--message` | text | Initial message to send after the agent starts | None |
| `--message-file` | path | File containing initial message to send | None |
| `--edit-message` | boolean | Open an editor to compose the initial message (uses $EDITOR) | `False` |
| `--message-delay` | float | Seconds to wait before sending initial message | `1.0` |
| `--retry` | integer | Number of connection retries | `3` |
| `--retry-delay` | text | Delay between retries (e.g., 5s, 1m) | `5s` |
| `--attach-command` | text | Command to run instead of attaching to main session | None |
| `--format` | choice (`human` &#x7C; `json` &#x7C; `jsonl`) | Output format for command results | `human` |
| `-q`, `--quiet` | boolean | Suppress all console output | `False` |
| `-v`, `--verbose` | integer range (`0` and above) | Increase verbosity (default: BUILD); -v for DEBUG, -vv for TRACE | `0` |
| `--log-file` | path | Path to log file (overrides default ~/.mngr/logs/<timestamp>-<pid>.json) | None |
| `--log-commands` / `--no-log-commands` | boolean | Log commands that were executed | None |
| `--log-command-output` / `--no-log-command-output` | boolean | Log stdout/stderr from commands | None |
| `--log-env-vars` / `--no-log-env-vars` | boolean | Log environment variables (security risk) | None |
| `--context` | path | Project context directory (for build context and loading project-specific config) [default: local .git root] | None |
| `--plugin`, `--enable-plugin` | text | Enable a plugin [repeatable] | None |
| `--disable-plugin` | text | Disable a plugin [repeatable] | None |
| `-h`, `--help` | boolean | Show this message and exit. | `False` |

## create

Create and run an agent.

Sets up the agent's work_dir, optionally provisions a new host (or uses
an existing one), runs the specified agent, and connects to it (by default).

Alias: c

**Usage:**

```text
mngr create [OPTIONS] [POSITIONAL_NAME] [POSITIONAL_AGENT_TYPE]
            [AGENT_ARGS]...
```

**Options:**

| Name | Type | Description | Default |
| ---- | ---- | ----------- | ------- |
| `-n`, `--name` | text | Agent name (alternative to positional argument) [default: auto-generated] | None |
| `--name-style` | choice (`english` &#x7C; `fantasy` &#x7C; `scifi` &#x7C; `painters` &#x7C; `authors` &#x7C; `artists` &#x7C; `musicians` &#x7C; `animals` &#x7C; `scientists` &#x7C; `demons`) | Auto-generated name style | `english` |
| `--agent-type` | text | Which type of agent to run [default: claude] | None |
| `--agent-cmd`, `--agent-command` | text | Run a literal command using the generic agent type (mutually exclusive with --agent-type) | None |
| `-c`, `--add-cmd`, `--add-command` | text | Run extra command in additional window. Use name="command" to set window name. Note: ALL_UPPERCASE names (e.g., FOO="bar") are treated as env var assignments, not window names | None |
| `--user` | text | Override which user to run the agent as | None |
| `--in`, `--new-host` | text | Create a new host using provider (docker, modal, ...) | None |
| `--host`, `--target-host` | text | Use an existing host (by name or ID) [default: local] | None |
| `--target` | text | Target [HOST][:PATH]. Defaults to current dir if no other target args are given | None |
| `--target-path` | text | Directory to mount source inside agent host | None |
| `--in-place` | boolean | Run directly in source directory (no copy/clone/worktree) | `False` |
| `--project` | text | Project name for the agent [default: derived from git remote origin or folder name] | None |
| `--tag` | text | Metadata tag KEY=VALUE [repeatable] | None |
| `--host-name` | text | Name for the new host | None |
| `--host-name-style` | choice (`astronomy` &#x7C; `places` &#x7C; `cities` &#x7C; `fantasy` &#x7C; `scifi` &#x7C; `painters` &#x7C; `authors` &#x7C; `artists` &#x7C; `musicians` &#x7C; `scientists`) | Auto-generated host name style | `astronomy` |
| `--connect` / `--no-connect` | boolean | Connect to the agent after creation [default: connect] | `True` |
| `--await-ready` / `--no-await-ready` | boolean | Wait until agent is ready before returning [default: no-await-ready if --no-connect] | None |
| `--await-agent-stopped` / `--no-await-agent-stopped` | boolean | Wait until agent has completely finished running before exiting [default: no-await-agent-stopped] | None |
| `--ensure-clean` / `--no-ensure-clean` | boolean | Abort if working tree is dirty | `True` |
| `--snapshot-source` / `--no-snapshot-source` | boolean | Snapshot source agent first [default: yes if --source-agent and not local] | None |
| `--copy-work-dir` / `--no-copy-work-dir` | boolean | Copy source work_dir immediately [default: copy if --no-connect] | None |
| `--from`, `--source` | text | Directory to use as work_dir root [AGENT | AGENT.HOST | AGENT.HOST:PATH | HOST:PATH]. Defaults to current dir if no other source args are given | None |
| `--source-agent`, `--from-agent` | text | Source agent for cloning work_dir | None |
| `--source-host` | text | Source host | None |
| `--source-path` | text | Source path | None |
| `--rsync` / `--no-rsync` | boolean | Use rsync for file transfer [default: yes if rsync-args are present or if git is disabled] | None |
| `--rsync-args` | text | Additional arguments to pass to rsync | None |
| `--copy` | boolean | Copy source to isolated directory before running | `False` |
| `--clone` | boolean | Create a git clone that just shares objects with original repo | `False` |
| `--worktree` | boolean | Create a git worktree that shares objects and index with original repo. Requires --new-branch | `False` |
| `--include-git` / `--no-include-git` | boolean | Include .git directory | `True` |
| `--base-branch` | text | The starting point for the agent [default: current branch] | None |
| `--new-branch` | text | Create a fresh branch (named TEXT if provided, otherwise auto-generated) [default: new branch] | `` |
| `--no-new-branch` | text | Do not create a new branch; use the current branch directly. Incompatible with --worktree | None |
| `--new-branch-prefix` | text | Prefix for auto-generated branch names | `mngr/` |
| `--depth` | integer | Shallow clone depth [default: full] | None |
| `--shallow-since` | text | Shallow clone since date | None |
| `--include-unclean` / `--exclude-unclean` | boolean | Include uncommitted files [default: include if --no-ensure-clean] | None |
| `--include-gitignored` / `--no-include-gitignored` | boolean | Include gitignored files | `False` |
| `--env`, `--agent-env` | text | Set environment variable KEY=VALUE | None |
| `--env-file`, `--agent-env-file` | path | Load env | None |
| `--pass-env`, `--pass-agent-env` | text | Forward variable from shell | None |
| `--grant` | text | Grant a permission to the agent [repeatable] | None |
| `--user-command` | text | Run custom shell command during provisioning [repeatable] | None |
| `--sudo-command` | text | Run custom shell command as root during provisioning [repeatable] | None |
| `--upload-file` | text | Upload LOCAL:REMOTE file pair [repeatable] | None |
| `--append-to-file` | text | Append REMOTE:TEXT to file [repeatable] | None |
| `--prepend-to-file` | text | Prepend REMOTE:TEXT to file [repeatable] | None |
| `--create-directory` | text | Create directory on remote [repeatable] | None |
| `--host-env` | text | Set environment variable KEY=VALUE for host [repeatable] | None |
| `--host-env-file` | path | Load env file for host [repeatable] | None |
| `--pass-host-env` | text | Forward variable from shell for host [repeatable] | None |
| `--snapshot` | text | Use existing snapshot instead of building | None |
| `-b`, `--build`, `--build-arg` | text | Build argument as key=value or --key=value (e.g., -b gpu=h100 -b cpu=2) [repeatable] | None |
| `--build-args` | text | Space-separated build arguments (e.g., 'gpu=h100 cpu=2') | None |
| `-s`, `--start`, `--start-arg` | text | Argument for start [repeatable] | None |
| `--start-args` | text | Space-separated start arguments (alternative to -s) | None |
| `--idle-timeout` | integer | Shutdown after idle for N seconds [default: none] | None |
| `--idle-mode` | choice (`io` &#x7C; `user` &#x7C; `agent` &#x7C; `ssh` &#x7C; `create` &#x7C; `boot` &#x7C; `start` &#x7C; `run` &#x7C; `disabled`) | When to consider host idle [default: io if remote, disabled if local] | None |
| `--activity-sources` | text | Activity sources for idle detection (comma-separated) | None |
| `--start-on-boot` / `--no-start-on-boot` | boolean | Restart on host boot [default: no] | None |
| `--reconnect` / `--no-reconnect` | boolean | Automatically reconnect if dropped | `True` |
| `--interactive` / `--no-interactive` | boolean | Enable interactive mode [default: yes if TTY] | None |
| `--message` | text | Initial message to send after the agent starts | None |
| `--message-file` | path | File containing initial message to send | None |
| `--edit-message` | boolean | Open an editor to compose the initial message (uses $EDITOR) | `False` |
| `--message-delay` | float | Seconds to wait before sending initial message | `1.0` |
| `--retry` | integer | Number of connection retries | `3` |
| `--retry-delay` | text | Delay between retries (e.g., 5s, 1m) | `5s` |
| `--attach-command` | text | Command to run instead of attaching to main session | None |
| `--format` | choice (`human` &#x7C; `json` &#x7C; `jsonl`) | Output format for command results | `human` |
| `-q`, `--quiet` | boolean | Suppress all console output | `False` |
| `-v`, `--verbose` | integer range (`0` and above) | Increase verbosity (default: BUILD); -v for DEBUG, -vv for TRACE | `0` |
| `--log-file` | path | Path to log file (overrides default ~/.mngr/logs/<timestamp>-<pid>.json) | None |
| `--log-commands` / `--no-log-commands` | boolean | Log commands that were executed | None |
| `--log-command-output` / `--no-log-command-output` | boolean | Log stdout/stderr from commands | None |
| `--log-env-vars` / `--no-log-env-vars` | boolean | Log environment variables (security risk) | None |
| `--context` | path | Project context directory (for build context and loading project-specific config) [default: local .git root] | None |
| `--plugin`, `--enable-plugin` | text | Enable a plugin [repeatable] | None |
| `--disable-plugin` | text | Disable a plugin [repeatable] | None |
| `-h`, `--help` | boolean | Show this message and exit. | `False` |

## destroy

Destroy agent(s) and clean up resources.

When the last agent on a host is destroyed, the host itself is also destroyed.

Examples:

  mngr destroy my-agent

  mngr destroy agent1 agent2 agent3

  mngr destroy --agent my-agent --agent another-agent

  mngr destroy --session mngr-my-agent

  mngr destroy --all --force

**Usage:**

```text
mngr destroy [OPTIONS] [AGENTS]...
```

**Options:**

| Name | Type | Description | Default |
| ---- | ---- | ----------- | ------- |
| `--agent` | text | Agent name or ID to destroy (can be specified multiple times) | None |
| `-a`, `--all`, `--all-agents` | boolean | Destroy all agents | `False` |
| `--session` | text | Tmux session name to destroy (can be specified multiple times). The agent name is extracted by stripping the configured prefix from the session name. | None |
| `-f`, `--force` | boolean | Skip confirmation prompts and force destroy running agents | `False` |
| `--dry-run` | boolean | Show what would be destroyed without actually destroying | `False` |
| `--gc` / `--no-gc` | boolean | Run garbage collection after destroying agents to clean up orphaned resources (default: enabled) | `True` |
| `--format` | choice (`human` &#x7C; `json` &#x7C; `jsonl`) | Output format for command results | `human` |
| `-q`, `--quiet` | boolean | Suppress all console output | `False` |
| `-v`, `--verbose` | integer range (`0` and above) | Increase verbosity (default: BUILD); -v for DEBUG, -vv for TRACE | `0` |
| `--log-file` | path | Path to log file (overrides default ~/.mngr/logs/<timestamp>-<pid>.json) | None |
| `--log-commands` / `--no-log-commands` | boolean | Log commands that were executed | None |
| `--log-command-output` / `--no-log-command-output` | boolean | Log stdout/stderr from commands | None |
| `--log-env-vars` / `--no-log-env-vars` | boolean | Log environment variables (security risk) | None |
| `--context` | path | Project context directory (for build context and loading project-specific config) [default: local .git root] | None |
| `--plugin`, `--enable-plugin` | text | Enable a plugin [repeatable] | None |
| `--disable-plugin` | text | Disable a plugin [repeatable] | None |
| `--help` | boolean | Show this message and exit. | `False` |

## gc

Garbage collect unused resources.

Automatically removes unused resources from providers and mngr itself.

Examples:

  mngr gc --work-dirs --dry-run

  mngr gc --all-agent-resources

  mngr gc --machines --snapshots --provider docker

  mngr gc --logs --build-cache

**Usage:**

```text
mngr gc [OPTIONS]
```

**Options:**

| Name | Type | Description | Default |
| ---- | ---- | ----------- | ------- |
| `--all-agent-resources` | boolean | Clean all agent resource types (machines, snapshots, volumes, work dirs) | `False` |
| `--machines` | boolean | Remove unused containers, instances, and sandboxes | `False` |
| `--snapshots` | boolean | Remove unused snapshots | `False` |
| `--volumes` | boolean | Remove unused volumes | `False` |
| `--work-dirs` | boolean | Remove work directories (git worktrees/clones) not in use by any agent | `False` |
| `--logs` | boolean | Remove log files from destroyed agents/hosts | `False` |
| `--build-cache` | boolean | Remove build cache entries | `False` |
| `--include` | text | Only clean resources matching CEL filter (repeatable) | None |
| `--exclude` | text | Exclude resources matching CEL filter (repeatable) | None |
| `--all-providers` | boolean | Clean resources across all providers | `False` |
| `--provider` | text | Clean resources for a specific provider (repeatable) | None |
| `--dry-run` | boolean | Show what would be cleaned without actually cleaning | `False` |
| `--on-error` | choice (`abort` &#x7C; `continue`) | What to do when errors occur: abort (stop immediately) or continue (keep going) | `abort` |
| `-w`, `--watch` | integer | Re-run garbage collection at the specified interval (seconds) | None |
| `--format` | choice (`human` &#x7C; `json` &#x7C; `jsonl`) | Output format for command results | `human` |
| `-q`, `--quiet` | boolean | Suppress all console output | `False` |
| `-v`, `--verbose` | integer range (`0` and above) | Increase verbosity (default: BUILD); -v for DEBUG, -vv for TRACE | `0` |
| `--log-file` | path | Path to log file (overrides default ~/.mngr/logs/<timestamp>-<pid>.json) | None |
| `--log-commands` / `--no-log-commands` | boolean | Log commands that were executed | None |
| `--log-command-output` / `--no-log-command-output` | boolean | Log stdout/stderr from commands | None |
| `--log-env-vars` / `--no-log-env-vars` | boolean | Log environment variables (security risk) | None |
| `--context` | path | Project context directory (for build context and loading project-specific config) [default: local .git root] | None |
| `--plugin`, `--enable-plugin` | text | Enable a plugin [repeatable] | None |
| `--disable-plugin` | text | Disable a plugin [repeatable] | None |
| `-h`, `--help` | boolean | Show this message and exit. | `False` |

## list

List all agents managed by mngr.

Displays agents with their status, host information, and other metadata.
Supports filtering, sorting, and multiple output formats.

Examples:

  mngr list

  mngr list --running

  mngr list --provider docker

  mngr list --format json

**Usage:**

```text
mngr list [OPTIONS]
```

**Options:**

| Name | Type | Description | Default |
| ---- | ---- | ----------- | ------- |
| `--include` | text | Include agents matching CEL expression (repeatable) | None |
| `--exclude` | text | Exclude agents matching CEL expression (repeatable) | None |
| `--running` | boolean | Show only running agents (alias for --include state == "running") | `False` |
| `--stopped` | boolean | Show only stopped agents (alias for --include state == "stopped") | `False` |
| `--local` | boolean | Show only local agents (alias for --include host.provider == "local") | `False` |
| `--remote` | boolean | Show only remote agents (alias for --exclude host.provider == "local") | `False` |
| `--provider` | text | Show only agents using specified provider (repeatable) | None |
| `--stdin` | boolean | Read agent and host IDs or names from stdin (one per line) | `False` |
| `--format-template` | text | Output format as a string template (mutually exclusive with --format) | None |
| `--fields` | text | Which fields to include (comma-separated) | None |
| `--sort` | text | Sort by field [default: create_time] | `create_time` |
| `--sort-order` | choice (`asc` &#x7C; `desc`) | Sort order [default: asc] | `asc` |
| `--limit` | integer | Limit number of results | None |
| `-w`, `--watch` | integer | Continuously watch and update status at specified interval (seconds) [default: 2] | None |
| `--on-error` | choice (`abort` &#x7C; `continue`) | What to do when errors occur: abort (stop immediately) or continue (keep going) | `abort` |
| `--format` | choice (`human` &#x7C; `json` &#x7C; `jsonl`) | Output format for command results | `human` |
| `-q`, `--quiet` | boolean | Suppress all console output | `False` |
| `-v`, `--verbose` | integer range (`0` and above) | Increase verbosity (default: BUILD); -v for DEBUG, -vv for TRACE | `0` |
| `--log-file` | path | Path to log file (overrides default ~/.mngr/logs/<timestamp>-<pid>.json) | None |
| `--log-commands` / `--no-log-commands` | boolean | Log commands that were executed | None |
| `--log-command-output` / `--no-log-command-output` | boolean | Log stdout/stderr from commands | None |
| `--log-env-vars` / `--no-log-env-vars` | boolean | Log environment variables (security risk) | None |
| `--context` | path | Project context directory (for build context and loading project-specific config) [default: local .git root] | None |
| `--plugin`, `--enable-plugin` | text | Enable a plugin [repeatable] | None |
| `--disable-plugin` | text | Disable a plugin [repeatable] | None |
| `-h`, `--help` | boolean | Show this message and exit. | `False` |

## list

List all agents managed by mngr.

Displays agents with their status, host information, and other metadata.
Supports filtering, sorting, and multiple output formats.

Examples:

  mngr list

  mngr list --running

  mngr list --provider docker

  mngr list --format json

**Usage:**

```text
mngr list [OPTIONS]
```

**Options:**

| Name | Type | Description | Default |
| ---- | ---- | ----------- | ------- |
| `--include` | text | Include agents matching CEL expression (repeatable) | None |
| `--exclude` | text | Exclude agents matching CEL expression (repeatable) | None |
| `--running` | boolean | Show only running agents (alias for --include state == "running") | `False` |
| `--stopped` | boolean | Show only stopped agents (alias for --include state == "stopped") | `False` |
| `--local` | boolean | Show only local agents (alias for --include host.provider == "local") | `False` |
| `--remote` | boolean | Show only remote agents (alias for --exclude host.provider == "local") | `False` |
| `--provider` | text | Show only agents using specified provider (repeatable) | None |
| `--stdin` | boolean | Read agent and host IDs or names from stdin (one per line) | `False` |
| `--format-template` | text | Output format as a string template (mutually exclusive with --format) | None |
| `--fields` | text | Which fields to include (comma-separated) | None |
| `--sort` | text | Sort by field [default: create_time] | `create_time` |
| `--sort-order` | choice (`asc` &#x7C; `desc`) | Sort order [default: asc] | `asc` |
| `--limit` | integer | Limit number of results | None |
| `-w`, `--watch` | integer | Continuously watch and update status at specified interval (seconds) [default: 2] | None |
| `--on-error` | choice (`abort` &#x7C; `continue`) | What to do when errors occur: abort (stop immediately) or continue (keep going) | `abort` |
| `--format` | choice (`human` &#x7C; `json` &#x7C; `jsonl`) | Output format for command results | `human` |
| `-q`, `--quiet` | boolean | Suppress all console output | `False` |
| `-v`, `--verbose` | integer range (`0` and above) | Increase verbosity (default: BUILD); -v for DEBUG, -vv for TRACE | `0` |
| `--log-file` | path | Path to log file (overrides default ~/.mngr/logs/<timestamp>-<pid>.json) | None |
| `--log-commands` / `--no-log-commands` | boolean | Log commands that were executed | None |
| `--log-command-output` / `--no-log-command-output` | boolean | Log stdout/stderr from commands | None |
| `--log-env-vars` / `--no-log-env-vars` | boolean | Log environment variables (security risk) | None |
| `--context` | path | Project context directory (for build context and loading project-specific config) [default: local .git root] | None |
| `--plugin`, `--enable-plugin` | text | Enable a plugin [repeatable] | None |
| `--disable-plugin` | text | Disable a plugin [repeatable] | None |
| `-h`, `--help` | boolean | Show this message and exit. | `False` |

## message

Send a message to one or more agents.

Agent IDs can be specified as positional arguments for convenience.
The message is sent to the agent's stdin.

If no message is specified with --message, reads from stdin (if not a tty)
or opens an editor (if interactive).

Examples:

  mngr message my-agent --message "Hello"

  mngr message agent1 agent2 --message "Hello to all"

  mngr message --agent my-agent --agent another-agent --message "Hello"

  mngr message --all --message "Hello everyone"

  echo "Hello" | mngr message my-agent

**Usage:**

```text
mngr message [OPTIONS] [AGENTS]...
```

**Options:**

| Name | Type | Description | Default |
| ---- | ---- | ----------- | ------- |
| `--agent` | text | Agent name or ID to send message to (can be specified multiple times) | None |
| `-a`, `--all`, `--all-agents` | boolean | Send message to all agents | `False` |
| `--include` | text | Include agents matching CEL expression (repeatable) | None |
| `--exclude` | text | Exclude agents matching CEL expression (repeatable) | None |
| `--stdin` | boolean | Read agent and host IDs or names from stdin (one per line) | `False` |
| `-m`, `--message` | text | The message content to send | None |
| `--on-error` | choice (`abort` &#x7C; `continue`) | What to do when errors occur: abort (stop immediately) or continue (keep going) | `continue` |
| `--format` | choice (`human` &#x7C; `json` &#x7C; `jsonl`) | Output format for command results | `human` |
| `-q`, `--quiet` | boolean | Suppress all console output | `False` |
| `-v`, `--verbose` | integer range (`0` and above) | Increase verbosity (default: BUILD); -v for DEBUG, -vv for TRACE | `0` |
| `--log-file` | path | Path to log file (overrides default ~/.mngr/logs/<timestamp>-<pid>.json) | None |
| `--log-commands` / `--no-log-commands` | boolean | Log commands that were executed | None |
| `--log-command-output` / `--no-log-command-output` | boolean | Log stdout/stderr from commands | None |
| `--log-env-vars` / `--no-log-env-vars` | boolean | Log environment variables (security risk) | None |
| `--context` | path | Project context directory (for build context and loading project-specific config) [default: local .git root] | None |
| `--plugin`, `--enable-plugin` | text | Enable a plugin [repeatable] | None |
| `--disable-plugin` | text | Disable a plugin [repeatable] | None |
| `--help` | boolean | Show this message and exit. | `False` |

## message

Send a message to one or more agents.

Agent IDs can be specified as positional arguments for convenience.
The message is sent to the agent's stdin.

If no message is specified with --message, reads from stdin (if not a tty)
or opens an editor (if interactive).

Examples:

  mngr message my-agent --message "Hello"

  mngr message agent1 agent2 --message "Hello to all"

  mngr message --agent my-agent --agent another-agent --message "Hello"

  mngr message --all --message "Hello everyone"

  echo "Hello" | mngr message my-agent

**Usage:**

```text
mngr message [OPTIONS] [AGENTS]...
```

**Options:**

| Name | Type | Description | Default |
| ---- | ---- | ----------- | ------- |
| `--agent` | text | Agent name or ID to send message to (can be specified multiple times) | None |
| `-a`, `--all`, `--all-agents` | boolean | Send message to all agents | `False` |
| `--include` | text | Include agents matching CEL expression (repeatable) | None |
| `--exclude` | text | Exclude agents matching CEL expression (repeatable) | None |
| `--stdin` | boolean | Read agent and host IDs or names from stdin (one per line) | `False` |
| `-m`, `--message` | text | The message content to send | None |
| `--on-error` | choice (`abort` &#x7C; `continue`) | What to do when errors occur: abort (stop immediately) or continue (keep going) | `continue` |
| `--format` | choice (`human` &#x7C; `json` &#x7C; `jsonl`) | Output format for command results | `human` |
| `-q`, `--quiet` | boolean | Suppress all console output | `False` |
| `-v`, `--verbose` | integer range (`0` and above) | Increase verbosity (default: BUILD); -v for DEBUG, -vv for TRACE | `0` |
| `--log-file` | path | Path to log file (overrides default ~/.mngr/logs/<timestamp>-<pid>.json) | None |
| `--log-commands` / `--no-log-commands` | boolean | Log commands that were executed | None |
| `--log-command-output` / `--no-log-command-output` | boolean | Log stdout/stderr from commands | None |
| `--log-env-vars` / `--no-log-env-vars` | boolean | Log environment variables (security risk) | None |
| `--context` | path | Project context directory (for build context and loading project-specific config) [default: local .git root] | None |
| `--plugin`, `--enable-plugin` | text | Enable a plugin [repeatable] | None |
| `--disable-plugin` | text | Disable a plugin [repeatable] | None |
| `--help` | boolean | Show this message and exit. | `False` |

## pull

Pull files from an agent to local machine.

Syncs files from an agent's working directory to a local directory.
Default behavior uses rsync for efficient incremental file transfer.

If no source is specified, shows an interactive selector to choose an agent.

Examples:
  mngr pull my-agent
  mngr pull my-agent ./local-copy
  mngr pull my-agent:src ./local-src
  mngr pull --source-agent my-agent

**Usage:**

```text
mngr pull [OPTIONS] [SOURCE] [DESTINATION]
```

**Options:**

| Name | Type | Description | Default |
| ---- | ---- | ----------- | ------- |
| `--source` | text | Source specification: AGENT, AGENT:PATH, or PATH | None |
| `--source-agent` | text | Source agent name or ID | None |
| `--source-host` | text | Source host name or ID | None |
| `--source-path` | text | Path within the agent's work directory | None |
| `--destination` | path | Local destination directory [default: .] | None |
| `--dry-run` | boolean | Show what would be transferred without actually transferring | `False` |
| `--stop` | boolean | Stop the agent after pulling (for state consistency) | `False` |
| `--delete` / `--no-delete` | boolean | Delete files in destination that don't exist in source | `False` |
| `--sync-mode` | choice (`files` &#x7C; `state` &#x7C; `full`) | What to sync: files (working directory only), state (agent state), or full (everything) | `files` |
| `--exclude` | text | Patterns to exclude from sync [repeatable] | None |
| `--format` | choice (`human` &#x7C; `json` &#x7C; `jsonl`) | Output format for command results | `human` |
| `-q`, `--quiet` | boolean | Suppress all console output | `False` |
| `-v`, `--verbose` | integer range (`0` and above) | Increase verbosity (default: BUILD); -v for DEBUG, -vv for TRACE | `0` |
| `--log-file` | path | Path to log file (overrides default ~/.mngr/logs/<timestamp>-<pid>.json) | None |
| `--log-commands` / `--no-log-commands` | boolean | Log commands that were executed | None |
| `--log-command-output` / `--no-log-command-output` | boolean | Log stdout/stderr from commands | None |
| `--log-env-vars` / `--no-log-env-vars` | boolean | Log environment variables (security risk) | None |
| `--context` | path | Project context directory (for build context and loading project-specific config) [default: local .git root] | None |
| `--plugin`, `--enable-plugin` | text | Enable a plugin [repeatable] | None |
| `--disable-plugin` | text | Disable a plugin [repeatable] | None |
| `--help` | boolean | Show this message and exit. | `False` |
