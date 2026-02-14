# Mobile and Multi-Machine Setup

`mngr` can be accessed from any device -- phone, tablet, or second laptop -- via a built-in HTTP API server and mobile-first web UI. This guide walks through setup.

## Quick Start

Start the API server on your primary machine (where `mngr` is installed):

```bash
uv run mngr serve
```

This starts the server on `0.0.0.0:8000` and prints the first 8 characters of your API token. To see the full token:

```bash
uv run mngr token
```

The token is auto-generated on first use and stored at `~/.config/mngr/api_token` (file permissions `0600`). Reuse `mngr token` any time you need it.

Open `http://<your-machine-ip>:8000` in your phone's browser, enter the token, and you are in.

## What You Get

The web UI is a mobile-first single-page app with:

- Agent list with name, type, host, and state (color-coded)
- Text filter for searching agents
- Full-screen agent views with embedded iframes (for agents that report URLs)
- Message input bar for sending messages to agents
- Stop button for running agents
- Auto-refresh every 5 seconds
- Dark theme, 44px minimum touch targets

When an agent has a web terminal URL (via the [ttyd plugin](../core_plugins/default_url_for_cli_agents_via_ttyd.md)), tapping it opens the terminal full-screen in an iframe -- you can interact with CLI agents directly from your phone.

## Configuring the API Server

The API server plugin accepts three settings:

- `port` -- port to bind to (default: `8000`)
- `host` -- address to bind to (default: `0.0.0.0`)
- `api_token` -- bearer token (auto-generated if not set)

You can set these in your config file under `[plugins.api_server]`:

```toml
# ~/.mngr/profiles/<profile_id>/settings.toml
[plugins.api_server]
port = 9000
host = "127.0.0.1"
```

Or via `mngr config set`:

```bash
uv run mngr config set plugins.api_server.port 9000 --scope user
```

You can also pass `--port` and `--host` directly to `mngr serve`:

```bash
uv run mngr serve --port 9000 --host 127.0.0.1
```

See [config](../commands/secondary/config.md) for more on configuration scopes and commands.

## Making It Reachable from Outside Your Network

If you run `mngr serve` on your local machine, it is only reachable from your local network. To access it from a phone on a different network, you need to expose it.

The recommended approach is to deploy the API server to Modal, which gives you an always-on HTTPS endpoint accessible from anywhere. See [Deploying to Modal](#deploying-to-modal) below.

Alternatively, the [port forwarding plugin](../core_plugins/local_port_forwarding_via_frp_and_nginx.md) uses FRP and nginx to expose services via subdomain URLs:

```
<service>.<agent>.<host>.mngr.localhost:8080
```

This is primarily used for exposing individual agent services (like ttyd terminals) rather than the API server itself. See the plugin docs for setup details.

## Web Terminal Access (ttyd)

The [ttyd plugin](../core_plugins/default_url_for_cli_agents_via_ttyd.md) provides browser-based terminal access to CLI agents (like Claude Code). When enabled:

- Each CLI agent gets a `terminal` URL type backed by a ttyd process attached to the agent's tmux session
- URLs contain per-agent security tokens -- only someone with the URL can access the terminal
- The web UI embeds these terminals as full-screen iframes

You can also open a terminal directly from the CLI:

```bash
uv run mngr open my-agent terminal
```

Or just open the default URL:

```bash
uv run mngr open my-agent
```

See [open](../commands/primary/open.md) for the full set of options, including `--wait` and `--active` for keeping the agent alive while you interact.

## Multi-Machine Setup (Remote Provider)

If you want `mngr` on a second machine to see agents managed by the first, configure the `mngr` remote provider on the second machine.

Edit your settings file (`mngr config edit --scope user`) and add:

```toml
[[providers]]
name = "remote"
backend = "mngr"
url = "https://your-api-server-url"
token = "your-api-token"
```

**Note:** Provider definitions use `[[providers]]` TOML array syntax, which cannot be set via `mngr config set`. Use `mngr config edit` instead.

After this, `mngr list` on the second machine includes agents from the remote server. You can also send messages and stop agents:

```bash
uv run mngr list               # shows local + remote agents
uv run mngr message my-agent "check the tests"
```

The remote provider is read-only for host-level operations (create, destroy, start/stop hosts). Those must go through the primary `mngr` instance or the web UI.

See [providers](../concepts/providers.md) for more on provider configuration.

## Deploying to Modal

Deploying the API server to Modal is the recommended way to get always-on mobile access. Modal provides HTTPS automatically, has low cold-start times, and `mngr` already has deep Modal integration (provider, volumes, secrets).

The architecture looks like this:

```
Phone/Tablet/Laptop          Modal                    Agent Hosts
     |                         |                           |
     |---HTTPS (REST)--------->|  mngr API server          |
     |                         |  (FastAPI)                |
     |<---JSON responses-------|                           |
     |                         |---SSH-------------------->|  Remote hosts
     |<---iframe URLs----------|                           |
```

### What Modal provides

- **HTTPS**: Automatic TLS termination -- no certificate management
- **Persistent endpoints**: Via `@modal.fastapi_endpoint()`
- **Volumes**: For storing mngr config persistently
- **Secrets**: For storing SSH keys and API tokens securely
- **Low latency**: Cold starts of 1-3 seconds; use `keep_warm` (~$0.50/day) to eliminate them

### Setup

**Note:** A dedicated `mngr deploy-api` command is planned but not yet available. For now, deployment requires manual Modal configuration.

The steps are:

1. Store your SSH key as a Modal secret so the API server can reach your hosts
2. Store your mngr config in a Modal volume
3. Deploy a FastAPI app that imports and calls `imbue.mngr.api` functions directly (no subprocess overhead)
4. Use the resulting Modal URL as your API endpoint

The API server constructs the same `MngrContext` the CLI uses, so all operations behave identically to running the CLI locally.

See [Modal provider](../core_plugins/providers/modal.md) for general Modal usage with mngr.

## Commands Reference

| Command | Purpose |
|---------|---------|
| `mngr serve` | Start the API server and web UI |
| `mngr serve --port 9000` | Start on a custom port |
| `mngr token` | Print the current API token |
| `mngr open <agent>` | Open an agent's default URL |
| `mngr open <agent> terminal` | Open an agent's web terminal |
| `mngr open <agent> --wait --active` | Open and keep the agent alive while connected |
| `mngr config edit --scope user` | Edit user config (for adding providers) |

## Security

The security model is designed for single-user personal use:

- **API token**: 256-bit random token generated via `secrets.token_urlsafe(32)`. Stored at `~/.config/mngr/api_token` with `0600` permissions.
- **HTTPS**: Provided automatically when deployed to Modal. For local-only use, add your own TLS termination or rely on network-level security.
- **ttyd tokens**: Each agent's web terminal URL contains a per-agent security token. Only someone with the URL can access the terminal.
- **SSH key isolation**: When deployed to Modal, SSH keys are stored in Modal secrets and never leave the Modal environment.
- **No credentials in responses**: API responses never include tokens, keys, or other sensitive data.

## See Also

- [Customization](../customization.md) -- configuration files, command defaults, and templates
- [Config commands](../commands/secondary/config.md) -- managing configuration via the CLI
- [Modal provider](../core_plugins/providers/modal.md) -- creating agents on Modal
- [Port forwarding plugin](../core_plugins/local_port_forwarding_via_frp_and_nginx.md) -- exposing services via FRP/nginx
- [ttyd plugin](../core_plugins/default_url_for_cli_agents_via_ttyd.md) -- web terminal access for CLI agents
- [Providers](../concepts/providers.md) -- configuring provider instances
- [open command](../commands/primary/open.md) -- opening agent URLs
