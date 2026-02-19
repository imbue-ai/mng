# mng: build your team of AI engineering agents

**installation:**
```bash
curl -fsSL https://raw.githubusercontent.com/imbue-ai/mngr/main/scripts/install.sh | bash
```

**mng is *very* simple to use:**

```bash
mng                  # launch claude locally (defaults: command=create, agent=claude, provider=local, project=current dir)
mng --in modal       # launch claude on Modal
mng my-task          # launch claude with a name
mng my-task codex    # launch codex instead of claude
mng -- --model opus  # pass any arguments through to the underlying agent

# send an initial message so you don't have to wait around:
mng --no-connect --message "Speed up one of my tests and make a PR on github"

# or, be super explicit about all of the arguments:
mng create --name my-task --agent-type claude --in modal

# tons more arguments for anything you could want! Learn more via --help
mng create --help

# or see the other commands--list, destroy, message, connect, push, pull, clone, and more!
mng --help
```

**mng is fast:**
```bash
> time mng local-hello  --message "Just say hello" --no-connect --in local
# (time results)

> time mng remote-hello --message "Just say hello" --no-connect --in modal
# (time results)

> time mng list
# (time results)
```

**mng itself is free, *and* the cheapest way to run remote agents (they shut down when idle):**

```bash
mng create --in modal --no-connect --message "just say 'hello'" --idle-timeout 60 -- --model sonnet
# costs $0.001 for inference
# costs $0.0001 for compute because it shuts down 60 seconds after the agent completes
```

**mng takes security and privacy seriously:**

```bash
# by default, cannot be accessed by anyone except your modal account (uses a local unique SSH key)
mng create example-task --in modal

# you (or your agent) can do whatever bad ideas you want in that container without fear
mng exec example-task "rm -rf /"

# you can block all outgoing internet access
mng create --in modal -b offline

# or restrict outgoing traffic to certain IPs
mng create --in modal -b cidr-allowlist=203.0.113.0/24
```

**mng is powerful and composable:**

```bash
# start multiple agents on the same host to save money and share data
mng create agent-1 --in modal --host-name shared-host
mng create agent-2 --host shared-host

# run commands directly on an agent's host
mng exec agent-1 "git log --oneline -5"

# never lose any work: snapshot and fork the entire agent states
mng create doomed-agent --in modal
SNAPSHOT=$(mng snapshot doomed-agent --format "{id}")
mng message doomed-agent "try running 'rm -rf /' and see what happens"
mng create new-agent --snapshot $SNAPSHOT
```

<!--
# programmatically send messages to your agents and see their chat histories
mng message agent-1 "Tell me a joke"
mng transcript agent-1   # [future]

# [future] schedule agents to run periodically
mng schedule --template my-daily-hook "look at any flaky tests over the past day and try to fix one of them" --cron "0 * * * *"
-->

**mng makes it easy to work with remote agents**

```bash
mng connect my-agent       # directly connect to remote agents via SSH for debugging
mng pull my-agent          # pull changes from an agent to your local machine
mng push my-agent          # push your changes to an agent
mng pair my-agent          # or sync changes continuously!
```

**mng is easy to learn:**

```text
> mng ask "How do I create a container on modal with custom packages installed by default?"

Simply run:
    mng create --in modal --build-arg "--dockerfile path/to/Dockerfile"
```

<!--
If you don't have a Dockerfile for your project, run:
    mng bootstrap   # [future]

From the repo where you would like a Dockerfile created.
-->

## Overview

`mng` makes it easy to create and use any AI agent (ex: Claude Code, Codex), whether you want to run locally or remotely.

`mng` is built on open-source tools and standards (SSH, git, tmux, docker, etc.), and is extensible via [plugins](./docs/concepts/plugins.md) to enable the latest AI coding workflows.

## Installation

**Quick install** (installs system dependencies + mng automatically):
```bash
curl -fsSL https://raw.githubusercontent.com/imbue-ai/mngr/main/scripts/install.sh | bash
```

**Manual install** (requires [uv](https://docs.astral.sh/uv/) and system deps: `git`, `tmux`, `jq`, `rsync`, `unison`):
```bash
uv tool install mng

# or run without installing
uvx mng
```

**Upgrade:**
```bash
uv tool upgrade mng
```

**For development:**
```bash
git clone git@github.com:imbue-ai/mngr.git && cd mngr && uv sync --all-packages && uv tool install -e libs/mng
```

## Shell Completion

`mng` supports tab completion for commands and agent names in bash, zsh, and fish.

**Zsh** (add to `~/.zshrc`):
```bash
eval "$(_MNG_COMPLETE=zsh_source mng)"
```

**Bash** (add to `~/.bashrc`):
```bash
eval "$(_MNG_COMPLETE=bash_source mng)"
```

**Fish** (run once):
```bash
_MNG_COMPLETE=fish_source mng > ~/.config/fish/completions/mng.fish
```

Note: `mng` must be installed on your PATH for completion to work (not invoked via `uv run`).

## Commands

```bash
# without installing:
uvx mng <command> [options]

# if installed:
mng <command> [options]
```

### For managing agents:

- **[`create`](docs/commands/primary/create.md)**: (default) Create and run an agent in a host
- [`list`](docs/commands/primary/list.md): List active agents
- [`connect`](docs/commands/primary/connect.md): Attach to an agent
<!-- - [`open`](docs/commands/primary/open.md) [future]: Open a URL from an agent in your browser -->
- [`stop`](docs/commands/primary/stop.md): Stop an agent
- [`start`](docs/commands/primary/start.md): Start a stopped agent
- [`snapshot`](docs/commands/secondary/snapshot.md) [experimental]: Create a snapshot of a host's state
- [`destroy`](docs/commands/primary/destroy.md): Stop an agent (and clean up any associated resources)
- [`exec`](docs/commands/primary/exec.md): Execute a shell command on an agent's host
- [`rename`](docs/commands/primary/rename.md): Rename an agent
- [`clone`](docs/commands/aliases/clone.md): Create a copy of an existing agent
- [`migrate`](docs/commands/aliases/migrate.md): Move an agent to a different host
- [`limit`](docs/commands/secondary/limit.md): Configure limits for agents and hosts

### For moving data in and out:

- [`pull`](docs/commands/primary/pull.md): Pull data from agent
- [`push`](docs/commands/primary/push.md): Push data to agent
- [`pair`](docs/commands/primary/pair.md): Continually sync data with an agent
- [`message`](docs/commands/secondary/message.md): Send a message to an agent
- [`provision`](docs/commands/secondary/provision.md): Re-run provisioning on an agent (useful for syncing config and auth)

### For maintenance:

- [`cleanup`](docs/commands/secondary/cleanup.md): Clean up stopped agents and unused resources
- [`logs`](docs/commands/secondary/logs.md): View agent and host logs
- [`gc`](docs/commands/secondary/gc.md): Garbage collect unused resources

### For managing mng itself:

- [`ask`](docs/commands/secondary/ask.md): Chat with mng for help
- [`plugin`](docs/commands/secondary/plugin.md) [experimental]: Manage mng plugins
- [`config`](docs/commands/secondary/config.md): View and edit mng configuration

## How it works

You can interact with `mng` via the terminal (run `mng --help` to learn more).
<!-- You can also interact via one of many [web interfaces](./web_interfaces.md) [future] (ex: [TheEye](http://ididntmakethisyet.com)) -->

`mng` uses robust open source tools like SSH, git, and tmux to run and manage your agents:

- **[agents](./docs/concepts/agents.md)** are simply processes that run in [tmux](https://github.com/tmux/tmux/wiki) sessions, each with their own `work_dir` (working folder) and configuration (ex: secrets, environment variables, etc)
<!-- - [agents](./docs/concepts/agents.md) usually expose URLs so you can access them from the web [future: mng open] -->
- [agents](./docs/concepts/agents.md) run on **[hosts](./docs/concepts/hosts.md)**--either locally (by default), or special environments like [Modal](https://modal.com) [Sandboxes](https://modal.com/docs/guide/sandboxes) (`--in modal`) or [Docker](https://www.docker.com) [containers](https://docs.docker.com/get-started/docker-concepts/the-basics/what-is-a-container/) (`--in docker`).  Use `--host <name>` to target an existing host.
- multiple [agents](./docs/concepts/agents.md) can share a single [host](./docs/concepts/hosts.md).
- [hosts](./docs/concepts/hosts.md) come from **[providers](./docs/concepts/providers.md)** (ex: Modal, AWS, docker, etc)
- [hosts](./docs/concepts/hosts.md) help save money by automatically "pausing" when all of their [agents](./docs/concepts/agents.md) are "idle". See [idle detection](./docs/concepts/idle_detection.md) for more details.
- [hosts](./docs/concepts/hosts.md) automatically "stop" when all of their [agents](./docs/concepts/agents.md) are "stopped"
- `mng` is extensible via **[plugins](./docs/concepts/plugins.md)**--you can add new agent types, provider backends, CLI commands, and lifecycle hooks
<!-- - `mng` is absurdly extensible--there are existing **[plugins](./docs/concepts/plugins.md)** for almost everything, and `mng` can even [dynamically generate new plugins](docs/commands/secondary/plugin.md#mng-plugin-generate) [future] -->

### Architecture

`mng` stores very little state (beyond configuration and local caches for performance), and instead relies on conventions:

- any process running in window 0 of a `mng-` prefixed tmux sessions is considered an agent
- agents store their status and logs in a standard location (default: `$MNG_HOST_DIR/agents/<agent_id>/`)
- all hosts are accessed via SSH--if you can SSH into it, it can be a host
- ...[and more](./docs/conventions.md)

See [`architecture.md`](./docs/architecture.md) for an in-depth overview of the `mng` architecture and design principles.

## Security

**Best practices:**
1. Use providers with good isolation (like Docker or Modal) when working with agents, especially those that are untrusted.
2. Follow the "principle of least privilege": only expose the minimal set of API tokens and secrets for each agent, and restrict their access (eg to the network) as much as possible.
3. Avoid storing sensitive data in agents' filesystems (or encrypt it if necessary).

See [`./docs/security_model.md`](./docs/security_model.md) for more details on our security model.

<!--
## Learning more

TODO: put a ton of examples and references here!
-->

## Contributing

Contributions are welcome!
<!-- Please see [`CONTRIBUTING.md`](/CONTRIBUTING.md) for guidelines. [future] -->
