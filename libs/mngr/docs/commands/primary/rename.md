<!-- This file is auto-generated. Do not edit directly. -->
<!-- To modify, edit the command's help metadata and run: uv run python scripts/make_cli_docs.py -->

# mngr rename

**Synopsis:**

```text
mngr [rename|mv] <CURRENT> <NEW-NAME> [--dry-run] [--host]
```


Rename an agent or host.

Renames the agent's data.json and tmux session (if running).
Git branch names are not renamed.

If a previous rename was interrupted, re-running the command
will attempt to finish it.

Alias: mv

Examples:

  mngr rename my-agent new-name

  mngr rename my-agent new-name --dry-run

**Usage:**

```text
mngr rename [OPTIONS] CURRENT NEW-NAME
```

## Arguments

- `CURRENT`: Current name or ID of the agent to rename
- `NEW-NAME`: New name for the agent

**Options:**

## Behavior

| Name | Type | Description | Default |
| ---- | ---- | ----------- | ------- |
| `--dry-run` | boolean | Show what would be renamed without actually renaming | `False` |
| `--host` | boolean | Rename a host instead of an agent [future] | `False` |

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

- [mngr list](./list.md) - List existing agents
- [mngr create](./create.md) - Create a new agent
- [mngr destroy](./destroy.md) - Destroy an agent

## Examples

**Rename an agent**

```bash
$ mngr rename my-agent new-name
```

**Preview what would be renamed**

```bash
$ mngr rename my-agent new-name --dry-run
```

**Use the alias**

```bash
$ mngr mv my-agent new-name
```
