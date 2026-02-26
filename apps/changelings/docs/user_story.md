This is the primary flow for how a user would deploy a changeling for the first time:

1. user pastes this command into their terminal: "changelings deploy elena-turing"
2. (user gets through various auth flows, now has tokens--just assume this exists for now, we'll just set the right env vars)
3. user answers some questions:
 - what do you want to name the agent? [<agent-name> | <type something>]
 - where do you want this agent to run? [modal | local | docker]
 - do you want this agent to be able to launch its own agents?  [yes | not now]
 - do you want to access this agent from anywhere besides this computer?  [yes (requires forwarding server) | not now]
 - do you want to receive mobile notifications from this agent? [yes (requires notification setup) | not now]
4. we run: "git clone <agent-repo-url> && mng create --in <provider> <...extra args determined by file in agent repo>"
    if the user wants the agent to be able to run its own agents and tasks, we ensure that `mng` is injected as well
5. if local access only: we ensure a local daemon python web process is running (for forwarding requests and receiving notifications & auth requests from the agent and displaying them locally). Forwarding servers bring offline agents back online.
6. (future) if remote access: we deploy that forwarding server (eg to modal), which will forward requests to the agent (including web hooks). Forwarding servers bring offline agents back online.
7. we're done: print the associated URL(s) where the agent can be accessed

The point of this whole flow is to make it as easy as possible for users to deploy a new changeling.
