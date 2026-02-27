# changelings

Run your own persistent, specialized AI agents

## Overview

changelings is an application that makes it easy to create and deploy persistent, specialized AI agents that are *fully* yours.

Each changeling is a specific sub-type of `mng` agent. While `mng` agents can be any process running in a tmux session, changelings additionally *must*:

1. Serve a web interface (so that it is easy for users to interact with them)
2. Be conversational (able to receive messages from the user and generate responses)

Other than that, the design of each changeling is completely open -- you can customize the agent's behavior, the data it has access to, and the way it responds to messages in any way you want.

## Terminology

- **changeling**: a persistent `mng` agent that serves a web interface and is conversational. Each changeling is identified by its `AgentId` (the standard mng agent identifier) and serves a web interface from the `mng` `Host` where it is running (possibly locally, in modal, or in a docker container).
- **zygote**: the minimal core of a changeling agent's code (e.g. cloned from a git repo). This is the starting point from which a changeling is configured and deployed.
- **forwarding server**: a local process that handles authentication and proxies web traffic from the user's browser to the appropriate changeling's web server. Users access all their changelings through such gateways. There may be both a local and remote forwarding servers.

## Architecture

The forwarding servers provide:
- Authentication via one-time codes and signed cookies
- A landing page listing all accessible changelings
- Reverse proxying of HTTP and WebSocket traffic to individual changeling web servers using Service Worker-based path rewriting

Each changeling runs its own web server on a separate port. The forwarding server multiplexes access to all of them under path prefixes (e.g. `/agents/{agent_id}/`).

## Design

See [./docs/design.md](./docs/design.md) for more details on the design principles and architecture of changelings.
