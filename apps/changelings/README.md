# changelings

Run your own persistent, specialized AI agents

## Overview

changelings is an application that makes it easy to create and deploy persistent, specialized AI agents that are *fully* yours.

Each changeling is simply an agent created with `mng` that has persistent state. Each changeling must:

1. Run a web server (so that it is easy for users to interact with it)
2. Accept incoming messages from the user (so that it can respond to user requests)

Other than that, the design of each changeling is completely open -- you can customize the agent's behavior, the data it has access to, and the way it responds to messages in any way you want.

There are lots of examples of how to get started:

- (TODO: actually create some examples and link them here)

## Design

See [./docs/design.md](./docs/design.md) for more details on the design principles and architecture of changelings.
