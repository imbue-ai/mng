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

### Planned plugins that are relevant

Several [future] plugins directly address pieces of this problem:

- **offline_mngr_state**: Backs up agent/host state to S3 or local directory for offline access. Critical for mobile (unreliable connections, want to see status without SSH).
- **local_port_forwarding_via_frp_and_nginx**: Exposes agent services via subdomain URLs with authentication.
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

### Mobile client options

From simplest to most polished:

#### Option A: Mobile web app (recommended starting point)

Adapt `sculptor_web` to be a responsive web app served by the Modal API server. This requires:

- Making the existing FastHTML UI responsive (CSS media queries, touch targets).
- Pointing it at the HTTP API instead of shelling out to `mngr list`.
- Adding authentication (token in a cookie or localStorage).

Advantages: No app store deployment, works on any device, reuses existing code.

#### Option B: PWA (Progressive Web App)

Same as Option A, but with a service worker for offline support and "Add to Home Screen" capability. The `offline_mngr_state` S3 backend could feed a cached agent list for offline viewing.

#### Option C: Native mobile app

A React Native or Flutter app that talks to the HTTP API. More work, but enables push notifications, better offline support, and native UX.

For a personal tool, Option A is likely sufficient.

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

## Required work

### Phase 1: HTTP API on Modal

1. Create a FastAPI app that wraps `imbue.mngr.api` operations.
2. Deploy as a Modal web endpoint.
3. Implement token-based authentication.
4. Store config and SSH keys in Modal secrets/volumes.
5. Test from a second machine via `curl`.

### Phase 2: Mobile-friendly web UI

1. Fork/adapt `sculptor_web` to use the HTTP API instead of CLI subprocess calls.
2. Make the UI responsive for mobile screens.
3. Add authentication flow (enter token, store in cookie).
4. Deploy as static files served by the API server.

### Phase 3: Live updates and offline support

1. Implement SSE endpoints for agent events and logs.
2. Implement `offline_mngr_state` plugin (S3 backend).
3. Add service worker for PWA offline support.
4. Cache agent list for instant load on mobile.

### Phase 4: Enhanced mobile experience

1. Push notifications (via web push or native app) for agent state changes.
2. File browser for push/pull operations.
3. Web terminal via ttyd for direct agent interaction from mobile.

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
