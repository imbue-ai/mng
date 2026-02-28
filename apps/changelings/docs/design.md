# Overview

Each changeling is a specific sub-type of `mng` agent. While `mng` agents can be any process running in a tmux session, changelings additionally *must* serve a web interface and be conversational (able to receive messages and generate responses).

# Terminology

- **changeling**: a persistent `mng` agent with a web interface and conversational capabilities, identified by its `AgentId`
- **zygote**: the minimal core of a changeling's code, typically cloned from a git repo. This is the starting point before configuration and deployment.
- **template**: an HTML/web template for serving a particular interface (e.g. a chat UI, a dashboard, etc.)
- **forwarding server**: a local gateway that authenticates users and proxies traffic to changeling web servers

# Relationship to mng

Changelings are built on top of `mng` and should interact with it exclusively through the `mng` CLI interface. Changelings should never directly access mng's internal data directories (e.g., `~/.mng/agents/`). Instead, use `mng` commands like `mng list`, `mng logs`, `mng exec`, etc. This ensures changelings remain compatible as mng's internals evolve and work correctly across all provider backends (local, modal, docker).

# Design principles

1. **Simplicity**: The system should be as simple as possible, both in terms of user experience and internal architecture. Each changeling is simply a web server with some persistent storage (ideally just a file system) that, by convention, ends up calling an AI agent to respond to messages from the user. The only required routes are for the index and for handling incoming messages.
2. **Personal**: Changelings are designed to serve an *individual* user. They may respond to requests from other humans (or agents), but only to the extent that they are configured to do so by their primary human user.
3. **Open**: Changelings are both transparent (the user should always be able to see exactly what is going on and dive into any detail they want) and extensible (the user should be able to easily add new capabilities, and to modify or remove existing ones).
4. **Trustworthy**: Changelings should take security and safety seriously. They should have minimal access to data that they do not need, and for the minimal amount of time that they need it.

# Architecture for changeling agents

Each changeling has its own code repo (its zygote), cloned from a git remote and stored at `~/.changelings/<agent-name>/`. The agent should make commits there if it's ever changing anything. You can optionally link the code to a git remote in case you want the agent to push changes and make debugging easier.

Changelings use space in the host volume (via the agent dir) for persistent data. The structure and format of this data is up to each individual changeling. You can optionally configure them to store their memories in git (but that is less secure, as data would leak out if synced).

Changelings *must* serve web requests on one or more ports. On startup, they write JSON records to `$MNG_AGENT_STATE_DIR/logs/servers.jsonl` -- one line per server -- containing the server name and URL, e.g. `{"server": "web", "url": "http://127.0.0.1:9100"}`. An agent may write multiple records for different servers (e.g. a "web" UI server and an "api" backend server). Later entries for the same server name override earlier ones. The forwarding server reads this via `mng logs <agent-id> servers.jsonl` to discover all backends.

# Architecture for the local forwarding server

The local forwarding server is a FastAPI app that handles authentication and traffic forwarding. It is the gateway through which users access all their changelings.

This is a separate component from any individual changeling's web server -- it does not define what changelings do or how they respond to messages. It only handles routing and authentication.

## Authentication

The forwarding server uses `itsdangerous` for cookie signing. Auth works as follows:

- **Signing key**: generated once on first server start, stored at `{data_directory}/signing_key`. Used to sign all auth cookies.
- **One-time codes**: generated during `changeling deploy` and stored in `{data_directory}/one_time_codes.json`. Each code is associated with an agent ID and can only be used once. When a code is consumed, it is marked as "USED" in the JSON file.
- **Cookies**: after successful authentication, the server sets a signed cookie for the specific changeling. The cookie value contains the agent ID, signed with the signing key.

## Local forwarding server routes

`/login` route (takes agent_id and one_time_code params):
    if you have a valid cookie for this changeling, it redirects you to the main page ("/")
    if you don't have a cookie, it uses JS to redirect you and your secret to "/authenticate?agent_id={agent_id}&one_time_code={one_time_code}"
        this is done to prevent preloading servers from accidentally consuming your one-time use codes

`/authenticate` route (takes agent_id and one_time_code params):
    validates the one-time code against stored codes
    if this is a valid code (not used and not revoked), marks it as used and replies with a signed cookie
    if this is not a valid code, explains to the user that they need to generate a new login URL for this device (each URL can only be used once)

`/` route is special:
    looks at the cookies you have -- for each valid changeling cookie, that changeling is listed
    if you have 0 valid cookies, it shows a placeholder telling you to log in
    if you have 1 or more valid cookies, those changelings are shown as links to their individual pages

`/agents/{agent_id}/` route lists all servers for a changeling:
    requires a valid auth cookie for that changeling
    shows a page listing all known server names for the agent (discovered via `mng logs`)
    each server name links to `/agents/{agent_id}/{server_name}/`

`/agents/{agent_id}/{server_name}/{path}` route serves individual server UIs:
    requires a valid auth cookie for that changeling (auth is per-agent, not per-server)
    proxies any request from the user to the specific server's backend URL
    uses Service Workers for transparent path rewriting so the server's app works correctly under the `/agents/{agent_id}/{server_name}/` prefix

All pages except "/", "/login" and "/authenticate" require the auth cookie to be set for the relevant changeling.

## Proxying design

Since we can't control DNS or use subdomains, we multiplex changelings under URL path prefixes (`/agents/{agent_id}/{server_name}/`). Each server for an agent gets its own prefix and Service Worker scope. This requires a combination of Service Workers, script injection, and rewriting:

- On first navigation, a bootstrap page installs a Service Worker scoped to `/agents/{agent_id}/{server_name}/`
- The SW intercepts all same-origin requests and rewrites paths to include the prefix
- HTML responses have a WebSocket shim injected to rewrite WS URLs
- Cookie paths in Set-Cookie headers are rewritten to scope under the server prefix
- WebSocket connections are proxied bidirectionally

# Command line interface

- `changeling deploy <git-url>` (clones a git repo and deploys a changeling from it)
- `changeling forward` (starts the local forwarding server for accessing changelings)

[future] Additional commands for managing deployed changelings (list, stop, start, destroy, logs, etc.)

# Deferred items

The following are planned but not in the initial implementation:

- [future] Remote forwarding server deployment (e.g. to Modal) for access from anywhere
- [future] Mobile notifications from changelings
- [future] Desktop client / system tray icon
- [future] Multi-agent interaction between changelings
- [future] Offline agent handling (serving cached pages when agent is not running)
