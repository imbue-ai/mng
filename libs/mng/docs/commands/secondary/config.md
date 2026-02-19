<!-- This file is auto-generated. Do not edit directly. -->
<!-- To modify, edit the command's help metadata and run: uv run python scripts/make_cli_docs.py -->

# mng config

**Synopsis:**

```text
mng [config|cfg] <subcommand> [OPTIONS]
```


Manage mng configuration.

View, edit, and modify mng configuration settings at the user, project,
or local scope.

Examples:

  mng config list

  mng config get prefix

  mng config set --scope project commands.create.connect false

  mng config unset commands.create.connect

  mng config edit --scope user

**Usage:**

```text
mng config [OPTIONS] COMMAND [ARGS]...
```

**Options:**

## Common

| Name | Type | Description | Default |
| ---- | ---- | ----------- | ------- |
| `--format` | text | Output format (human, json, jsonl, FORMAT): Output format for results. When a template is provided [experimental], fields use standard python templating like 'name: {agent.name}' See below for available fields. | `human` |
| `--json` | boolean | Alias for --format json | `False` |
| `--jsonl` | boolean | Alias for --format jsonl | `False` |
| `-q`, `--quiet` | boolean | Suppress all console output | `False` |
| `-v`, `--verbose` | integer range | Increase verbosity (default: BUILD); -v for DEBUG, -vv for TRACE | `0` |
| `--log-file` | path | Path to log file (overrides default ~/.mng/logs/<timestamp>-<pid>.json) | None |
| `--log-commands`, `--no-log-commands` | boolean | Log commands that were executed | None |
| `--log-command-output`, `--no-log-command-output` | boolean | Log stdout/stderr from commands | None |
| `--log-env-vars`, `--no-log-env-vars` | boolean | Log environment variables (security risk) | None |
| `--context` | path | Project context directory (for build context and loading project-specific config) [default: local .git root] | None |
| `--plugin`, `--enable-plugin` | text | Enable a plugin [repeatable] | None |
| `--disable-plugin` | text | Disable a plugin [repeatable] | None |

## Other Options

| Name | Type | Description | Default |
| ---- | ---- | ----------- | ------- |
| `--scope` | choice (`user` &#x7C; `project` &#x7C; `local`) | Config scope: user (~/.mng/profiles/<profile_id>/), project (.mng/), or local (.mng/settings.local.toml) | None |
| `-h`, `--help` | boolean | Show this message and exit. | `False` |

## mng config list

List all configuration values.

Shows all configuration settings from the specified scope, or from the
merged configuration if no scope is specified.

Supports custom format templates via --format. Available fields:
key, value.

Examples:

  mng config list

  mng config list --scope user

  mng config list --format json

  mng config list --format '{key}={value}'

**Usage:**

```text
mng config list [OPTIONS]
```

**Options:**

## Common

| Name | Type | Description | Default |
| ---- | ---- | ----------- | ------- |
| `--format` | text | Output format (human, json, jsonl, FORMAT): Output format for results. When a template is provided [experimental], fields use standard python templating like 'name: {agent.name}' See below for available fields. | `human` |
| `--json` | boolean | Alias for --format json | `False` |
| `--jsonl` | boolean | Alias for --format jsonl | `False` |
| `-q`, `--quiet` | boolean | Suppress all console output | `False` |
| `-v`, `--verbose` | integer range | Increase verbosity (default: BUILD); -v for DEBUG, -vv for TRACE | `0` |
| `--log-file` | path | Path to log file (overrides default ~/.mng/logs/<timestamp>-<pid>.json) | None |
| `--log-commands`, `--no-log-commands` | boolean | Log commands that were executed | None |
| `--log-command-output`, `--no-log-command-output` | boolean | Log stdout/stderr from commands | None |
| `--log-env-vars`, `--no-log-env-vars` | boolean | Log environment variables (security risk) | None |
| `--context` | path | Project context directory (for build context and loading project-specific config) [default: local .git root] | None |
| `--plugin`, `--enable-plugin` | text | Enable a plugin [repeatable] | None |
| `--disable-plugin` | text | Disable a plugin [repeatable] | None |

## Other Options

| Name | Type | Description | Default |
| ---- | ---- | ----------- | ------- |
| `--scope` | choice (`user` &#x7C; `project` &#x7C; `local`) | Config scope: user (~/.mng/profiles/<profile_id>/), project (.mng/), or local (.mng/settings.local.toml) | None |

## mng config get

Get a configuration value.

Retrieves the value of a specific configuration key. Use dot notation
for nested keys (e.g., 'commands.create.connect').

Examples:

  mng config get prefix

  mng config get commands.create.connect

  mng config get logging.console_level --scope user

**Usage:**

```text
mng config get [OPTIONS] KEY
```

**Options:**

## Common

| Name | Type | Description | Default |
| ---- | ---- | ----------- | ------- |
| `--format` | text | Output format (human, json, jsonl, FORMAT): Output format for results. When a template is provided [experimental], fields use standard python templating like 'name: {agent.name}' See below for available fields. | `human` |
| `--json` | boolean | Alias for --format json | `False` |
| `--jsonl` | boolean | Alias for --format jsonl | `False` |
| `-q`, `--quiet` | boolean | Suppress all console output | `False` |
| `-v`, `--verbose` | integer range | Increase verbosity (default: BUILD); -v for DEBUG, -vv for TRACE | `0` |
| `--log-file` | path | Path to log file (overrides default ~/.mng/logs/<timestamp>-<pid>.json) | None |
| `--log-commands`, `--no-log-commands` | boolean | Log commands that were executed | None |
| `--log-command-output`, `--no-log-command-output` | boolean | Log stdout/stderr from commands | None |
| `--log-env-vars`, `--no-log-env-vars` | boolean | Log environment variables (security risk) | None |
| `--context` | path | Project context directory (for build context and loading project-specific config) [default: local .git root] | None |
| `--plugin`, `--enable-plugin` | text | Enable a plugin [repeatable] | None |
| `--disable-plugin` | text | Disable a plugin [repeatable] | None |

## Other Options

| Name | Type | Description | Default |
| ---- | ---- | ----------- | ------- |
| `--scope` | choice (`user` &#x7C; `project` &#x7C; `local`) | Config scope: user (~/.mng/profiles/<profile_id>/), project (.mng/), or local (.mng/settings.local.toml) | None |

## mng config set

Set a configuration value.

Sets a configuration value at the specified scope. Use dot notation
for nested keys (e.g., 'commands.create.connect').

Values are parsed as JSON if possible, otherwise as strings.
Use 'true'/'false' for booleans, numbers for integers/floats.

Examples:

  mng config set prefix "my-"

  mng config set commands.create.connect false

  mng config set logging.console_level DEBUG --scope user

**Usage:**

```text
mng config set [OPTIONS] KEY VALUE
```

**Options:**

## Common

| Name | Type | Description | Default |
| ---- | ---- | ----------- | ------- |
| `--format` | text | Output format (human, json, jsonl, FORMAT): Output format for results. When a template is provided [experimental], fields use standard python templating like 'name: {agent.name}' See below for available fields. | `human` |
| `--json` | boolean | Alias for --format json | `False` |
| `--jsonl` | boolean | Alias for --format jsonl | `False` |
| `-q`, `--quiet` | boolean | Suppress all console output | `False` |
| `-v`, `--verbose` | integer range | Increase verbosity (default: BUILD); -v for DEBUG, -vv for TRACE | `0` |
| `--log-file` | path | Path to log file (overrides default ~/.mng/logs/<timestamp>-<pid>.json) | None |
| `--log-commands`, `--no-log-commands` | boolean | Log commands that were executed | None |
| `--log-command-output`, `--no-log-command-output` | boolean | Log stdout/stderr from commands | None |
| `--log-env-vars`, `--no-log-env-vars` | boolean | Log environment variables (security risk) | None |
| `--context` | path | Project context directory (for build context and loading project-specific config) [default: local .git root] | None |
| `--plugin`, `--enable-plugin` | text | Enable a plugin [repeatable] | None |
| `--disable-plugin` | text | Disable a plugin [repeatable] | None |

## Other Options

| Name | Type | Description | Default |
| ---- | ---- | ----------- | ------- |
| `--scope` | choice (`user` &#x7C; `project` &#x7C; `local`) | Config scope: user (~/.mng/profiles/<profile_id>/), project (.mng/), or local (.mng/settings.local.toml) | `project` |

## mng config unset

Remove a configuration value.

Removes a configuration value from the specified scope. Use dot notation
for nested keys (e.g., 'commands.create.connect').

Examples:

  mng config unset commands.create.connect

  mng config unset logging.console_level --scope user

**Usage:**

```text
mng config unset [OPTIONS] KEY
```

**Options:**

## Common

| Name | Type | Description | Default |
| ---- | ---- | ----------- | ------- |
| `--format` | text | Output format (human, json, jsonl, FORMAT): Output format for results. When a template is provided [experimental], fields use standard python templating like 'name: {agent.name}' See below for available fields. | `human` |
| `--json` | boolean | Alias for --format json | `False` |
| `--jsonl` | boolean | Alias for --format jsonl | `False` |
| `-q`, `--quiet` | boolean | Suppress all console output | `False` |
| `-v`, `--verbose` | integer range | Increase verbosity (default: BUILD); -v for DEBUG, -vv for TRACE | `0` |
| `--log-file` | path | Path to log file (overrides default ~/.mng/logs/<timestamp>-<pid>.json) | None |
| `--log-commands`, `--no-log-commands` | boolean | Log commands that were executed | None |
| `--log-command-output`, `--no-log-command-output` | boolean | Log stdout/stderr from commands | None |
| `--log-env-vars`, `--no-log-env-vars` | boolean | Log environment variables (security risk) | None |
| `--context` | path | Project context directory (for build context and loading project-specific config) [default: local .git root] | None |
| `--plugin`, `--enable-plugin` | text | Enable a plugin [repeatable] | None |
| `--disable-plugin` | text | Disable a plugin [repeatable] | None |

## Other Options

| Name | Type | Description | Default |
| ---- | ---- | ----------- | ------- |
| `--scope` | choice (`user` &#x7C; `project` &#x7C; `local`) | Config scope: user (~/.mng/profiles/<profile_id>/), project (.mng/), or local (.mng/settings.local.toml) | `project` |

## mng config edit

Open configuration file in editor.

Opens the configuration file for the specified scope in your default
editor (from $EDITOR or $VISUAL environment variable, or 'vi' as fallback).

If the config file doesn't exist, it will be created with an empty template.

Examples:

  mng config edit

  mng config edit --scope user

  mng config edit --scope local

**Usage:**

```text
mng config edit [OPTIONS]
```

**Options:**

## Common

| Name | Type | Description | Default |
| ---- | ---- | ----------- | ------- |
| `--format` | text | Output format (human, json, jsonl, FORMAT): Output format for results. When a template is provided [experimental], fields use standard python templating like 'name: {agent.name}' See below for available fields. | `human` |
| `--json` | boolean | Alias for --format json | `False` |
| `--jsonl` | boolean | Alias for --format jsonl | `False` |
| `-q`, `--quiet` | boolean | Suppress all console output | `False` |
| `-v`, `--verbose` | integer range | Increase verbosity (default: BUILD); -v for DEBUG, -vv for TRACE | `0` |
| `--log-file` | path | Path to log file (overrides default ~/.mng/logs/<timestamp>-<pid>.json) | None |
| `--log-commands`, `--no-log-commands` | boolean | Log commands that were executed | None |
| `--log-command-output`, `--no-log-command-output` | boolean | Log stdout/stderr from commands | None |
| `--log-env-vars`, `--no-log-env-vars` | boolean | Log environment variables (security risk) | None |
| `--context` | path | Project context directory (for build context and loading project-specific config) [default: local .git root] | None |
| `--plugin`, `--enable-plugin` | text | Enable a plugin [repeatable] | None |
| `--disable-plugin` | text | Disable a plugin [repeatable] | None |

## Other Options

| Name | Type | Description | Default |
| ---- | ---- | ----------- | ------- |
| `--scope` | choice (`user` &#x7C; `project` &#x7C; `local`) | Config scope: user (~/.mng/profiles/<profile_id>/), project (.mng/), or local (.mng/settings.local.toml) | `project` |

## mng config path

Show configuration file paths.

Shows the paths to configuration files. If --scope is specified, shows
only that scope's path. Otherwise shows all paths and whether they exist.

Examples:

  mng config path

  mng config path --scope user

**Usage:**

```text
mng config path [OPTIONS]
```

**Options:**

## Common

| Name | Type | Description | Default |
| ---- | ---- | ----------- | ------- |
| `--format` | text | Output format (human, json, jsonl, FORMAT): Output format for results. When a template is provided [experimental], fields use standard python templating like 'name: {agent.name}' See below for available fields. | `human` |
| `--json` | boolean | Alias for --format json | `False` |
| `--jsonl` | boolean | Alias for --format jsonl | `False` |
| `-q`, `--quiet` | boolean | Suppress all console output | `False` |
| `-v`, `--verbose` | integer range | Increase verbosity (default: BUILD); -v for DEBUG, -vv for TRACE | `0` |
| `--log-file` | path | Path to log file (overrides default ~/.mng/logs/<timestamp>-<pid>.json) | None |
| `--log-commands`, `--no-log-commands` | boolean | Log commands that were executed | None |
| `--log-command-output`, `--no-log-command-output` | boolean | Log stdout/stderr from commands | None |
| `--log-env-vars`, `--no-log-env-vars` | boolean | Log environment variables (security risk) | None |
| `--context` | path | Project context directory (for build context and loading project-specific config) [default: local .git root] | None |
| `--plugin`, `--enable-plugin` | text | Enable a plugin [repeatable] | None |
| `--disable-plugin` | text | Disable a plugin [repeatable] | None |

## Other Options

| Name | Type | Description | Default |
| ---- | ---- | ----------- | ------- |
| `--scope` | choice (`user` &#x7C; `project` &#x7C; `local`) | Config scope: user (~/.mng/profiles/<profile_id>/), project (.mng/), or local (.mng/settings.local.toml) | None |

## See Also

- [mng create](../primary/create.md) - Create a new agent with configuration

## Examples

**List all configuration values**

```bash
$ mng config list
```

**Get a specific value**

```bash
$ mng config get provider.docker.image
```

**Set a value at user scope**

```bash
$ mng config set --user provider.docker.image my-image:latest
```

**Edit config in your editor**

```bash
$ mng config edit
```

**Show config file paths**

```bash
$ mng config path
```
