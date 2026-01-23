# mngr message - CLI Options Reference

Send a message to one or more agents

**Alias:** `msg`

## Usage

```
mngr message [[--agent] AGENT ...] [options]
```

Agent IDs can be specified as positional arguments for convenience. The following are equivalent:

```
mngr message my-agent --message "Hello"
mngr message --agent my-agent --message "Hello"
mngr message my-agent another-agent --message "Hello"
mngr message --agent my-agent --agent another-agent --message "Hello"
```

## General

- `--agent AGENT`: Agent(s) to send the message to. Positional arguments are also accepted as a shorthand. [repeatable]
- `-a, --all, --all-agents`: Send message to all agents
- `--include FILTER`: Filter agents to send message to by tags, names, types, hosts, etc.
- `--exclude FILTER`: Exclude agents matching filter from receiving the message
- `--stdin`: Read agents and hosts (ids or names) from stdin (one per line)
- `--message MESSAGE`: The message content to send

If no message is specified, reads from stdin (if headless) or opens an editor (if interactive).

See [multi-target](../generic/multi_target.md) options for behavior when some agents fail.

## TODOs

All features described in this document are implemented. Notes:

- `-m` short form for `--message` is implemented but not documented above
- Multi-target error handling options are available via `--on-error` (choices: `abort`, `continue`). See [multi-target.md](../generic/multi_target.md#todos) for limitations on additional error behaviors.
