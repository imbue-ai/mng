# OpenCode Agent

The OpenCode agent type integrates [OpenCode](https://github.com/sst/opencode), an open-source AI coding assistant, with mngr.

## Installation

The OpenCode agent requires the `mngr-opencode` plugin package:

```bash
uv pip install mngr-opencode
```

Once installed, the plugin is automatically discovered via entry points and the `opencode` agent type becomes available.

## Usage

Create an OpenCode agent:

```bash
mngr create my-agent opencode
```

Or specify the agent type explicitly:

```bash
mngr create my-agent --agent-type opencode
```

## Configuration

The OpenCode agent supports the following configuration options:

```toml
[agent_types.opencode]
command = "opencode"           # Command to run the OpenCode agent
cli_args = ""                  # Additional CLI arguments to pass
permissions = []               # Permissions granted to the agent
parent_type = null             # Parent agent type to inherit from
```

### Custom Configuration

You can create a custom OpenCode agent type with pre-configured settings:

```toml
[agent_types.my_opencode]
parent_type = "opencode"
cli_args = "--verbose"
permissions = ["github"]
```

## Implementation

The OpenCode agent is implemented as a plugin in the `mngr-opencode` package at `imbue/mngr_opencode/plugin.py`. It provides:

- `OpenCodeAgentConfig`: Configuration class with command field
- `register_agent_type()`: Hook that registers the agent type with mngr

The agent uses the default `BaseAgent` implementation, meaning it inherits standard agent functionality without custom behavior.

## TODOs

The following features are not yet implemented:

- **Installation checking**: No automatic detection or installation of the opencode CLI (unlike the claude agent which checks and can auto-install)
- **Settings synchronization**: No syncing of OpenCode configuration files to remote hosts (unlike claude agent's sync_home_settings, sync_claude_json, etc.)
- **Session resumption**: No built-in session ID or resumption support (unlike claude agent's UUID-based session management)
- **Custom provisioning**: No custom provisioning logic or file transfers for OpenCode-specific configuration
- **Credential handling**: No automatic credential transfer to remote hosts
