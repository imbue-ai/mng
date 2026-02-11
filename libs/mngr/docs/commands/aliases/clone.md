# mngr clone - CLI Options Reference

Create a new agent by cloning an existing one.

A convenience wrapper around `mngr create --from-agent <agent>`. The first
argument is the source agent to clone from. All remaining arguments are
passed through to the create command.

## Usage

```
mngr clone <SOURCE_AGENT> [<AGENT_NAME>] [create-options...]
```

## Examples

```bash
# Clone an agent with auto-generated name
mngr clone my-agent

# Clone with a specific name
mngr clone my-agent new-agent

# Clone into a Docker container
mngr clone my-agent --in docker

# Clone and pass args to the agent
mngr clone my-agent -- --model opus
```

## See Also

- `mngr create --help` - Full create option set
- `mngr list --help` - List existing agents
