"""Interface definitions for the zygote agent framework."""

from abc import ABC
from abc import abstractmethod

from imbue.imbue_common.mutable_model import MutableModel
from imbue.zygote.data_types import Thread
from imbue.zygote.data_types import ThreadMessage
from imbue.zygote.primitives import MemoryKey
from imbue.zygote.primitives import NotificationSource
from imbue.zygote.primitives import ThreadId


class ToolExecutorInterface(MutableModel, ABC):
    """Interface for executing tools called by the inner dialog agent.

    Implementations of this interface provide the actual behavior for each tool.
    The inner dialog loop calls execute_tool() with the tool name and input,
    and the executor returns the result.
    """

    model_config = {"arbitrary_types_allowed": True}

    @abstractmethod
    async def send_message_to_thread(self, thread_id: ThreadId, content: str) -> str:
        """Send a message to a user chat thread. Returns a confirmation string."""
        ...

    @abstractmethod
    async def create_sub_agent(self, name: str, agent_type: str, message: str) -> str:
        """Create a sub-agent via mng. Returns a status string."""
        ...

    @abstractmethod
    async def read_memory(self, key: MemoryKey) -> str:
        """Read a value from persistent memory. Returns the stored value."""
        ...

    @abstractmethod
    async def write_memory(self, key: MemoryKey, value: str) -> str:
        """Write a value to persistent memory. Returns a confirmation string."""
        ...

    @abstractmethod
    async def compact_history(self) -> str:
        """Compact the inner dialog history. Returns the summary."""
        ...


class ZygoteAgentInterface(MutableModel, ABC):
    """Interface for the ZygoteAgent.

    Defines the public contract for interacting with a zygote agent,
    including receiving messages, events, and managing threads and memory.
    """

    model_config = {"arbitrary_types_allowed": True}

    @abstractmethod
    def get_thread(self, thread_id: ThreadId) -> Thread:
        """Get a thread by ID, creating it if it does not exist."""
        ...

    @abstractmethod
    def add_user_message(self, thread_id: ThreadId, content: str) -> ThreadMessage:
        """Add a user message to a thread."""
        ...

    @abstractmethod
    def add_assistant_message(self, thread_id: ThreadId, content: str) -> ThreadMessage:
        """Add an assistant message to a thread."""
        ...

    @abstractmethod
    def set_memory(self, key: MemoryKey, value: str) -> None:
        """Set a value in the agent's persistent memory."""
        ...

    @abstractmethod
    async def receive_user_message(self, thread_id: ThreadId, message: str) -> str:
        """Handle a user message and return a response."""
        ...

    @abstractmethod
    async def receive_event(
        self,
        source: NotificationSource,
        content: str,
        thread_id: ThreadId | None = None,
    ) -> None:
        """Handle a system event by notifying the inner dialog."""
        ...

    @abstractmethod
    async def compact_inner_dialog(self) -> None:
        """Compact the inner dialog history."""
        ...

    @abstractmethod
    async def create_sub_agent(self, name: str, agent_type: str, message: str) -> str:
        """Create a sub-agent. Must be overridden with actual mng integration."""
        ...
