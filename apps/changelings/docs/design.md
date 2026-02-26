# Overview

Each changeling is a deployed web server (persistent or serverless) that serves a persistent, special-purpose AI agent

# Design principles

1. **Simplicity**: The system should be as simple as possible, both in terms of user experience and internal architecture. Each changeling is simply a web server with some persistent storage (ideally just a file system) that, by convention, ends up calling an AI agent to respond to messages from the user. The only required routes are for the index and for handling incoming messages.
2. **Personal**: Changelings are designed to serve an *individual* user. They may respond to requests from other humans (or agents), but only to the extent that they are configured to do so by their primary human user.
3. **Open**: Changelings are both transparent (the user should always be able to see exactly what is going on and dive into any detail they want) and extensible (the user should be able to easily add new capabilities, and to modify or remove existing ones).
4. **Trustworthy**: Changelings should take security and safety seriously. They should have minimal access to data that they do not need, and for the minimal amount of time that they need it.
