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
from typing import Any
from typing import Self

from pydantic import Field
from pydantic import model_validator

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
from imbue.zygote.interfaces import ToolExecutorInterface
from imbue.zygote.interfaces import ZygoteAgentInterface
from imbue.zygote.primitives import MemoryKey
from imbue.zygote.primitives import MessageId
from imbue.zygote.primitives import MessageRole
from imbue.zygote.primitives import NotificationId
from imbue.zygote.primitives import NotificationSource
from imbue.zygote.primitives import ThreadId
from imbue.zygote.prompts import build_inner_dialog_full_prompt


class DefaultToolExecutor(ToolExecutorInterface):
    """Default tool executor that delegates to the ZygoteAgent.

    This executor implements the tool interface by calling back into the
    agent that owns it, providing access to threads, memory, and sub-agent
    creation.
    """

    model_config = {"arbitrary_types_allowed": True}

    agent: Any = Field(description="The agent this executor delegates to")

    async def send_message_to_thread(self, thread_id: ThreadId, content: str) -> str:
        self.agent.add_assistant_message(thread_id, content)
        return f"Message sent to thread {thread_id}"

    async def create_sub_agent(self, name: str, agent_type: str, message: str) -> str:
        return await self.agent.create_sub_agent(name, agent_type, message)

    async def read_memory(self, key: MemoryKey) -> str:
        value = self.agent.memory.entries.get(key)
        if value is None:
            raise ToolExecutionError(f"Memory key not found: {key}")
        return value

    async def write_memory(self, key: MemoryKey, value: str) -> str:
        self.agent.set_memory(key, value)
        return f"Stored value for key: {key}"

    async def compact_history(self) -> str:
        await self.agent.compact_inner_dialog()
        return "History compacted successfully"


class ZygoteAgent(ZygoteAgentInterface):
    """A text-defined AI agent with an inner dialog loop and chat threads.

    The agent is split into two pieces:
    1. An inner dialog loop that processes notifications and uses tools.
       All logic comes from the system prompt.
    2. A chat response system that generates replies for user threads,
       informed by the inner dialog's current state.

    Usage:
        config = ZygoteAgentConfig(...)
        agent = ZygoteAgent(
            config=config,
            client=AsyncAnthropic(),
        )

        # User sends a message
        response = await agent.receive_user_message(thread_id, "Hello!")

        # System event occurs
        await agent.receive_event(NotificationSource.SYSTEM, "Daily check-in")
    """

    model_config = {"arbitrary_types_allowed": True}

    config: ZygoteAgentConfig = Field(description="Agent configuration")
    client: Any = Field(description="Anthropic API client (anthropic.AsyncAnthropic or compatible)")
    inner_dialog_state: InnerDialogState = Field(
        default_factory=InnerDialogState,
        description="Current state of the inner dialog",
    )
    thread_store: dict[ThreadId, Thread] = Field(
        default_factory=dict,
        description="Active chat threads",
    )
    memory: AgentMemory = Field(
        default_factory=AgentMemory,
        description="Persistent key-value memory",
    )
    inner_dialog_system_prompt: str = Field(
        default="",
        description="Compiled inner dialog system prompt (auto-generated from config)",
    )
    tool_executor: Any = Field(
        default=None,
        description="Tool executor for inner dialog (auto-generated if not provided)",
    )

    @model_validator(mode="after")
    def _initialize_computed_fields(self) -> Self:
        """Compute the inner dialog system prompt and default tool executor."""
        if not self.inner_dialog_system_prompt:
            self.inner_dialog_system_prompt = build_inner_dialog_full_prompt(
                base_prompt=self.config.base_system_prompt,
                inner_dialog_prompt=self.config.inner_dialog_system_prompt,
            )
        if self.tool_executor is None:
            self.tool_executor = DefaultToolExecutor(agent=self)
        return self

    @property
    def threads(self) -> dict[ThreadId, Thread]:
        return dict(self.thread_store)

    def get_thread(self, thread_id: ThreadId) -> Thread:
        """Get a thread by ID, creating it if it does not exist."""
        if thread_id not in self.thread_store:
            self.thread_store[thread_id] = Thread(id=thread_id)
        return self.thread_store[thread_id]

    def _add_message(self, thread_id: ThreadId, content: str, role: MessageRole) -> ThreadMessage:
        """Add a message with the given role to a thread."""
        thread = self.get_thread(thread_id)
        message = ThreadMessage(
            id=MessageId(),
            role=role,
            content=content,
            timestamp=datetime.now(timezone.utc),
        )
        self.thread_store[thread_id] = thread.model_copy_update(
            to_update(thread.field_ref().messages, thread.messages + (message,))
        )
        return message

    def add_user_message(self, thread_id: ThreadId, content: str) -> ThreadMessage:
        """Add a user message to a thread."""
        return self._add_message(thread_id, content, MessageRole.USER)

    def add_assistant_message(self, thread_id: ThreadId, content: str) -> ThreadMessage:
        """Add an assistant message to a thread."""
        return self._add_message(thread_id, content, MessageRole.ASSISTANT)

    def set_memory(self, key: MemoryKey, value: str) -> None:
        """Set a value in the agent's persistent memory."""
        new_entries = dict(self.memory.entries)
        new_entries[key] = value
        self.memory = AgentMemory(entries=new_entries)

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
        self.inner_dialog_state = await process_notification(
            state=self.inner_dialog_state,
            notification=notification,
            system_prompt=self.inner_dialog_system_prompt,
            tool_executor=self.tool_executor,
            client=self.client,
            model=self.config.model,
            max_tokens=self.config.max_tokens,
        )

        await self._compact_if_needed()

        # If the inner dialog already replied to this thread (via the
        # send_message_to_thread tool), return that reply directly instead
        # of generating a separate chat response.
        thread = self.get_thread(thread_id)
        if thread.messages and thread.messages[-1].role == MessageRole.ASSISTANT:
            return thread.messages[-1].content

        inner_summary = get_inner_dialog_summary(self.inner_dialog_state)

        response = await generate_chat_response(
            thread=thread,
            inner_dialog_summary=inner_summary,
            base_system_prompt=self.config.base_system_prompt,
            chat_system_prompt=self.config.chat_system_prompt,
            client=self.client,
            model=self.config.model,
            max_tokens=self.config.max_tokens,
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
        self.inner_dialog_state = await process_notification(
            state=self.inner_dialog_state,
            notification=notification,
            system_prompt=self.inner_dialog_system_prompt,
            tool_executor=self.tool_executor,
            client=self.client,
            model=self.config.model,
            max_tokens=self.config.max_tokens,
        )

        await self._compact_if_needed()

    async def _compact_if_needed(self) -> None:
        """Compact the inner dialog history if it exceeds the maximum."""
        if len(self.inner_dialog_state.messages) > self.config.max_inner_dialog_messages:
            await self.compact_inner_dialog()

    async def compact_inner_dialog(self) -> None:
        """Compact the inner dialog history."""
        self.inner_dialog_state = await compact_inner_dialog(
            state=self.inner_dialog_state,
            client=self.client,
            model=self.config.model,
            max_tokens=self.config.max_tokens,
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
