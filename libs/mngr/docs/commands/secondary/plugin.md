<!-- This file is auto-generated. Do not edit directly. -->
<!-- To modify, edit the command's help metadata and run: uv run python scripts/make_cli_docs.py -->

# mngr plugin

**Synopsis:**

```text
mngr [plugin|plug] <subcommand> [OPTIONS]
```


Manage available and active plugins.

View, enable, and disable plugins registered with mngr.

Examples:

  mngr plugin list

  mngr plugin list --active

  mngr plugin list --fields name,enabled

**Usage:**

```text
mngr plugin [OPTIONS] COMMAND [ARGS]...
```

**Options:**

## Common

| Name | Type | Description | Default |
| ---- | ---- | ----------- | ------- |
| `--format` | text | Output format (human, json, jsonl); some commands also accept a template string | `human` |
| `--json` | boolean | Alias for --format json | `False` |
| `--jsonl` | boolean | Alias for --format jsonl | `False` |
| `-q`, `--quiet` | boolean | Suppress all console output | `False` |
| `-v`, `--verbose` | integer range | Increase verbosity (default: BUILD); -v for DEBUG, -vv for TRACE | `0` |
| `--log-file` | path | Path to log file (overrides default ~/.mngr/logs/<timestamp>-<pid>.json) | None |
| `--log-commands`, `--no-log-commands` | boolean | Log commands that were executed | None |
| `--log-command-output`, `--no-log-command-output` | boolean | Log stdout/stderr from commands | None |
| `--log-env-vars`, `--no-log-env-vars` | boolean | Log environment variables (security risk) | None |
| `--context` | path | Project context directory (for build context and loading project-specific config) [default: local .git root] | None |
| `--plugin`, `--enable-plugin` | text | Enable a plugin [repeatable] | None |
| `--disable-plugin` | text | Disable a plugin [repeatable] | None |

## Other Options

| Name | Type | Description | Default |
| ---- | ---- | ----------- | ------- |
| `-h`, `--help` | boolean | Show this message and exit. | `False` |

## mngr plugin list

List discovered plugins.

Shows all plugins registered with mngr, including built-in plugins
and any externally installed plugins.

Examples:

  mngr plugin list

  mngr plugin list --active

  mngr plugin list --format json

  mngr plugin list --fields name,enabled

**Usage:**

```text
mngr plugin list [OPTIONS]
```

**Options:**

## Common

| Name | Type | Description | Default |
| ---- | ---- | ----------- | ------- |
| `--format` | text | Output format (human, json, jsonl); some commands also accept a template string | `human` |
| `--json` | boolean | Alias for --format json | `False` |
| `--jsonl` | boolean | Alias for --format jsonl | `False` |
| `-q`, `--quiet` | boolean | Suppress all console output | `False` |
| `-v`, `--verbose` | integer range | Increase verbosity (default: BUILD); -v for DEBUG, -vv for TRACE | `0` |
| `--log-file` | path | Path to log file (overrides default ~/.mngr/logs/<timestamp>-<pid>.json) | None |
| `--log-commands`, `--no-log-commands` | boolean | Log commands that were executed | None |
| `--log-command-output`, `--no-log-command-output` | boolean | Log stdout/stderr from commands | None |
| `--log-env-vars`, `--no-log-env-vars` | boolean | Log environment variables (security risk) | None |
| `--context` | path | Project context directory (for build context and loading project-specific config) [default: local .git root] | None |
| `--plugin`, `--enable-plugin` | text | Enable a plugin [repeatable] | None |
| `--disable-plugin` | text | Disable a plugin [repeatable] | None |

## Other Options

| Name | Type | Description | Default |
| ---- | ---- | ----------- | ------- |
| `--active` | boolean | Show only currently enabled plugins | `False` |
| `--fields` | text | Comma-separated list of fields to display (name, version, description, enabled) | None |

## mngr plugin add

Install a plugin package.

SPECIFIER can be a PyPI package name, a local path, or a git URL.

Local paths (starting with '.', '/', or '~') are installed in editable mode.
Git URLs must start with 'git+'.

Examples:

  mngr plugin add mngr-opencode

  mngr plugin add mngr-opencode>=1.0

  mngr plugin add ./my-plugin

  mngr plugin add git+https://github.com/user/mngr-plugin.git

**Usage:**

```text
mngr plugin add [OPTIONS] SPECIFIER
```

**Options:**

## Common

| Name | Type | Description | Default |
| ---- | ---- | ----------- | ------- |
| `--format` | text | Output format (human, json, jsonl); some commands also accept a template string | `human` |
| `--json` | boolean | Alias for --format json | `False` |
| `--jsonl` | boolean | Alias for --format jsonl | `False` |
| `-q`, `--quiet` | boolean | Suppress all console output | `False` |
| `-v`, `--verbose` | integer range | Increase verbosity (default: BUILD); -v for DEBUG, -vv for TRACE | `0` |
| `--log-file` | path | Path to log file (overrides default ~/.mngr/logs/<timestamp>-<pid>.json) | None |
| `--log-commands`, `--no-log-commands` | boolean | Log commands that were executed | None |
| `--log-command-output`, `--no-log-command-output` | boolean | Log stdout/stderr from commands | None |
| `--log-env-vars`, `--no-log-env-vars` | boolean | Log environment variables (security risk) | None |
| `--context` | path | Project context directory (for build context and loading project-specific config) [default: local .git root] | None |
| `--plugin`, `--enable-plugin` | text | Enable a plugin [repeatable] | None |
| `--disable-plugin` | text | Disable a plugin [repeatable] | None |

## mngr plugin remove

Uninstall a plugin package.

SPECIFIER can be a package name or a local path. For local paths, the
package name is read from pyproject.toml. Git URLs are not supported --
use the package name instead (find it with `mngr plugin list`).

Examples:

  mngr plugin remove mngr-opencode

  mngr plugin remove ./my-plugin

**Usage:**

```text
mngr plugin remove [OPTIONS] SPECIFIER
```

**Options:**

## Common

| Name | Type | Description | Default |
| ---- | ---- | ----------- | ------- |
| `--format` | text | Output format (human, json, jsonl); some commands also accept a template string | `human` |
| `--json` | boolean | Alias for --format json | `False` |
| `--jsonl` | boolean | Alias for --format jsonl | `False` |
| `-q`, `--quiet` | boolean | Suppress all console output | `False` |
| `-v`, `--verbose` | integer range | Increase verbosity (default: BUILD); -v for DEBUG, -vv for TRACE | `0` |
| `--log-file` | path | Path to log file (overrides default ~/.mngr/logs/<timestamp>-<pid>.json) | None |
| `--log-commands`, `--no-log-commands` | boolean | Log commands that were executed | None |
| `--log-command-output`, `--no-log-command-output` | boolean | Log stdout/stderr from commands | None |
| `--log-env-vars`, `--no-log-env-vars` | boolean | Log environment variables (security risk) | None |
| `--context` | path | Project context directory (for build context and loading project-specific config) [default: local .git root] | None |
| `--plugin`, `--enable-plugin` | text | Enable a plugin [repeatable] | None |
| `--disable-plugin` | text | Disable a plugin [repeatable] | None |

## mngr plugin enable

Enable a plugin.

Sets plugins.<name>.enabled = true in the configuration file at the
specified scope.

Examples:

  mngr plugin enable modal

  mngr plugin enable modal --scope user

  mngr plugin enable modal --format json

**Usage:**

```text
mngr plugin enable [OPTIONS] NAME
```

**Options:**

## Common

| Name | Type | Description | Default |
| ---- | ---- | ----------- | ------- |
| `--format` | text | Output format (human, json, jsonl); some commands also accept a template string | `human` |
| `--json` | boolean | Alias for --format json | `False` |
| `--jsonl` | boolean | Alias for --format jsonl | `False` |
| `-q`, `--quiet` | boolean | Suppress all console output | `False` |
| `-v`, `--verbose` | integer range | Increase verbosity (default: BUILD); -v for DEBUG, -vv for TRACE | `0` |
| `--log-file` | path | Path to log file (overrides default ~/.mngr/logs/<timestamp>-<pid>.json) | None |
| `--log-commands`, `--no-log-commands` | boolean | Log commands that were executed | None |
| `--log-command-output`, `--no-log-command-output` | boolean | Log stdout/stderr from commands | None |
| `--log-env-vars`, `--no-log-env-vars` | boolean | Log environment variables (security risk) | None |
| `--context` | path | Project context directory (for build context and loading project-specific config) [default: local .git root] | None |
| `--plugin`, `--enable-plugin` | text | Enable a plugin [repeatable] | None |
| `--disable-plugin` | text | Disable a plugin [repeatable] | None |

## Other Options

| Name | Type | Description | Default |
| ---- | ---- | ----------- | ------- |
| `--scope` | choice (`user` &#x7C; `project` &#x7C; `local`) | Config scope: user (~/.mngr/profiles/<profile_id>/), project (.mngr/), or local (.mngr/settings.local.toml) | `project` |

## mngr plugin disable

Disable a plugin.

Sets plugins.<name>.enabled = false in the configuration file at the
specified scope.

Examples:

  mngr plugin disable modal

  mngr plugin disable modal --scope user

  mngr plugin disable modal --format json

**Usage:**

```text
mngr plugin disable [OPTIONS] NAME
```

**Options:**

## Common

| Name | Type | Description | Default |
| ---- | ---- | ----------- | ------- |
| `--format` | text | Output format (human, json, jsonl); some commands also accept a template string | `human` |
| `--json` | boolean | Alias for --format json | `False` |
| `--jsonl` | boolean | Alias for --format jsonl | `False` |
| `-q`, `--quiet` | boolean | Suppress all console output | `False` |
| `-v`, `--verbose` | integer range | Increase verbosity (default: BUILD); -v for DEBUG, -vv for TRACE | `0` |
| `--log-file` | path | Path to log file (overrides default ~/.mngr/logs/<timestamp>-<pid>.json) | None |
| `--log-commands`, `--no-log-commands` | boolean | Log commands that were executed | None |
| `--log-command-output`, `--no-log-command-output` | boolean | Log stdout/stderr from commands | None |
| `--log-env-vars`, `--no-log-env-vars` | boolean | Log environment variables (security risk) | None |
| `--context` | path | Project context directory (for build context and loading project-specific config) [default: local .git root] | None |
| `--plugin`, `--enable-plugin` | text | Enable a plugin [repeatable] | None |
| `--disable-plugin` | text | Disable a plugin [repeatable] | None |

## Other Options

| Name | Type | Description | Default |
| ---- | ---- | ----------- | ------- |
| `--scope` | choice (`user` &#x7C; `project` &#x7C; `local`) | Config scope: user (~/.mngr/profiles/<profile_id>/), project (.mngr/), or local (.mngr/settings.local.toml) | `project` |

## See Also

- [mngr config](./config.md) - Manage mngr configuration

## Examples

**List all plugins**

```bash
$ mngr plugin list
```

**List only active plugins**

```bash
$ mngr plugin list --active
```

**List plugins as JSON**

```bash
$ mngr plugin list --format json
```

**Show specific fields**

```bash
$ mngr plugin list --fields name,enabled
```

**Install a plugin from PyPI**

```bash
$ mngr plugin add mngr-opencode
```

**Install a local plugin**

```bash
$ mngr plugin add ./my-plugin
```

**Remove a plugin**

```bash
$ mngr plugin remove mngr-opencode
```

**Enable a plugin**

```bash
$ mngr plugin enable modal
```

**Disable a plugin**

```bash
$ mngr plugin disable modal --scope user
```
