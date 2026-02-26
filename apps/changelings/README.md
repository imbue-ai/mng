# changelings

Run your own persistent, specialized AI agents

## Overview

changelings is an application that makes it easy to create and deploy persistent, specialized AI agents that are *fully* yours.

Each changeling is a specific sub-type of `mng` agent. While `mng` agents can be any process running in a tmux session, changelings additionally *must*:

1. Serve a web interface (so that it is easy for users to interact with them)
2. Be conversational (able to receive messages from the user and generate responses)

Other than that, the design of each changeling is completely open -- you can customize the agent's behavior, the data it has access to, and the way it responds to messages in any way you want.

## Terminology

- **changeling**: a persistent `mng` agent that serves a web interface and is conversational. Each changeling has a unique name (e.g. "elena-turing") and runs its own web server.
- **zygote**: the minimal core of a changeling agent's code (e.g. cloned from a git repo). This is the starting point from which a changeling is configured and deployed.
- **template**: an HTML/web template used for serving a particular interface. Templates define how a changeling's web UI looks and behaves.
- **forwarding server**: a local process that handles authentication and proxies web traffic from the user's browser to the appropriate changeling's web server. Users access all their changelings through this single gateway.

## Architecture

The forwarding server runs locally and provides:
- Authentication via one-time codes and signed cookies
- A landing page listing all accessible changelings
- Reverse proxying of HTTP and WebSocket traffic to individual changeling web servers using Service Worker-based path rewriting

Each changeling runs its own web server on a separate port. The forwarding server multiplexes access to all of them under path prefixes (e.g. `/agents/elena-turing/`).

## Design

See [./docs/design.md](./docs/design.md) for more details on the design principles and architecture of changelings.
