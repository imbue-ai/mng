<!-- This file is auto-generated. Do not edit directly. -->
<!-- To modify, edit the command's help metadata and run: uv run python scripts/make_cli_docs.py -->

# mngr provision

**Synopsis:**

```text
mngr [provision|prov] [AGENT] [--agent <AGENT>] [--user-command <CMD>] [--upload-file <LOCAL:REMOTE>] [--env <KEY=VALUE>]
```


Re-run provisioning on an existing agent.

This re-runs the provisioning steps (plugin lifecycle hooks, file transfers,
user commands, env vars) on an agent that has already been created. Useful for
syncing config, auth, and installing additional packages.

The agent's existing environment variables are preserved. New env vars from
--env, --env-file, and --pass-env override existing ones with the same key.

The command runs regardless of whether the agent is running or stopped.
Provisioning steps are designed to be idempotent. Note that provisioning a
running agent may cause brief disruption if config files are overwritten
while the agent is actively reading them.

Alias: prov

Examples:

  mngr provision my-agent

  mngr provision my-agent --user-command "pip install pandas"

  mngr provision my-agent --env "NEW_VAR=value"

  mngr provision my-agent --upload-file ./config.json:/app/config.json

**Usage:**

```text
mngr provision [OPTIONS] [AGENT]
```

## Arguments

- `AGENT`: Agent name or ID to provision

**Options:**

## Target Selection

| Name | Type | Description | Default |
| ---- | ---- | ----------- | ------- |
| `--agent` | text | Agent name or ID to provision (alternative to positional argument) | None |
| `--host` | text | Filter by host name or ID [future] | None |

## Agent Provisioning

| Name | Type | Description | Default |
| ---- | ---- | ----------- | ------- |
| `--user-command` | text | Run custom shell command during provisioning [repeatable] | None |
| `--sudo-command` | text | Run custom shell command as root during provisioning [repeatable] | None |
| `--upload-file` | text | Upload LOCAL:REMOTE file pair [repeatable] | None |
| `--append-to-file` | text | Append REMOTE:TEXT to file [repeatable] | None |
| `--prepend-to-file` | text | Prepend REMOTE:TEXT to file [repeatable] | None |
| `--create-directory` | text | Create directory on remote [repeatable] | None |

## Agent Environment Variables

| Name | Type | Description | Default |
| ---- | ---- | ----------- | ------- |
| `--env`, `--agent-env` | text | Set environment variable KEY=VALUE | None |
| `--env-file`, `--agent-env-file` | path | Load env file | None |
| `--pass-env`, `--pass-agent-env` | text | Forward variable from shell | None |

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

- [mngr create](../primary/create.md) - Create and run an agent
- [mngr connect](../primary/connect.md) - Connect to an agent
- [mngr list](../primary/list.md) - List existing agents

## Examples

**Re-provision an agent**

```bash
$ mngr provision my-agent
```

**Install a package**

```bash
$ mngr provision my-agent --user-command 'pip install pandas'
```

**Upload a config file**

```bash
$ mngr provision my-agent --upload-file ./config.json:/app/config.json
```

**Set an environment variable**

```bash
$ mngr provision my-agent --env 'API_KEY=secret'
```

**Run a root command**

```bash
$ mngr provision my-agent --sudo-command 'apt-get install -y ffmpeg'
```
