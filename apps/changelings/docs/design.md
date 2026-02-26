# Overview

Each changeling is simply a `mng` agent that has persistent state.

# Design principles

1. **Simplicity**: The system should be as simple as possible, both in terms of user experience and internal architecture. Each changeling is simply a web server with some persistent storage (ideally just a file system) that, by convention, ends up calling an AI agent to respond to messages from the user. The only required routes are for the index and for handling incoming messages.
2. **Personal**: Changelings are designed to serve an *individual* user. They may respond to requests from other humans (or agents), but only to the extent that they are configured to do so by their primary human user.
3. **Open**: Changelings are both transparent (the user should always be able to see exactly what is going on and dive into any detail they want) and extensible (the user should be able to easily add new capabilities, and to modify or remove existing ones).
4. **Trustworthy**: Changelings should take security and safety seriously. They should have minimal access to data that they do not need, and for the minimal amount of time that they need it.

# Architecture for changeling agents

They have code repos for their *own* code, should make commits there if they're ever changing anything
You can optionally link their code to a git remote in case you want them to push their changes and make debugging easier

They use space in the host volume (via the agent dir) for data
You can optionally configure them to store their memories in git (but that is less secure, now data is leaking out, esp if you're syncing)

They *must* service web requests on some port (configurable, but will almost always be the default one, unless you're running a bunch locally)
They can just append an event with the current port into <agent_data_dir>/logs/agent_server.jsonl to expose the data to mng

# Architecture for local forwarding server

The local forwarding server is just a super simple fastapi app that takes care of authentication and traffic forwarding.
It has its own built-in key for signing cookies that it sends back.

## Local forwarding server routes:

"/login" route (takes agent_id and one_time_code params)
    if you have a cookie for this agent_id, it redirects you to the main page ("/")
    if you don't have a cookie, it uses js to redirect you and your secret to "/authenticate?agent_id={agent_id}&one_time_code={one_time_code}"
        this is done to prevent preloading servers from accidentally consuming your one-time use codes

"/authenticate" route  (takes agent_id and one_time_code params)
    pulls the proxy auth headers out of the request URL
    if this is a valid one time code for this agent it (eg not used and not yet revoked), mark it as used and reply with a cookie showing that this is valid (for storing this data, just use a json file on disk somewhere)
    if this is not a valid one time code, explain to the user that they need to generate a new login URL for this device (each URL can only be used once)

"/" route is special
    looks at the cookies you have--for each valid agent_id cookie you have, that is considered in the listing
    if you have 0 valid agent_id cookies, it shows a placeholder telling you to log in
    if you have 1 or more valid agent_id cookie, those agents are part of the list that is rendered into the dropdown
    basically the page is just a simple jinja template that is a list of links to each of the accesible agents ("/<agent_id>/")

"/{agent_id}/" route serves the individual agent URLs. Has two basic states:
    if the agent is online, basically just proxying any request from the user back to the forwarded agent URL
        there's an irritating level of complexity with service workers to get this to work, but seems like it should
    if the agent is offline, serve "index.html" from the agent's data volume (if it exists) or just a placeholder "the agent is offline" page for now

all pages except the "/", "/login" and "/authenticate" are agent-specific (contain the agent_id in the URL) and require the auth cookie to be set for that agent

# Command line interface

We can start with just:

- `changelings deploy <agent-repo-url>` (deploys a new agent from the given repo URL, which should be a git repo containing an agent that follows the changeling conventions)
- `changelings list` (lists all deployed agents and their status)
