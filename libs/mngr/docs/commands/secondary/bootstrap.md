<!-- This file is auto-generated. Do not edit directly. -->
<!-- To modify, edit the command's help metadata and run: uv run python scripts/make_cli_docs.py -->

# mngr bootstrap

**Synopsis:**

```text
mngr bootstrap [--output PATH] [--force] [--dry-run] [--project-dir DIR]
```


Generate a Dockerfile for your project.

Analyzes the current project directory and uses AI to generate an
appropriate Dockerfile at .mngr/Dockerfile. This Dockerfile can then
be used with mngr create --build-arg "--dockerfile .mngr/Dockerfile".

**Usage:**

```text
mngr bootstrap [OPTIONS]
```

**Options:**

## Bootstrap

| Name | Type | Description | Default |
| ---- | ---- | ----------- | ------- |
| `--output` | path | Output path for the generated Dockerfile [default: .mngr/Dockerfile] | None |
| `--force` | boolean | Overwrite existing Dockerfile | `False` |
| `--dry-run` | boolean | Print the generated Dockerfile to stdout instead of writing it | `False` |
| `--project-dir` | path | Directory to analyze [default: current working directory] | None |

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
- [mngr ask](./ask.md) - Chat with mngr for help

## Examples

**Generate a Dockerfile**

```bash
$ mngr bootstrap
```

**Preview without writing**

```bash
$ mngr bootstrap --dry-run
```

**Overwrite existing**

```bash
$ mngr bootstrap --force
```

**Specify project directory**

```bash
$ mngr bootstrap --project-dir /path/to/project
```
