# Default URL for CLI Agents via ttyd

This plugin provides web-based terminal access to CLI agents using [ttyd](https://github.com/tsl0922/ttyd).

## Overview

Many agents (Claude Code, Codex CLI, etc.) are terminal-based. This plugin automatically creates a web URL for any agent that doesn't already have one, allowing you to interact with the agent through your browser via `mngr open`.

The URL connects to the agent's tmux session through a secure web terminal.

## Usage

Once an agent is created, open its web terminal in your browser:

```bash
mngr open my-agent terminal
```

This opens the agent's web terminal URL. If `terminal` is the only URL type available for the agent, you can omit it:

```bash
mngr open my-agent
```

The URL includes a security token, so only you can access it.

## Security

ttyd is secured with a per-agent token embedded in the URL. This prevents other websites from accessing your terminal—only requests with the correct token are allowed.

The token is generated when the agent is created and is included in the URL opened by `mngr open`.

## Requirements

This plugin requires:

- **ttyd** - Install via your package manager or download from [GitHub](https://github.com/tsl0922/ttyd/releases)
- **tmux** - For managing agent sessions (installed by default on most providers)
- **A forwarding plugin** - Such as [Local Port Forwarding via FRP and Nginx](./local_port_forwarding_via_frp_and_nginx.md)

### Missing Forwarding Plugin

If no forwarding plugin is available, remote agent creation fails with an error explaining which plugins to install or how to disable web terminal access (local agents work fine without forwarding plugins).
