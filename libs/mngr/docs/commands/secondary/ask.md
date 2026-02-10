<!-- This file is auto-generated. Do not edit directly. -->
<!-- To modify, edit the command's help metadata and run: uv run python scripts/make_cli_docs.py -->

# mngr ask

**Synopsis:**

```text
mngr ask [QUERY...] [--execute]
```


[future] Chat with mngr for help.

Ask mngr a question and it will generate the appropriate CLI command.
If no query is provided, shows general help.

Examples:

  mngr ask "how do I create an agent?"

  mngr ask start a container with claude code

  mngr ask --execute forward port 8080 to the public internet

**Usage:**

```text
mngr ask [OPTIONS] [QUERY]...
```

## Arguments

- `QUERY`: The query (optional)

**Options:**

## Behavior

| Name | Type | Description | Default |
| ---- | ---- | ----------- | ------- |
| `--execute` | boolean | [future] Execute the generated CLI command instead of just printing it | `False` |

## Common

| Name | Type | Description | Default |
| ---- | ---- | ----------- | ------- |
| `--format` | choice (`human` &#x7C; `json` &#x7C; `jsonl`) | Output format for command results | `human` |
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

## See Also

- [mngr create](../primary/create.md) - Create an agent
- [mngr list](../primary/list.md) - List existing agents
- [mngr connect](../primary/connect.md) - Connect to an agent

## Examples

**Ask a question**

```bash
$ mngr ask "how do I create an agent?"
```

**Ask without quotes**

```bash
$ mngr ask start a container with claude code
```

**Execute the generated command**

```bash
$ mngr ask --execute forward port 8080 to the public internet
```
