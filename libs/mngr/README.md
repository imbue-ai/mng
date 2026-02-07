# mngr

**Effortlessly run Claude Code (or any agent) in a remote sandbox via the CLI, locally in a new worktree, or whatever you want!**

```bash
# install
# TODO: update installation instructions to be better before release
git clone git@github.com:imbue-ai/mngr.git && cd mngr && uv sync --all-packages && uv tool install -e libs/mngr

# then use mngr:
mngr create my-agent --in modal  # create an agent in a Modal sandbox and instantly connect to it
mngr create my-agent             # or just run locally in a new worktree to try it out!
```

**Easily transfer data (and agents) back and forth, script your own workflows, and access all of your agents via the web**

```bash
mngr pull my-agent # pull changes from an agent to your local machine
mngr push my-agent # push your changes to an agent
mngr pair my-agent # or sync changes continuously!
mngr migrate my-agent modal # move an existing local agent to the cloud
mngr message my-agent fix the tests on main # send a message to an agent
mngr open my-agent # access the agent's terminal and web UIs via a secure web interface
```

**See the status of all your agents in a single place--whether they're blocked, done, whether the tests pass, etc**

```bash
mngr list  # see all your agents and their status
# TODO: show some example output here
```

**Save money by automatically suspending idle agents**

```bash
mngr connect my-agent  # after 5 minutes without typing, the agent will automatically suspend itself
```

**Never lose any work: snapshot and fork the entire agent state**

```bash
mngr message my-agent try running rm -rf /  # or try doing something unhinged...
mngr create new-agent --snapshot `mngr snapshot list my-agent --format "{id}"` # ...and then recover from it!
mngr snapshot new-agent  # make a snapshot of any agent's current state
mngr clone another-agent forked-agent  # or create a copy of any existing agent 
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
- [`clone`](docs/commands/aliases/clone.md) [future]: Create a copy of an existing agent
- [`migrate`](docs/commands/aliases/migrate.md) [future]: Move an agent to a different host
- [`limit`](docs/commands/secondary/limit.md) [future]: (Re)set resource limits for an agent

### For moving data in and out:

- [`pull`](docs/commands/primary/pull.md): Pull data from agent
- [`push`](docs/commands/primary/push.md): Push data to agent
- [`pair`](docs/commands/primary/pair.md): Continually sync data with an agent
- [`message`](docs/commands/secondary/message.md): Send a message to an agent
- [`provision`](docs/commands/secondary/provision.md) [future]: Re-run provisioning on an agent (useful for syncing config and auth)

### For managing mngr itself:

- [`ask`](docs/commands/secondary/ask.md) [future]: Chat with mngr for help
- [`plugin`](docs/commands/secondary/plugin.md) [future]: Manage mngr plugins
- [`config`](docs/commands/secondary/config.md): View and edit mngr configuration

## Examples

TODO: put a ton of examples here!

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

## Contributing

Contributions are welcome! Please see [`CONTRIBUTING.md`](/CONTRIBUTING.md) for guidelines.
