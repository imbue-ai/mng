# mngr push - CLI Options Reference

Syncs git state and/or files to one agent (or host) from another agent (or host)

By default, syncs from somewhere on your local host to an agent.

This is the equivalent of a "manual sync" operation, pushing your local changes to the remote agent host.

## Usage

```
mngr push [(--agent) agent [other-agent]]
```

When two agents are provided, syncs from the first agent to the second agent (instead of from local).

## General

- `--source SOURCE`: Where to pull from. Accepts a unified syntax: `[AGENT | AGENT.HOST | AGENT.HOST:PATH | HOST:PATH]` [default: local current directory]
- `--source-agent AGENT`: Source agent
- `--source-host HOST`: Source host
- `--source-path PATH`: Source path
- `--target TARGET`: Where to pull to. Accepts a unified syntax: `[AGENT | AGENT.HOST | AGENT.HOST:PATH | HOST:PATH]` [default: agent's work_dir if `--target-agent`, otherwise host root]
- `--target-agent TARGET`: Target agent.
- `--target-host HOST`: Target host.
- `--target-path PATH`: Directory to mount source inside agent host.
- `--stdin`: Read sources (agents and hosts, ids or names) from stdin (one per line)
- `--rsync-arg ARG`: Additional argument to pass to rsync command [repeatable]
- `--rsync-args ARGS`: Additional arguments to pass to rsync command (as a single string)
- `--dry-run`: Show what would be synced without actually syncing

(all other options are the same as `mngr pull`)

See [multi-target](../generic/multi_target.md) options for behavior when some agents cannot be processed.

## TODOs

**Note: The push command is not yet implemented.** The following features need to be added:

- [ ] Basic push command from local to agent
- [ ] Push from one agent to another agent (two agent syntax)
- [ ] `--source` option with unified syntax parser
- [ ] `--source-agent`, `--source-host`, `--source-path` options
- [ ] `--target` option with unified syntax parser
- [ ] `--target-agent`, `--target-host`, `--target-path` options
- [ ] `--stdin` option for reading sources from stdin
- [ ] `--rsync-arg` option (repeatable)
- [ ] `--rsync-args` option (single string)
- [ ] `--dry-run` option
- [ ] Integration with multi-target options
- [ ] Reuse common options from pull command
