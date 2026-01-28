# mngr create

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

## See Also

- [mngr connect](./connect.md) - Connect to an existing agent
- [mngr list](./list.md) - List existing agents
- [mngr destroy](./destroy.md) - Destroy agents

## Examples

**Create an agent locally in a new git worktree (default)**

```bash
$ mngr create my-agent
```

**Create an agent in a Docker container**

```bash
$ mngr create my-agent --in docker
```

**Create an agent in a Modal sandbox**

```bash
$ mngr create my-agent --in modal
```

**Create a codex agent instead of claude**

```bash
$ mngr create my-agent codex
```

**Pass arguments to the agent**

```bash
$ mngr create my-agent -- --model opus
```

**Create on an existing host**

```bash
$ mngr create my-agent --host my-dev-box
```

**Clone from an existing agent**

```bash
$ mngr create new-agent --source other-agent
```

**Run directly in-place (no worktree)**

```bash
$ mngr create my-agent --in-place
```

**Create without connecting**

```bash
$ mngr create my-agent --no-connect
```

**Add extra tmux windows**

```bash
$ mngr create my-agent -c server="npm run dev"
```
