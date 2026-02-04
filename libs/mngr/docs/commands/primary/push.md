<!-- This file is auto-generated. Do not edit directly. -->
<!-- To modify, edit the command's help metadata and run: uv run python scripts/make_cli_docs.py -->

# mngr push

Push files or git commits from local machine to an agent.

Syncs files or git state from a local directory to an agent's working directory.
Default behavior uses rsync for efficient incremental file transfer.
Use --sync-mode=git to push git branches instead of syncing files.

If no target is specified, shows an interactive selector to choose an agent.

IMPORTANT: The source (host) workspace is never modified. Only the target
(agent workspace) may be modified.

Examples:
  mngr push my-agent
  mngr push my-agent ./local-dir
  mngr push my-agent:subdir ./local-src
  mngr push --target-agent my-agent --source ./local-dir
  mngr push my-agent --sync-mode=git
  mngr push my-agent --sync-mode=git --mirror

**Usage:**

```text
mngr push [OPTIONS] [TARGET] [SOURCE]
```

## Arguments

- `TARGET`: The target (optional)
- `SOURCE`: The source (optional)

**Options:**

## Target Selection

| Name | Type | Description | Default |
| ---- | ---- | ----------- | ------- |
| `--target` | text | Target specification: AGENT, AGENT:PATH, or PATH | None |
| `--target-agent` | text | Target agent name or ID | None |
| `--target-host` | text | Target host name or ID | None |
| `--target-path` | text | Path within the agent's work directory | None |

## Source

| Name | Type | Description | Default |
| ---- | ---- | ----------- | ------- |
| `--source` | path | Local source directory [default: .] | None |

## Sync Options

| Name | Type | Description | Default |
| ---- | ---- | ----------- | ------- |
| `--dry-run` | boolean | Show what would be transferred without actually transferring | `False` |
| `--stop` | boolean | Stop the agent after pushing (for state consistency) | `False` |
| `--delete`, `--no-delete` | boolean | Delete files in destination that don't exist in source | `False` |
| `--sync-mode` | choice (`files` &#x7C; `git` &#x7C; `full`) | What to sync: files (working directory via rsync), git (push git branches), or full (everything) | `files` |
| `--exclude` | text | Patterns to exclude from sync [repeatable] | None |
| `--source-branch` | text | Branch to push from (git mode only) [default: current branch] | None |
| `--uncommitted-changes` | choice (`stash` &#x7C; `clobber` &#x7C; `merge` &#x7C; `fail`) | How to handle uncommitted changes in the agent workspace: stash (stash and leave stashed), clobber (overwrite), merge (stash, push, unstash), fail (error if changes exist) | `fail` |

## Git Options

| Name | Type | Description | Default |
| ---- | ---- | ----------- | ------- |
| `--mirror` | boolean | Use git push --mirror (dangerous: overwrites all refs in target). Only applies to git mode. | `False` |
| `--rsync-only` | boolean | Use rsync even if git is available in both source and destination | `False` |

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
