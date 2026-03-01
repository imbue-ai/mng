Start a new conversation thread with the given message.

```bash
$MNG_HOST_DIR/commands/chat.sh --new --as-agent "$ARGUMENTS"
```

This creates a new conversation and injects the message as an agent-initiated message. The conversation will be visible in the chat interface and the conversation watcher will sync new messages to the event log.
