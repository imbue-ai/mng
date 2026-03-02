---
name: send-message-to-user
description: Start a new conversation thread with a user or inject an agent-initiated message. Use when you need to respond to a user or proactively start a conversation.
---


## Conversations

Conversations are managed via the `chat` script:

- `$MNG_HOST_DIR/commands/chat.sh --new "message"` - start a new conversation
- `$MNG_HOST_DIR/commands/chat.sh --resume <id>` - resume an existing conversation
- `$MNG_HOST_DIR/commands/chat.sh --list` - list all conversations



# Starting a New Conversation

This skill creates a new conversation thread in the changeling's chat system.

## When to use

- A user message arrived that warrants a response in a new conversation (rather than replying in an existing one)
- You want to proactively reach out to the user about something
- You need to start a conversation with context from an event you processed

## How to create a conversation

Run the chat script with `--new --as-agent` and provide the message as an argument:

```bash
$MNG_HOST_DIR/commands/chat.sh --new --as-agent "Your message here"
```

This will:
1. Generate a unique conversation ID
2. Append a `conversation_created` event to `logs/conversations/events.jsonl`
3. Inject the message into the conversation via `llm inject`
4. The conversation will appear in the chat interface for the user to see and reply to

## Guidelines

- Keep initial messages clear and concise
- Reference the event or context that triggered the conversation when relevant
- If responding to a user message from another conversation, mention which conversation you are following up from
- The conversation watcher will automatically sync any replies back to the event log
