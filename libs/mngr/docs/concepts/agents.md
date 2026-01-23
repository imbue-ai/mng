# Agents

An agent is a process running in tmux that `mngr` manages.

Each agent runs inside a properly-named tmux session (e.g. `mngr-<agent-id>`) inside a working directory on a [host](./hosts.md).

Each agent has a name, a unique identifier (`agent-id`), and is a particular ["agent type"](agent_types.md)

Nothing stops you from creating additional invocations of agent programs inside the tmux session (e.g. launching multiple Claude Code's), but only the main agent process for a given tmux session is considered by `mngr`.

## Passing Arguments

Arguments after `--` go directly to the agent command:

```bash
mngr create my-agent claude -- --model opus
```

To see what arguments an agent accepts, use `mngr create my-agent <type> -- --help`.

## Overriding Defaults

You can override plugin defaults:

```bash
mngr create my-agent claude --idle-timeout 1h      # Override timeout
```

## Running a Custom Command

Use `--agent-cmd` (or `--agent-command`) to run a literal command instead of using an agent type:

```bash
mngr create my-agent --agent-cmd "sleep 1000"      # Run a simple command
mngr create my-agent --agent-cmd "./my-script.sh"  # Run a custom script
```

The `--agent-cmd` flag implicitly uses the "generic" agent type, which simply runs the provided command without any special handling. This means `--agent-cmd` and `--agent-type` are mutually exclusive: you either specify an agent type (like `claude` or `codex`), or you provide a literal command to run.

See [`mngr create`](../commands/primary/create.md) for all available options.

## Capbilities

Any unix process can be an agent, which means that the only strict requirement is that the program run in a properly-named tmux session (e.g. "mngr-<agent_name>").

Many (most) programs that you want to run as agents will support additional "capabilities" that `mngr` can leverage to provide extra functionality, for example:

- Agents can put their "status" in a special file that `mngr` reads to show in `mngr list` (for example, "Thinking...", "Waiting for input", etc.)
- Agents can self-report when they are active (which enables automatic shutdown of "idle" hosts), see [idle detection](./idle_detection.md) for details
- Agents can expose URLs for web interfaces (and the default plugins automatically create a secure web terminal via ttyd for CLI agents)
- Agents can be sent messages via `mngr message` (for example, to provide user input or commands). This applies to all unix process (since we're just writing to stdin).
- Agents can be created recursively (and, with the `recursive_mngr` plugin, understand their "parent" agents and create remote child agents as well).
- Agents can have a list of "permissions" that control both what they are allowed to do and what information they have access to. See [permissions](./permissions.md) for more details.
- Agents can define custom properties for any additional functionality (e.g., providing a stream of events, exposing a REST API, etc.)

## Hierarchy

Agents can create other agents via recursive invocations of `mngr`.

```bash
# Inside an agent, create a child agent
mngr create sub-task-agent claude
```

By default, the `mngr` binary only exposes the "local" provider, which means that these child agents run on the same host as the parent.

If you want to allow agents to create remote/untrusted child agents, see the [recursive mngr plugin](../../specs/plugins/recursive_mngr.md) for security considerations and more details.

## Lifecycle

An agent can be in one of the following states:

- **stopped**: the agent folder exists (but there is no tmux session)
- **running**: tmux session exists and the expected process exists in pane 0
- **replaced**: tmux session exists and a different process in pane 0
- **done**: the tmux session exists and there is no process under the shell for that pane

## Properties

See [agent spec](../../specs/agent.md) for the properties of agents and their storage locations.

You can also run [`mngr list --help`](../commands/primary/list.md#available-fields) for the full list.

## Interface

See [`imbue/mngr/interfaces/agent.py`](../../imbue/mngr/interfaces/agent.py) for the agent data structures.
