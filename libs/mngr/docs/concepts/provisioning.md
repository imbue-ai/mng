# Provisioning

Provisioning sets up a [host](./hosts.md) before an [agent](./agents.md) starts: installing packages, creating config files, starting services.

```bash
mngr create my-agent claude     # Provisioning runs automatically
mngr provision --agent my-agent # Re-run provisioning manually
```

## Step Sources

Provisioning steps come from three sources, executed in order:

1. **Plugin defaults**: The [agent type's](./agent_types.md) plugin defines required setup (e.g., installing Node.js for Claude)
2. **User commands**: Flags like `--user-command`, `--upload-file`, etc. for the `mngr create` and `mngr provision` commands
3. **Devcontainer hooks**: If using a devcontainer, its lifecycle hooks (`onCreateCommand`, etc.) run as part of provisioning

## Custom Steps

Add your own provisioning steps when creating an agent:

```bash
mngr create my-agent claude --user-command "pip install pandas"
mngr create my-agent claude --upload-file ./config.json:/app/config.json
mngr create my-agent claude --sudo-command "apt-get install -y ffmpeg"
```

These run after plugin defaults but before the agent starts.

See [`mngr provision`](../commands/secondary/provision.md) for all options.

## Re-running Provisioning

You can re-run provisioning on an existing agent with `mngr provision`. This is useful for syncing configuration changes or installing additional packages.

Provisioning is designed to be idempotent--the underlying tool ([pyinfra](https://pyinfra.com/)) and built-in plugins can safely run multiple times without breaking anything.

## Implementation Details

For implementation details about package version checking, cross-platform installation, and plugin ordering during provisioning, see the [provisioning spec](../../specs/provisioning.md).
