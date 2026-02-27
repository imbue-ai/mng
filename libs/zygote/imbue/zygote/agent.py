"""The main ZygoteAgent class.

ZygoteAgent ties together the inner dialog loop and chat response system.
It manages threads, the inner dialog state, and memory, and provides
a simple interface for receiving messages and events.

The agent's behavior is entirely defined by its system prompts -- the code
here is just the plumbing that connects the inner dialog loop to chat
threads and tool execution.
"""

from datetime import datetime
from datetime import timezone

import anthropic

from imbue.imbue_common.model_update import to_update
from imbue.zygote.chat import generate_chat_response
from imbue.zygote.data_types import AgentMemory
from imbue.zygote.data_types import InnerDialogState
from imbue.zygote.data_types import Notification
from imbue.zygote.data_types import Thread
from imbue.zygote.data_types import ThreadMessage
from imbue.zygote.data_types import ZygoteAgentConfig
from imbue.zygote.errors import ToolExecutionError
from imbue.zygote.errors import ZygoteError
from imbue.zygote.inner_dialog import compact_inner_dialog
from imbue.zygote.inner_dialog import get_inner_dialog_summary
from imbue.zygote.inner_dialog import process_notification
from imbue.zygote.primitives import MemoryKey
from imbue.zygote.primitives import MessageId
from imbue.zygote.primitives import MessageRole
from imbue.zygote.primitives import NotificationId
from imbue.zygote.primitives import NotificationSource
from imbue.zygote.primitives import ThreadId
from imbue.zygote.prompts import build_inner_dialog_full_prompt
from imbue.zygote.tools import ToolExecutor


class DefaultToolExecutor(ToolExecutor):
    """Default tool executor that delegates to the ZygoteAgent.

    This executor implements the tool interface by calling back into the
    agent that owns it, providing access to threads, memory, and sub-agent
    creation.
    """

    def __init__(self, agent: "ZygoteAgent") -> None:
        self._agent = agent

    async def send_message_to_thread(self, thread_id: ThreadId, content: str) -> str:
        self._agent.add_assistant_message(thread_id, content)
        return f"Message sent to thread {thread_id}"

    async def create_sub_agent(self, name: str, agent_type: str, message: str) -> str:
        return await self._agent.create_sub_agent(name, agent_type, message)

    async def read_memory(self, key: MemoryKey) -> str:
        value = self._agent.memory.entries.get(key)
        if value is None:
            raise ToolExecutionError(f"Memory key not found: {key}")
        return value

    async def write_memory(self, key: MemoryKey, value: str) -> str:
        self._agent.set_memory(key, value)
        return f"Stored value for key: {key}"

    async def compact_history(self) -> str:
        await self._agent.compact_inner_dialog()
        return "History compacted successfully"


class ZygoteAgent:
    """A text-defined AI agent with an inner dialog loop and chat threads.

    The agent is split into two pieces:
    1. An inner dialog loop that processes notifications and uses tools.
       All logic comes from the system prompt.
    2. A chat response system that generates replies for user threads,
       informed by the inner dialog's current state.

    Usage:
        config = ZygoteAgentConfig(...)
        agent = ZygoteAgent(config=config, client=AsyncAnthropic())

        # User sends a message
        response = await agent.receive_user_message(thread_id, "Hello!")

        # System event occurs
        await agent.receive_event(NotificationSource.SYSTEM, "Daily check-in")
    """

    def __init__(
        self,
        config: ZygoteAgentConfig,
        client: anthropic.AsyncAnthropic,
        tool_executor: ToolExecutor | None = None,
    ) -> None:
        self._config = config
        self._client = client
        self._inner_dialog_state = InnerDialogState()
        self._threads: dict[ThreadId, Thread] = {}
        self._memory = AgentMemory()
        self._inner_dialog_system_prompt = build_inner_dialog_full_prompt(
            base_prompt=config.base_system_prompt,
            inner_dialog_prompt=config.inner_dialog_system_prompt,
        )
        self._tool_executor = tool_executor or DefaultToolExecutor(self)

    @property
    def config(self) -> ZygoteAgentConfig:
        return self._config

    @property
    def inner_dialog_state(self) -> InnerDialogState:
        return self._inner_dialog_state

    @property
    def threads(self) -> dict[ThreadId, Thread]:
        return dict(self._threads)

    @property
    def memory(self) -> AgentMemory:
        return self._memory

    def get_thread(self, thread_id: ThreadId) -> Thread:
        """Get a thread by ID, creating it if it does not exist."""
        if thread_id not in self._threads:
            self._threads[thread_id] = Thread(id=thread_id)
        return self._threads[thread_id]

    def add_user_message(self, thread_id: ThreadId, content: str) -> ThreadMessage:
        """Add a user message to a thread."""
        thread = self.get_thread(thread_id)
        message = ThreadMessage(
            id=MessageId(),
            role=MessageRole.USER,
            content=content,
            timestamp=datetime.now(timezone.utc),
        )
        self._threads[thread_id] = thread.model_copy_update(
            to_update(thread.field_ref().messages, thread.messages + (message,))
        )
        return message

    def add_assistant_message(self, thread_id: ThreadId, content: str) -> ThreadMessage:
        """Add an assistant message to a thread."""
        thread = self.get_thread(thread_id)
        message = ThreadMessage(
            id=MessageId(),
            role=MessageRole.ASSISTANT,
            content=content,
            timestamp=datetime.now(timezone.utc),
        )
        self._threads[thread_id] = thread.model_copy_update(
            to_update(thread.field_ref().messages, thread.messages + (message,))
        )
        return message

    def set_memory(self, key: MemoryKey, value: str) -> None:
        """Set a value in the agent's persistent memory."""
        new_entries = dict(self._memory.entries)
        new_entries[key] = value
        self._memory = AgentMemory(entries=new_entries)

    async def receive_user_message(self, thread_id: ThreadId, message: str) -> str:
        """Handle a user message: notify inner dialog, then generate chat response.

        Returns the assistant's chat response for the thread.

        If the inner dialog already sent a message to this thread (via the
        send_message_to_thread tool), that message is returned directly
        instead of generating a separate chat response.
        """
        self.add_user_message(thread_id, message)

        notification = Notification(
            id=NotificationId(),
            source=NotificationSource.USER_MESSAGE,
            content=message,
            thread_id=thread_id,
            timestamp=datetime.now(timezone.utc),
        )
        self._inner_dialog_state = await process_notification(
            state=self._inner_dialog_state,
            notification=notification,
            system_prompt=self._inner_dialog_system_prompt,
            tool_executor=self._tool_executor,
            client=self._client,
            model=self._config.model,
            max_tokens=self._config.max_tokens,
        )

        if len(self._inner_dialog_state.messages) > self._config.max_inner_dialog_messages:
            await self.compact_inner_dialog()

        # If the inner dialog already replied to this thread (via the
        # send_message_to_thread tool), return that reply directly instead
        # of generating a separate chat response.
        thread = self.get_thread(thread_id)
        if thread.messages and thread.messages[-1].role == MessageRole.ASSISTANT:
            return thread.messages[-1].content

        inner_summary = get_inner_dialog_summary(self._inner_dialog_state)

        response = await generate_chat_response(
            thread=thread,
            inner_dialog_summary=inner_summary,
            base_system_prompt=self._config.base_system_prompt,
            chat_system_prompt=self._config.chat_system_prompt,
            client=self._client,
            model=self._config.model,
            max_tokens=self._config.max_tokens,
        )

        self.add_assistant_message(thread_id, response)
        return response

    async def receive_event(
        self,
        source: NotificationSource,
        content: str,
        thread_id: ThreadId | None = None,
    ) -> None:
        """Handle a system event by notifying the inner dialog.

        Unlike receive_user_message, this does not generate a chat response.
        The inner dialog may use tools (including send_message_to_thread)
        to respond to the event.
        """
        notification = Notification(
            id=NotificationId(),
            source=source,
            content=content,
            thread_id=thread_id,
            timestamp=datetime.now(timezone.utc),
        )
        self._inner_dialog_state = await process_notification(
            state=self._inner_dialog_state,
            notification=notification,
            system_prompt=self._inner_dialog_system_prompt,
            tool_executor=self._tool_executor,
            client=self._client,
            model=self._config.model,
            max_tokens=self._config.max_tokens,
        )

    async def compact_inner_dialog(self) -> None:
        """Compact the inner dialog history."""
        self._inner_dialog_state = await compact_inner_dialog(
            state=self._inner_dialog_state,
            client=self._client,
            model=self._config.model,
            max_tokens=self._config.max_tokens,
        )

    async def create_sub_agent(self, name: str, agent_type: str, message: str) -> str:
        """Create a sub-agent via mng.

        This is a placeholder that should be overridden or configured
        with an actual mng integration. The default implementation
        raises an error.
        """
        raise ZygoteError(
            "Sub-agent creation not configured. Override create_sub_agent or provide a custom ToolExecutor."
        )
