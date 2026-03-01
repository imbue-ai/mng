# Changeling Agent

You are a changeling agent managed by mng. This repo is your working directory.

## Key paths

- `.changelings/` - changeling configuration and entrypoints
- `.changelings/memory/` - shared memory (synced to Claude project memory)
- `.changelings/settings.toml` - changeling settings (optional)

## Working with mng

Use `mng` for all agent management:

- `mng list` - list running agents
- `mng create` - create sub-agents for delegated work
- `mng destroy <agent>` - clean up finished agents
- `mng message <agent> -m "..."` - send a message to an agent
- `mng exec <agent> "command"` - run a command on an agent's host

## Conversations

Conversations are managed via the `chat` script:

- `$MNG_HOST_DIR/commands/chat.sh --new "message"` - start a new conversation
- `$MNG_HOST_DIR/commands/chat.sh --resume <id>` - resume an existing conversation
- `$MNG_HOST_DIR/commands/chat.sh --list` - list all conversations

## Conventions

- Commit changes to this repo when you modify files
- Use project-scoped memory for all persistent notes
- Prefer mng commands over direct system operations for agent management
