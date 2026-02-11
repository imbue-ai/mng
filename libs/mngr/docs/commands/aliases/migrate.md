# mngr migrate - CLI Options Reference

Move an agent to a different host by cloning it and destroying the original.

Equivalent to running `mngr clone <source>` followed by `mngr destroy --force <source>`.
The first argument is the source agent to migrate. All remaining arguments are
passed through to the create command.

The source agent is always force-destroyed after a successful clone, including
running agents. If the clone step fails, the source agent is left untouched.

## Usage

```
mngr migrate <SOURCE_AGENT> [<AGENT_NAME>] [create-options...]
```

## Examples

```bash
# Migrate an agent to a Docker container
mngr migrate my-agent --in docker

# Migrate with a new name
mngr migrate my-agent new-agent --in modal

# Migrate and pass args to the agent
mngr migrate my-agent -- --model opus
```

## See Also

- `mngr clone --help` - Clone an agent (without destroying the original)
- `mngr create --help` - Full create option set
- `mngr destroy --help` - Destroy an agent
