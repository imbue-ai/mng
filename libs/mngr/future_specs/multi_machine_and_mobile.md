# Multi-Machine and Mobile Support

## Problem

Today, `mngr` can only be used from the machine where the CLI is installed. If you want to check on agents, send messages, or create new agents from a different machine (laptop, phone, tablet), you have to SSH into your primary machine and run the CLI there.

This is especially limiting for mobile, where there is no practical way to run a Python CLI.

## Goal

Enable using `mngr` from any device -- including phones and tablets -- with minimal latency and a lightweight client.

## Analysis of What Exists

### Architecture is already favorable

The existing architecture is well-suited for multi-machine use:

1. **Stateless CLI**: `mngr` stores almost no persistent state locally. Everything is reconstructed from provider queries and host queries. This means there is no local database to synchronize.

2. **Provider-stored state**: All host state lives in the provider (Modal tags, Docker labels, filesystem metadata). Multiple `mngr` instances can already manage the same agents without conflicts.

3. **SSH as universal transport**: All remote communication already goes through SSH. The CLI is essentially a thin orchestration layer on top of SSH + provider APIs.

4. **Programmatic API layer**: `libs/mngr/imbue/mngr/api/` already separates the core operations (create, list, connect, message, push, pull, etc.) from the CLI presentation layer. This API layer can be wrapped by any interface, not just Click.

### Existing web components

Several web-facing components already exist:

- **sculptor_web**: FastHTML-based agent management UI (polls `mngr list --format json`, displays agent status, embeds iframes for agent UIs). Runs on port 8765.
- **claude_web_view**: FastAPI + React transcript viewer with SSE for live updates.
- **flexmux**: Flask-based layout manager with ttyd terminal integration.
- **Modal routes**: FastAPI endpoints deployed as Modal functions (e.g., `snapshot_and_shutdown`).

### `mngr open` (in review on `mngr/open-local`)

The `mngr open` command opens an agent's self-reported URL in a browser. Key details:

- Each agent reports a single URL via `get_reported_url()`, stored at `{agent_dir}/status/url`.
- `mngr open` calls `webbrowser.open()` -- local-only by design.
- `--wait` keeps the process running after opening; `--active` records user activity every 30s to prevent idle shutdown.
- `--type` flag is declared but raises `NotImplementedError` -- intended for when plugins register multiple URL types per agent (terminal, chat, diff, etc.).

For mobile, `mngr open` is not directly usable (no local browser to open), but the URL reporting system it relies on is exactly what a mobile UI would consume. The `--active` activity recording pattern also needs a server-side equivalent.

### Planned plugins that are relevant

Several [future] plugins directly address pieces of this problem:

- **offline_mngr_state**: Backs up agent/host state to S3 or local directory for offline access. Critical for mobile (unreliable connections, want to see status without SSH).
- **local_port_forwarding_via_frp_and_nginx**: Exposes agent services via subdomain URLs with authentication. Required for agent URLs to be reachable from outside the host's network.
- **default_url_for_cli_agents_via_ttyd**: Web-based terminal access to CLI agents.
- **user_activity_tracking_via_web**: Tracks user activity in web interfaces for idle detection.

## Approach: Host mngr on Modal as an HTTP API

The most practical approach is to run `mngr` itself as a persistent service on Modal, exposing an HTTP API that any client (mobile app, web app, other CLIs) can talk to.

### Why Modal

- mngr already has deep Modal integration (Modal provider, Modal routes, Modal volumes).
- Modal supports persistent web endpoints via `@modal.fastapi_endpoint()`.
- Modal volumes can store configuration and cached state.
- Modal has low cold-start times, so the API can be "serverless" without painful latency.
- No need to manage infrastructure -- Modal handles scaling, availability, etc.

### Architecture

```
Phone/Tablet/Laptop           Modal                        Agent Hosts
     |                          |                              |
     |   HTTP (REST/SSE)        |                              |
     |------------------------->|  mngr API server             |
     |                          |  (FastAPI on Modal)          |
     |                          |                              |
     |                          |------- SSH ----------------->|  Modal sandbox
     |                          |------- SSH ----------------->|  Docker host
     |                          |------- provider API -------->|  Local host
     |                          |                              |
     |   SSE (streaming)        |                              |
     |<-------------------------|  (agent events, status)      |
     |                          |                              |
     |                          |------- S3/Volume ----------->|  Offline state
```

### What the API server does

Wraps the existing `imbue.mngr.api` module as HTTP endpoints:

| Endpoint | Method | Maps to | Notes |
|----------|--------|---------|-------|
| `/agents` | GET | `api.list.list_agents()` | Filter via query params |
| `/agents` | POST | `api.create.create()` | Returns agent ID |
| `/agents/{id}/message` | POST | `api.message.message()` | Send message to agent |
| `/agents/{id}/stop` | POST | `api.stop` | Stop agent |
| `/agents/{id}/start` | POST | `api.start` | Start agent |
| `/agents/{id}/destroy` | DELETE | `api.gc` | Destroy agent |
| `/agents/{id}/events` | GET (SSE) | Stream events file | Live event stream |
| `/agents/{id}/logs` | GET (SSE) | Stream log file | Live log stream |
| `/agents/{id}/push` | POST | `api.push` | Push files to agent |
| `/agents/{id}/pull` | POST | `api.pull` | Pull files from agent |
| `/config` | GET/PUT | Config read/write | Manage configuration |

### Authentication

For a single-user personal tool (per the "personal" principle), the simplest viable approach:

1. **API token**: A long random token generated during setup, stored in a Modal secret.
2. **Bearer auth**: All requests include `Authorization: Bearer <token>`.
3. **Token on device**: Each device stores the token locally (in keychain on mobile, in `~/.mngr/` on desktop).

This avoids the complexity of OAuth/OIDC while still being secure (HTTPS + long random token). The token can be rotated via the CLI.

### Mobile client: web app

A responsive web app served by the Modal API server. This requires:

- Making the existing FastHTML UI responsive (CSS media queries, touch targets).
- Pointing it at the HTTP API instead of shelling out to `mngr list`.
- Adding authentication (token in a cookie or localStorage).

Advantages: No app store deployment, works on any device, reuses existing code.

PWA (service worker, offline caching) and native apps are potential future improvements but not needed for an MVP.

### What the mobile interface needs to support

Core operations in priority order:

1. **View agent list and status** -- the most common operation, must be fast.
2. **Send messages to agents** -- kick off tasks, answer questions.
3. **View agent logs/events** -- monitor progress.
4. **Start/stop agents** -- manage lifecycle.
5. **Create agents** -- less common from mobile, but useful.
6. **Push/pull files** -- least common from mobile.

### Key implementation decisions

#### SSH key management

The API server needs SSH access to hosts. Options:

1. **Store SSH key in Modal secret**: Simple, works today. The API server uses this key for all SSH operations.
2. **Generate per-session keys**: More secure but more complex. Each API session gets a temporary SSH key that is authorized on relevant hosts.

Option 1 is simpler and consistent with the single-user model.

#### Config and state storage

- **Config**: Stored in a Modal volume (or Modal secret for sensitive values).
- **Offline state**: S3 backend from `offline_mngr_state` plugin, readable by both the API server and mobile clients.
- **Cached agent list**: API server can cache the last-known agent list in a Modal volume for fast responses. Refreshed on each `list` call.

#### Latency

The main latency concern is `mngr list`, which SSH's into every running host to check agent status. Mitigations:

1. **Cached results**: Return cached results immediately, refresh in background.
2. **SSE streaming**: Stream agent info as it arrives (the API already supports streaming via callbacks).
3. **offline_mngr_state**: For stopped hosts, read from S3 instead of trying to SSH.

## Implementation Plan

The plan is organized into chunks that each deliver a usable increment. Earlier chunks are prerequisites for later ones. Each chunk is roughly one task's worth of work.

### Chunk 1: Multiple URL types on agents

**Why first**: The current `get_reported_url()` returns a single `str | None`. For mobile, agents will expose multiple URL types (e.g., a chat UI, a terminal via ttyd, a diff view). The `--type` flag on `mngr open` is a placeholder for this. This is the smallest foundational change and unblocks everything else.

**What to do**:

1. Change the agent URL storage from a single file (`status/url`) to a directory (`status/urls/`), where each file is named by type (e.g., `status/urls/default`, `status/urls/terminal`, `status/urls/chat`).
2. Add `get_reported_urls() -> dict[str, str]` to `AgentInterface` and `BaseAgent`. Returns `{"default": "https://...", "terminal": "https://..."}`, etc. Keep `get_reported_url()` as a convenience that returns the `default` entry (or the only entry if there is exactly one).
3. Add a `urls: dict[str, str]` field to `AgentInfo` (in `api/list.py`) alongside the existing `url` field. The `url` field continues to return the default URL for backwards compatibility.
4. Implement the `--type` flag on `mngr open` so it selects from the available URL types. When multiple types exist and no `--type` is given, show a simple selector (reuse the interactive selector pattern from `select_agent_interactively`).

**Files touched**: `interfaces/agent.py`, `agents/base_agent.py`, `api/list.py`, `cli/open.py` (on `mngr/open-local` branch), `api/open.py`.

**Depends on**: `mngr open` landing (the `mngr/open-local` branch).

### Chunk 2: Port forwarding plugin (FRP + nginx)

**Why next**: Agent URLs are currently only reachable from inside the host's network (or via SSH tunnel). For mobile access, agent services need to be reachable over the public internet. This is already designed in `docs/core_plugins/local_port_forwarding_via_frp_and_nginx.md`.

**What to do**:

1. Implement the `local_port_forwarding_via_frp_and_nginx` plugin as documented.
2. During host provisioning, install and start `frpc` (FRP client) on the host and `nginx` as a reverse proxy.
3. The plugin registers forwarded services as agent URL types (from Chunk 1). For example, when ttyd is forwarded, it becomes a `terminal` URL type.
4. Implement the `forward-service` command for agents to register services.
5. Implement the `mngr auth` command that sets a browser authentication cookie for `*.mngr.localhost` domains.

**Files touched**: New plugin in `plugins/`, provisioning scripts, new CLI commands.

**Depends on**: Chunk 1 (URL types).

### Chunk 3: ttyd plugin for web terminal access

**Why next**: Once port forwarding works, we can expose ttyd as a web terminal, giving browser-based (and thus mobile-accessible) terminal access to CLI agents. Already designed in `docs/core_plugins/default_url_for_cli_agents_via_ttyd.md`.

**What to do**:

1. Implement the `default_url_for_cli_agents_via_ttyd` plugin as documented.
2. During agent creation (for CLI-based agents like Claude Code, Codex), start a ttyd process connected to the agent's tmux session.
3. Forward the ttyd port via the FRP plugin (Chunk 2), registering it as a `terminal` URL type (Chunk 1).
4. Generate a per-agent security token embedded in the URL.

**Files touched**: New plugin in `plugins/`, agent provisioning hooks.

**Depends on**: Chunk 2 (port forwarding).

**Milestone**: After chunks 1-3, `mngr open my-agent terminal` works from any browser on any machine, including mobile Safari/Chrome. This is usable multi-machine support without any API server -- you just need the URL.

### Chunk 4: HTTP API server on Modal

**Why next**: Viewing agent URLs in a browser is useful, but you still need the CLI to list agents, send messages, start/stop, etc. An HTTP API makes these operations accessible from any device.

**What to do**:

1. Create a new package: `libs/mngr_api_server/` (or a Modal route in `providers/modal/routes/`).
2. Build a FastAPI app that wraps the `imbue.mngr.api` module:
   - `GET /api/agents` -- calls `list_agents()`, returns `list[AgentInfo]` as JSON. Supports query params for CEL filters.
   - `POST /api/agents/{id}/message` -- calls `send_message_to_agents()`.
   - `POST /api/agents/{id}/start` -- starts a stopped agent.
   - `POST /api/agents/{id}/stop` -- stops an agent.
   - `DELETE /api/agents/{id}` -- destroys an agent.
   - `POST /api/agents` -- calls `create()`. Accepts agent type, name, provider, etc.
3. Implement bearer token authentication as middleware. Token stored in Modal Secret, validated on every request.
4. Bootstrap: `mngr deploy-api` CLI command that:
   - Generates an API token (or uses an existing one).
   - Stores the token + SSH key + config in Modal Secrets/Volumes.
   - Runs `modal deploy` to deploy the FastAPI app.
   - Prints the API URL and token.
5. The API server constructs a `MngrContext` on startup from the config/secrets stored in the Modal volume. This is the same context the CLI uses.

**Key design decision**: The API server runs `mngr` operations directly (in-process), not by shelling out to the CLI. It imports and calls `imbue.mngr.api.*` functions. This avoids subprocess overhead and gives proper error handling.

**Files touched**: New package or route module, new CLI command (`deploy-api`), Modal deployment config.

**Depends on**: Nothing strictly (can be done in parallel with chunks 2-3), but is most useful after chunks 1-3 so that the URLs returned by the API are actually reachable.

### Chunk 5: Minimal web UI (MVP)

**Why next**: The API server from Chunk 4 returns JSON. A minimal web UI makes it usable from a phone without curl.

**Design principle**: The MVP should feel like tmux -- a list of agents (like tmux sessions) where you tap one to get its terminal/UI in full screen. No fancy dashboards, no complex layouts. Just: pick an agent, see it.

**What to do**:

1. Single-page HTML app served by the API server (inline JS/CSS, no build step). Can use HTMX for simplicity (same pattern as sculptor_web).
2. **Agent list view** (the default view):
   - Full-width list of agents. Each row shows: name, type, state (color-coded), host name. Tap to open.
   - Pull-to-refresh or auto-refresh every few seconds.
   - A simple text filter at the top (like sculptor_web's search).
3. **Agent view** (after tapping an agent):
   - If the agent has a URL (from Chunk 1): embed it in a full-screen iframe. This is the main interaction mode -- you're looking at the agent's own UI (ttyd terminal, web app, etc.).
   - Below/above the iframe: a thin toolbar with agent name, back button, and a "message" button that opens a text input for sending messages via the API.
   - If no URL: show agent status markdown, logs tail, and the message input.
4. **Auth**: On first visit, prompt for API token. Store in localStorage. Send as Bearer token on all API requests.
5. **Mobile-first CSS**: viewport meta tag, full-width layout, minimum 44px touch targets. No sidebar -- everything is stacked/fullscreen.

This is intentionally minimal. The goal is to get something usable on a phone in the smallest amount of code. sculptor_web can be adapted later for a richer desktop experience.

**Depends on**: Chunk 4 (API server).

### Chunk 6: Activity tracking for web/mobile sessions

**Why next**: When a user is viewing an agent's URL in a mobile browser, the host doesn't know the user is active and may auto-stop. The `--active` flag on `mngr open` solves this for the CLI; we need an equivalent for web.

**What to do**:

1. Implement the `user_activity_tracking_via_web` plugin as documented. Inject a small JavaScript snippet (via nginx `sub_filter`) into proxied agent pages that sends heartbeat requests on keyboard/mouse/touch activity.
2. Add a heartbeat endpoint to the API server: `POST /api/agents/{id}/activity`. This calls `agent.record_activity(ActivitySource.USER)`.
3. The web UI (Chunk 5) sends periodic heartbeats while the user has an agent selected.

**Depends on**: Chunk 2 (nginx), Chunk 4 (API server).

### Chunk 7: SSE streaming for live updates

**Why next**: Polling every 2 seconds is wasteful on mobile (battery, data). SSE gives live updates with a single long-lived connection.

**What to do**:

1. Add `GET /api/agents/stream` SSE endpoint to the API server. On connect, sends the current agent list, then pushes diffs when agents change state (new agent, state change, URL reported, etc.).
2. The API server runs `list_agents()` periodically (or watches for changes) and pushes updates.
3. Update the web UI to use SSE instead of polling (fall back to polling if SSE disconnects).
4. Add `GET /api/agents/{id}/logs/stream` SSE endpoint that tails the agent's log file over SSH and streams new lines.

**Depends on**: Chunk 4 (API server), Chunk 5 (web UI).

### Chunk 8: `mngr` as a provider backend

**Why**: With the API server running, other `mngr` instances (on other machines) could use it as a "provider" -- querying it for hosts and agents instead of talking to Modal/Docker/local directly. This is hinted at in the existing providers doc (`backend = "mngr"`, `url = "https://mngr.internal.company.com"`).

**What to do**:

1. Implement a `mngr` provider backend that talks to a remote `mngr` API server (Chunk 4) over HTTP.
2. This allows `mngr list` on machine A to show agents managed by the API server on Modal, without machine A needing Modal credentials or SSH keys.
3. Config: `[[providers]]\nname = "remote"\nbackend = "mngr"\nurl = "https://<modal-url>"\ntoken = "..."`.

**Depends on**: Chunk 4 (API server).

**MVP Milestone**: After chunks 1-7, you have a working mobile experience. Open a URL on your phone, see your agents, tap one to get its terminal, send messages. Chunks 4+5 alone (API server + minimal web UI) are the fastest path to "something usable on a phone" if chunks 1-3 (URL infrastructure) are already in place.

### Optional / Future Chunks

These are lower priority and can be done in any order after the core chunks:

- **Offline state plugin** (`offline_mngr_state`): S3-backed cache of agent state for when hosts are stopped. The API server reads from S3 for offline hosts, merging with live data. Useful but not required for MVP -- stopped agents simply won't show status until their host is started.
- **Richer web UI**: Adapt sculptor_web for a fuller desktop experience (sidebar layout, multiple iframes, richer status display). The MVP tmux-like UI is phone-first; this would be desktop-optimized.
- **PWA support**: Service worker + manifest for "Add to Home Screen" and offline caching.
- **Push notifications**: Web Push API to notify when agents finish tasks or need input.
- **File browser**: Web UI for browsing agent work directories and pushing/pulling files.
- **`mngr open` over API**: `POST /api/agents/{id}/open` returns URL(s) instead of opening a browser.

## Dependency Graph

```
Chunk 1 (URL types)
  |
  v
Chunk 2 (FRP/nginx port forwarding)
  |
  v
Chunk 3 (ttyd web terminal)          Chunk 4 (HTTP API server)
  |                                     |       |
  |                                     v       v
  |                                 Chunk 5  Chunk 8
  |                                 (Web UI) (Provider)
  |                                     |
  |                                     v
  +-------------------------------> Chunk 6 (Activity tracking)
                                        |
                                        v
                                    Chunk 7 (SSE streaming)
```

Chunks 1, 2, 3 are a serial chain (each depends on the previous).
Chunk 4 can proceed in parallel with chunks 2 and 3.
Chunks 5, 6, 7, 8 depend on Chunk 4 but are mostly independent of each other.

**Fastest path to MVP**: Chunks 1 -> 2 -> 3 (URL infrastructure), then Chunk 4 + 5 (API + minimal UI). Chunks 6-8 improve the experience but aren't required for basic phone access.

## Concerns

### Security

Exposing an HTTP API increases attack surface compared to SSH-only access. Mitigations:

- HTTPS only (Modal provides this).
- Long random API token (256 bits).
- Rate limiting on the Modal endpoint.
- No credential storage in the API response payloads.
- SSH keys never leave the Modal environment.

### Latency

Modal cold starts could add 1-3 seconds to the first request. Mitigations:

- Use Modal's `keep_warm` to keep at least one instance running (costs ~$0.50/day for a small instance).
- Cache agent list for instant initial render.

### Complexity

Adding an HTTP API layer means maintaining two interfaces (CLI and HTTP). Mitigations:

- Both use the same `imbue.mngr.api` module -- no logic duplication.
- The HTTP layer is thin (routing + auth + serialization).
- The CLI remains the primary interface; HTTP is an alternative access method.

### Consistency with principles

- **Direct**: The HTTP API maps 1:1 to CLI commands. No additional abstraction.
- **Immediate**: Cached results + SSE streaming keep the mobile experience responsive.
- **Safe**: Same safety guarantees as CLI (all operations go through the same API layer).
- **Personal**: Single-user token auth. No multi-tenant concerns.
