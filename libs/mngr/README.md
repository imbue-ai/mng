# mngr: build your team of AI engineering agents

**installation**:
```bash
# TODO: update installation instructions to be better before release
git clone git@github.com:imbue-ai/mngr.git && cd mngr && uv sync --all-packages && uv tool install -e libs/mngr
```

**mngr is *very* simple to use:**

```bash
mngr                  # launch claude on Modal (defaults: command=create, agent=claude, provider=modal)
mngr --in local       # launch claude locally
mngr my-task          # launch claude with a name on Modal
mngr my-task codex    # launch codex instead of claude on Modal
mngr -- --model opus  # launch pass any arguments to the agent running on Modal

# send an initial message so you don't have to wait around:
mngr --no-connect --initial-message "Speed up one of my tests and make a PR on github"

# or, be super explicit about all of the arguments:
mngr create --name my-task --agent-type claude --in modal

# tons more arguments for anything you could want! Learn more via --help
mngr create --help

# or see the other commands--list, destroy, message, connect, push, pull, copy, and more!
mngr --help
```

**mngr is fast:**
```bash
> time mngr local-hello  --initial-message "Just say hello" --no-connect --in local
# (time results)

> time mngr remote-hello --initial-message "Just say hello" --no-connect --in modal
# (time results)

> time mngr list
# (time results)
```

**mngr itself is free, *and* the cheapest way to run remote agents (they shut down when idle):**

```bash
mngr create --in modal --no-connect --initial-message "just say 'hello'" --idle-timeout 60 -- --model sonnet
# costs $0.001 for inference
# costs $0.0001 for compute because it shuts down 60 seconds after the agent completes
```

**mngr takes security and privacy seriously:**

```bash
# by default, cannot be accessed by anyone except your modal account (uses a local unique SSH key)
mngr create example-task --in modal

# you (or your agent) can do whatever bad ideas you want in that container without fear
mngr exec example-task "rm -rf /"

# you can even completely block internet access...
mngr create --in modal --build-arg "--block-network"

# or only allow access to certain IPs
mngr create --in modal --build-arg "--cidr-allowlist 203.0.113.0/24"
```

**mngr is powerful and composable:**

```bash
# start multiple agents on the same host to save money and share data
mngr create agent-1 --in modal --host shared-host
mngr create agent-2 --in modal --host shared-host

# programmatically send messages to your agents and see their chat histories
mngr message agent-1 "Tell me a joke"
mngr transcript agent-1

# schedule agents to run periodically
mngr schedule --template my-daily-hook "look at any flaky tests over the past day and try to fix one of them" --cron "0 * * * *"

# never lose any work: snapshot and fork the entire agent states
mngr create doomed-agent --in modal
SNAPSHOT=$(mngr snapshot doomed-agent --format "{id}")
mngr message doomed-agent "try running 'rm -rf /' and see what happens"
mngr create new-agent --snapshot $SNAPSHOT
```

**mngr makes it easy to work with remote agents**

```bash
mngr connect my-agent       # directly connect to remote agents via SSH for debugging
mngr pull my-agent          # pull changes from an agent to your local machine
mngr push my-agent          # push your changes to an agent
mngr pair my-agent          # or sync changes continuously!
```

**mngr is easy to learn:**

```text
> mngr ask "How do I create a container on modal with custom packages installed by default?"

Simply run:
    mngr create --in modal --build-arg "--dockerfile path/to/Dockerfile"

If you don't have a Dockerfile for your project, run:
    mngr bootstrap

From the repo where you would like a Dockerfile created.
```

## Overview

`mngr` makes it easy to create and use any AI agent (ex: Claude Code, Codex), whether you want to run locally or remotely.

`mngr` is built on open-source tools and standards (SSH, git, tmux, docker, etc.), and has [100's of additional plugins](http://imbue.com/mngr/plugins) enable the latest AI coding workflows

## Installation

```bash
# for now, you can install like this:
git clone git@github.com:imbue-ai/mngr.git && cd mngr && uv sync --all-packages && uv tool install -e libs/mngr

# TODO: update installation instructions before release, for now, see above for installation
# run immediately without installing
# uvx mngr
# or install as a tool
# uv tool install mngr
# or install globally so that you can use across your projects
# curl -fsSL https://imbue.com/mngr/install.sh | bash
```

## Commands

```bash
# without installing:
uvx mngr <command> [options]

# if installed:
mngr <command> [options]
```

### For managing agents:

- **[`create`](docs/commands/primary/create.md)**: (default) Create and run an agent in a host
- [`list`](docs/commands/primary/list.md): List active agents
- [`connect`](docs/commands/primary/connect.md): Attach to an agent
- [`open`](docs/commands/primary/open.md) [future]: Open a URL from an agent in your browser
- [`stop`](docs/commands/primary/stop.md): Stop an agent
- [`start`](docs/commands/primary/start.md): Start a stopped agent
- [`snapshot`](docs/commands/secondary/snapshot.md) [future]: Create a snapshot of a host's state
- [`destroy`](docs/commands/primary/destroy.md): Stop an agent (and clean up any associated resources)
- [`clone`](docs/commands/aliases/clone.md): Create a copy of an existing agent
- [`migrate`](docs/commands/aliases/migrate.md): Move an agent to a different host
- [`limit`](docs/commands/secondary/limit.md) [future]: (Re)set resource limits for an agent

### For moving data in and out:

- [`pull`](docs/commands/primary/pull.md): Pull data from agent
- [`push`](docs/commands/primary/push.md): Push data to agent
- [`pair`](docs/commands/primary/pair.md): Continually sync data with an agent
- [`message`](docs/commands/secondary/message.md): Send a message to an agent
- [`provision`](docs/commands/secondary/provision.md) [future]: Re-run provisioning on an agent (useful for syncing config and auth)

### For managing mngr itself:

- [`ask`](docs/commands/secondary/ask.md): Chat with mngr for help
- [`bootstrap`](docs/commands/secondary/bootstrap.md): Generate a Dockerfile for your project
- [`plugin`](docs/commands/secondary/plugin.md) [future]: Manage mngr plugins
- [`config`](docs/commands/secondary/config.md): View and edit mngr configuration

## How it works

You can interact with `mngr` either via:

1. The terminal (run `mngr --help` to learn more)
2. One of many [web interfaces](./web_interfaces.md) (ex: [TheEye](http://ididntmakethisyet.com)) 

`mngr` uses robust open source tools like SSH, git, and tmux to run and manage your agents:

- **[agents](./docs/concepts/agents.md)** are simply [processes](TK-process) that run in [tmux](TK-tmux) sessions, each with their own `work_dir` (working folder) and configuration (ex: secrets, environment variables, etc)
- [agents](./docs/concepts/agents.md) usually expose URLs so you can access them from the web
- [agents](./docs/concepts/agents.md) run on **[hosts](./docs/concepts/hosts.md)**--either locally (by default), or special environments like [Modal]() [Sandboxes]() (`--in modal`) or [Docker]() [containers]() (`--in docker`).  Use `--host <name>` to target an existing host.
- multiple [agents](./docs/concepts/agents.md) can share a single [host](./docs/concepts/hosts.md).
- [hosts](./docs/concepts/hosts.md) come from **[providers](./docs/concepts/providers.md)** (ex: Modal, AWS, docker, etc)
- [hosts](./docs/concepts/hosts.md) help save money by automatically "pausing" when all of their [agents](./docs/concepts/agents.md) are "idle". See [idle detection](./docs/concepts/idle_detection.md)) for more details.
- [hosts](./docs/concepts/hosts.md) automatically "stop" when all of their [agents](./docs/concepts/agents.md) are "stopped"
- `mngr` is absurdly extensible--there are existing **[plugins](./docs/concepts/plugins.md)** for almost everything, and `mngr` can even [dynamically generate new plugins]()

### Architecture

`mngr` stores very little state (beyond configuration and local caches for performance), and instead relies on conventions:

- any process running in window 0 of a `mngr-` prefixed tmux sessions is considered an agent
- agents store their status, events, and logs in a standard location (default: `$MNGR_STATE_DIR/<agent_id>/`)
- all hosts are accessed via SSH--if you can SSH into it, it can be a host
- ...[and more](./docs/conventions.md)

See [`architecture.md`](./docs/architecture.md) for an in-depth overview of the `mngr` architecture and design principles.

## Security

**Best practices:**
1. Use providers with good isolation (like Docker or Modal) when working with agents, especialy those that are untrusted.
2. Follow the "principle of least privilege": only expose the minimal set of API tokens and secrets for each agent, and restrict their access (eg to the network) as much as possible.
3. Avoid storing sensitive data in agents' filesystems (or encrypt it if necessary).

See [`./docs/security_model.md`](./docs/security_model.md) for more details on our security model.

## Learning more

TODO: put a ton of examples and references here!

## Contributing

Contributions are welcome! Please see [`CONTRIBUTING.md`](/CONTRIBUTING.md) for guidelines.
