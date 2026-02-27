# zygote

A framework for building AI agents whose behavior is entirely defined by system prompts.

## Architecture

Zygote agents have two components:

### 1. Inner Dialog Agent Loop

The core of the agent. It receives notifications (user messages, system events, sub-agent completions) and processes them through a tool-use loop with the Claude API. All logic comes from the system prompt -- the code is just the plumbing.

Available tools:
- `send_message_to_thread` -- send messages to user chat threads
- `create_sub_agent` -- create sub-agents via mng
- `read_memory` / `write_memory` -- persistent key-value memory
- `compact_history` -- compact older messages into a summary

When the model stops calling tools, the agent yields control until the next notification.

### 2. Chat Response System

Generates replies for user threads by calling the model with:
- The chat system prompt (base + chat-specific instructions)
- The full conversation history for the thread
- A summary of the inner dialog's current state

### System Prompts

Three prompts control all behavior:
- **Base prompt**: shared identity and capabilities (used by both inner dialog and chat)
- **Inner dialog prompt**: how to think, when to use tools, how to handle notifications
- **Chat prompt**: how to respond to users, tone, format

## Usage

```python
import anthropic
from imbue.zygote.agent import ZygoteAgent
from imbue.zygote.data_types import ZygoteAgentConfig
from imbue.zygote.primitives import ModelName, NotificationSource, ThreadId

config = ZygoteAgentConfig(
    agent_name="my-agent",
    agent_description="A helpful assistant",
    base_system_prompt="You are a helpful assistant named Max.",
    inner_dialog_system_prompt="Process notifications carefully. Use memory to track context.",
    chat_system_prompt="Reply concisely and helpfully.",
    model=ModelName("claude-sonnet-4-5-20250514"),
)

client = anthropic.AsyncAnthropic()
agent = ZygoteAgent(config=config, client=client)

# Handle a user message (notifies inner dialog, then generates chat response)
thread_id = ThreadId()
response = await agent.receive_user_message(thread_id, "Hello!")

# Handle a system event (notifies inner dialog only)
await agent.receive_event(NotificationSource.SYSTEM, "Daily check-in")
```

## Extending

To add mng-based sub-agent creation, subclass `ZygoteAgent` and override `create_sub_agent`, or provide a custom `ToolExecutor`:

```python
from imbue.zygote.tools import ToolExecutor
from imbue.zygote.primitives import MemoryKey, ThreadId

class MyToolExecutor(ToolExecutor):
    async def send_message_to_thread(self, thread_id: ThreadId, content: str) -> str:
        # Default: delegate to agent
        ...

    async def create_sub_agent(self, name: str, agent_type: str, message: str) -> str:
        # Call mng to create a sub-agent
        ...

    async def read_memory(self, key: MemoryKey) -> str:
        ...

    async def write_memory(self, key: MemoryKey, value: str) -> str:
        ...

    async def compact_history(self) -> str:
        ...
```
