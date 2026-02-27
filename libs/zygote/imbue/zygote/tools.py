"""Tool definitions and execution for the inner dialog agent.

Tools are defined as Claude API tool schemas and executed via a ToolExecutor
protocol. The inner dialog agent uses these tools to interact with the outside
world -- sending messages to users, creating sub-agents, and managing memory.
"""

from abc import ABC
from abc import abstractmethod
from typing import Any
from typing import Final

from imbue.zygote.data_types import ToolResult
from imbue.zygote.errors import ToolExecutionError
from imbue.zygote.primitives import MemoryKey
from imbue.zygote.primitives import ThreadId

# =============================================================================
# Tool Definitions (Claude API format)
# =============================================================================

SEND_MESSAGE_TOOL: Final[dict[str, Any]] = {
    "name": "send_message_to_thread",
    "description": (
        "Send a message to a user chat thread. Use this to reply to users or send follow-up messages on a thread."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "thread_id": {
                "type": "string",
                "description": "The ID of the thread to send the message to",
            },
            "content": {
                "type": "string",
                "description": "The message content to send",
            },
        },
        "required": ["thread_id", "content"],
    },
}

CREATE_SUB_AGENT_TOOL: Final[dict[str, Any]] = {
    "name": "create_sub_agent",
    "description": (
        "Create a new sub-agent to handle a task. The sub-agent will be "
        "created using mng and will run independently. You will receive a "
        "notification when the sub-agent completes."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "name": {
                "type": "string",
                "description": "A name for the sub-agent",
            },
            "agent_type": {
                "type": "string",
                "description": "The type of agent to create (e.g., 'claude')",
            },
            "message": {
                "type": "string",
                "description": "Initial message/task for the sub-agent",
            },
        },
        "required": ["name", "agent_type", "message"],
    },
}

READ_MEMORY_TOOL: Final[dict[str, Any]] = {
    "name": "read_memory",
    "description": (
        "Read a value from persistent memory. Returns the stored value "
        "for the given key, or an error if the key does not exist."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "key": {
                "type": "string",
                "description": "The memory key to read",
            },
        },
        "required": ["key"],
    },
}

WRITE_MEMORY_TOOL: Final[dict[str, Any]] = {
    "name": "write_memory",
    "description": (
        "Write a value to persistent memory. This stores a key-value pair "
        "that persists across notifications. Use this to remember important "
        "context, decisions, or state."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "key": {
                "type": "string",
                "description": "The memory key to write",
            },
            "value": {
                "type": "string",
                "description": "The value to store",
            },
        },
        "required": ["key", "value"],
    },
}

COMPACT_HISTORY_TOOL: Final[dict[str, Any]] = {
    "name": "compact_history",
    "description": (
        "Request compaction of the inner dialog history. When the conversation "
        "history becomes long, call this to summarize older messages into a "
        "concise summary, freeing up context space."
    ),
    "input_schema": {
        "type": "object",
        "properties": {},
    },
}

ALL_TOOLS: Final[tuple[dict[str, Any], ...]] = (
    SEND_MESSAGE_TOOL,
    CREATE_SUB_AGENT_TOOL,
    READ_MEMORY_TOOL,
    WRITE_MEMORY_TOOL,
    COMPACT_HISTORY_TOOL,
)


# =============================================================================
# Tool Executor Interface
# =============================================================================


class ToolExecutor(ABC):
    """Interface for executing tools called by the inner dialog agent.

    Implementations of this interface provide the actual behavior for each tool.
    The inner dialog loop calls execute_tool() with the tool name and input,
    and the executor returns the result.
    """

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


async def execute_tool(
    tool_name: str,
    tool_input: dict[str, Any],
    tool_use_id: str,
    executor: ToolExecutor,
) -> ToolResult:
    """Execute a tool call and return the result.

    Routes the tool call to the appropriate method on the executor,
    catching ToolExecutionError and returning it as an error result.
    """
    try:
        result_content = await _dispatch_tool(tool_name, tool_input, executor)
        return ToolResult(tool_use_id=tool_use_id, content=result_content)
    except ToolExecutionError as e:
        return ToolResult(tool_use_id=tool_use_id, content=str(e), is_error=True)


async def _dispatch_tool(
    tool_name: str,
    tool_input: dict[str, Any],
    executor: ToolExecutor,
) -> str:
    """Dispatch a tool call to the appropriate executor method."""
    match tool_name:
        case "send_message_to_thread":
            return await executor.send_message_to_thread(
                thread_id=ThreadId(tool_input["thread_id"]),
                content=tool_input["content"],
            )
        case "create_sub_agent":
            return await executor.create_sub_agent(
                name=tool_input["name"],
                agent_type=tool_input["agent_type"],
                message=tool_input["message"],
            )
        case "read_memory":
            return await executor.read_memory(key=MemoryKey(tool_input["key"]))
        case "write_memory":
            return await executor.write_memory(
                key=MemoryKey(tool_input["key"]),
                value=tool_input["value"],
            )
        case "compact_history":
            return await executor.compact_history()
        case _:
            raise ToolExecutionError(f"Unknown tool: {tool_name}")
