# mngr create - CLI Options Reference

Create and run an agent.

`mngr create` is responsible for setting up the agent's work_dir, provisioning a new host (if requested), running the specified agent, and (by default) connecting to it.

**Alias:** `c`

## Usage

```
mngr create [OPTIONS] [NAME] [AGENT_TYPE] -- [AGENT_ARGS]...
```

## Arguments

- `NAME`: Name for the agent (auto-generated if not provided)
- `AGENT_TYPE`: Which type of agent to run (default: `claude`). Can also be specified via `--agent-type`
- `AGENT_ARGS`: Additional arguments passed to the agent

## Behavior

- `--[no-]connect`: Connect to an agent after creation (disconnecting will not destroy the agent) [default: connect]
- `--[no-]await-ready`: Wait until the agent is ready before returning (only applies if `--no-connect` is specified, changes when the command returns) [default: no-await-ready if --no-connect]
- `--[no-]copy-work-dir`: Immediately make a copy of the source work_dir. Useful when launching background agents so that you can continue editing locally without worrying about invalid content being copied into the new agent [default: copy if --no-connect, no-copy if --connect]
- `--[no-]ensure-clean`: Abort if git in the source work_dir has uncommitted changes [default: ensure-clean]
- `--[no-]snapshot-source`: Snapshot source agent before cloning [default: snapshot-source when `--source-agent` is specified and not local]

## Connection Options

See [connect options](./connect.md) (only applies if `--connect` is specified)

## Agent Options

- `--agent-type TEXT`: Which type of agent to run [default: `claude`]
- `-n, --name TEXT`: Agent name (alternative to positional argument) [default: auto-generated]
- `--name-style STYLE`: Auto-generated name style [choices: `english`, `fantasy`, `scifi`, `painters`, `authors`, `artists`, `musicians`, `animals`, `scientists`, `demons`]
- `--agent-cmd, --agent-command TEXT`: Run a literal command using the generic agent type. Mutually exclusive with `--agent-type` (ex: `--agent-cmd "sleep 1000"`)
- `-c, --add-cmd, --add-command TEXT`: Run an extra command in additional tmux window [repeatable]. Use `name=command` syntax to set window name (e.g., `-c server="npm run dev"` or `-c reviewer_1=claude`). Note: ALL_UPPERCASE names are treated as env var assignments, not window names
- `--user TEXT`: Override which user to run the agent as [default: if local, current user. if remote, as defined in the provider, or `root` if not specified]

## Agent Source Data (what to include in the new agent)

- `--from SOURCE`: Alias for `--source`
- `--source SOURCE`: Directory to use as work_dir root. Accepts a unified syntax: `[AGENT | AGENT.HOST | AGENT.HOST:PATH | HOST:PATH]` See below for examples. [default: nearest `.git` parent on 'local']
- `--source-agent AGENT`: Source agent [alias: `--from-agent`]
- `--source-host HOST`: Source host
- `--source-path PATH`: Source path
- `--include TEXT`: Include additional files matching glob pattern [repeatable]
- `--exclude TEXT`: Exclude files matching glob pattern [repeatable]
- `--include-file PATH`: Read include patterns from file
- `--exclude-file PATH`: Read exclude patterns from file
- `--[no-]include-git`: Include data from the `.git` directory [default: include-git]
- `--include-unclean / --exclude-unclean`: Include staged, unstaged, and untracked files. [default: include if --no-ensure-clean, exclude if --ensure-clean]
- `--[no-]include-gitignored`: Include files matching `.gitignore` [default: no-include-gitignored]

# Agent Target (where to put the new agent)

- `--target TARGET`: Target. Accepts a unified syntax: `[HOST][:PATH]` See below for examples.
- `--target-host HOST`: Target host [alias: `--in-host`]
- `--target-path PATH`: Directory to mount source inside agent host. Incompatible with `--in-place`
- `--in-place`: Run directly in source directory. Incompatible with `--target-path`
- `--copy`: Copy source to isolated directory before running [default for remote agents, and for local agents if not in a git repo]
- `--clone`: Create a git clone that shares objects with the original repo (only works for local agents)
- `--worktree`: Create a git worktree that shares objects and index with the original repo [default for local agents in a git repo]. Note: implies `--new-branch`

## Agent Git Configuration

- `--base-branch TEXT`: The starting point for the agent [default: current branch]
- `--new-branch TEXT / --no-new-branch`: Create a fresh branch for the agent's work (named TEXT if provided, otherwise auto-generated). The new branch is created from `--base-branch` [default: --no-new-branch unless --worktree is used]
- `--new-branch-prefix TEXT`: Prefix for auto-generated branch names [default: `mngr/`]
- `--depth INTEGER`: Shallow clone depth [default: full]
- `--shallow-since DATE`: Shallow clone since date

## Agent Environment Variables

- `--env, --agent-env TEXT`: Set an environment variable KEY=VALUE for the agent [repeatable]
- `--env-file, --agent-env-file PATH`: Load variables from env file for the agent [repeatable]
- `--pass-env, --pass-agent-env TEXT`: Forward a variable from your current shell for the agent [repeatable]

## Agent Provisioning

See [Provision Options](../secondary/provision.md)

## Agent Limits

See [Limit Options](../secondary/limit.md)

---

## Host Options

By default, `mngr create` uses the "local" host. Use these options to change that behavior:

- `--host HOST`: Use an existing host (by name or ID) [default: local]
- `--in, --new-host [PROVIDER]`: Create a new host using the specified provider (docker, modal, ...).

### New Host Identification

- `--host-name TEXT`: Name for the new host
- `--host-name-style STYLE`: Auto-generated name style [choices: `astronomy`, `places`, `cities`, `fantasy`, `scifi`, `painters`, `authors`, `artists`, `musicians`, `scientists`]
- `--tag TEXT`: Metadata tag KEY=VALUE [repeatable]
- `--project TEXT`: Project name for the agent [default: derived from git remote origin or folder name]

## New Host Environment Variables

- `--host-env TEXT`: Set an environment variable KEY=VALUE for the host [repeatable]
- `--host-env-file PATH`: Load variables from env file for the host [repeatable]
- `--pass-host-env TEXT`: Forward a variable from your current shell for the host [repeatable]

### New Host Build

- `--snapshot TEXT`: Use existing snapshot instead of building
- `-b, --build, --build-arg TEXT`: Argument for calling "build" on the provider (e.g. passed to `docker build`) [repeatable]
- `--build-args TEXT`: Space-separated build arguments (alternative to -b for convenience)
- `-s, --start, --start-arg TEXT`: Argument for calling "start" on the provider (e.g. passed to `docker run`) [repeatable]
- `--start-args TEXT`: Space-separated start arguments (alternative to -s for convenience)

## Common

See [Common Options](../generic/common.md)

## Examples

```bash
# Create an agent locally in a new git worktree (default for git repos)
mngr create my-agent

# Create an agent with a specific name in a Modal sandbox
mngr create my-agent --in modal

# Create an agent without specifying a name (auto-generated)
mngr create --in docker

# Run codex instead of claude (the default)
mngr create my-agent --agent-type codex

# Pass args to the agent
mngr create my-agent -- --model opus

# Create an agent on an existing host
mngr create my-agent --host my-dev-box

# Run directly in-place (no worktree/copy)
mngr create my-agent --in-place

# Create a new agent locally by cloning from an existing remote agent
mngr create my-agent --source other-agent.my-host:/my/code/dir

# Run additional commands in named tmux windows
mngr create my-agent -c server="npm run dev" -c tests="npm test --watch"
```

## TODOs

The following features are documented but not fully implemented:

- `--snapshot-source`: Backend function raises `NotImplementedError`
- `--snapshot`: CLI option parsed but not passed to provider's `create_host()` method
- `--host-env`, `--host-env-file`, `--pass-host-env`: Parsed in CLI but not passed to provider (host environment variables are unused)
- Remote source support: Project name derivation and git branch detection fail for remote hosts
