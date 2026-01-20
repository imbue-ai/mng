# mngr limit - CLI Options Reference

Configure limits for agents and hosts: idle timeout, permissions, port forwarding, etc.

Agents effectively have permissions that are equivalent to the *union* of all permissions on the same host.

Changing permissions for agents requires them to be restarted.

Changes to some limits for hosts (e.g. CPU, RAM, disk space, network, etc.) are handled by the provider.

**Alias:** `lim`

## Usage

```
mngr limit [[--agent] AGENT ...] [options]
```

Agent IDs can be specified as positional arguments for convenience. The following are equivalent:

```
mngr limit my-agent --idle-timeout 30m
mngr limit --agent my-agent --idle-timeout 30m
mngr limit my-agent another-agent --idle-timeout 30m
mngr limit --agent my-agent --agent another-agent --idle-timeout 30m
```

## General

- `--agent AGENT`: Agent(s) to configure. Positional arguments are also accepted as a shorthand. [repeatable]
- `--host HOST`: Host(s) to configure. [repeatable]
- `-a, --all, --all-agents`: Apply limits to all agents
- `--include FILTER`: Filter agents to configure by tags, names, types, hosts, etc.
- `--exclude FILTER`: Exclude agents matching filter from configuration
- `--stdin`: Read agents and hosts (ids or names) from stdin (one per line)
- `--dry-run`: Show what limits would be changed without actually changing them

## Lifecycle

- `--[no-]start-on-boot`: Automatically restart agent when host restarts. When adding the persist bit to a local agent, you may be prompted to install the post-boot-handler [default: no-persist for local, persist otherwise]
- `--idle-timeout DURATION`: Shutdown after idle for specified duration (e.g., `30s`, `5m`, `1h`)
- `--idle-mode MODE`: When to consider host idle [default: `io` (remote) or `disabled` (local), choices: `io`, `user`, `agent`, `ssh`, `create`, `boot`, `start`, `run`, `disabled`]
- `--activity-sources SOURCES`: Set activity sources for idle detection (comma-separated). Available sources: `create`, `boot`, `start`, `ssh`, `process`, `agent`, `user` [default: everything except process]
- `--add-activity-source SOURCE`: Add an activity source for idle detection [repeatable]
- `--remove-activity-source SOURCE`: Remove an activity source from idle detection [repeatable]

**Idle modes:**
- `io` - Time since there was any activity (user, agent, ssh, etc.)
- `user` - Time since the last user input or SSH activity
- `agent` - Time since the last agent output or SSH activity
- `ssh` - Time since an SSH connection was last active
- `create` - Time since the agent was created
- `boot` - Time since the host was booted
- `start` - Time since the agent was started
- `run` - Time since the agent process exited
- `disabled` - Never automatically idle (manual shutdown only)

## Permissions

- `--grant PERMISSION`: Grant a permission to the agent [repeatable]
- `--revoke PERMISSION`: Revoke a permission from the agent [repeatable]

## SSH Keys

- `--refresh-ssh-keys`: Refresh the SSH keys for the host
- `--add-ssh-key FILE`: Add an SSH public key to the host for access [repeatable]
- `--remove-ssh-key FILE`: Remove an SSH public key from the host [repeatable]
