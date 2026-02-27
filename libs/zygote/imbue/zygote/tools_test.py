import asyncio

from imbue.zygote.errors import ToolExecutionError
from imbue.zygote.primitives import MemoryKey
from imbue.zygote.primitives import ThreadId
from imbue.zygote.tools import ALL_TOOLS
from imbue.zygote.tools import COMPACT_HISTORY_TOOL
from imbue.zygote.tools import CREATE_SUB_AGENT_TOOL
from imbue.zygote.tools import READ_MEMORY_TOOL
from imbue.zygote.tools import SEND_MESSAGE_TOOL
from imbue.zygote.tools import ToolExecutor
from imbue.zygote.tools import WRITE_MEMORY_TOOL
from imbue.zygote.tools import execute_tool


class MockToolExecutor(ToolExecutor):
    """Mock executor that records calls and returns canned responses."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, str]]] = []

    async def send_message_to_thread(self, thread_id: ThreadId, content: str) -> str:
        self.calls.append(("send_message", {"thread_id": str(thread_id), "content": content}))
        return "message sent"

    async def create_sub_agent(self, name: str, agent_type: str, message: str) -> str:
        self.calls.append(("create_sub_agent", {"name": name, "agent_type": agent_type, "message": message}))
        return "agent created"

    async def read_memory(self, key: MemoryKey) -> str:
        self.calls.append(("read_memory", {"key": str(key)}))
        return "stored_value"

    async def write_memory(self, key: MemoryKey, value: str) -> str:
        self.calls.append(("write_memory", {"key": str(key), "value": value}))
        return "written"

    async def compact_history(self) -> str:
        self.calls.append(("compact_history", {}))
        return "compacted"


class TestToolDefinitions:
    def test_all_tools_count(self) -> None:
        assert len(ALL_TOOLS) == 5

    def test_all_tools_have_names(self) -> None:
        for tool in ALL_TOOLS:
            assert "name" in tool
            assert "description" in tool
            assert "input_schema" in tool

    def test_send_message_tool_schema(self) -> None:
        assert SEND_MESSAGE_TOOL["name"] == "send_message_to_thread"
        required = SEND_MESSAGE_TOOL["input_schema"]["required"]
        assert "thread_id" in required
        assert "content" in required

    def test_create_sub_agent_tool_schema(self) -> None:
        assert CREATE_SUB_AGENT_TOOL["name"] == "create_sub_agent"
        required = CREATE_SUB_AGENT_TOOL["input_schema"]["required"]
        assert "name" in required
        assert "agent_type" in required
        assert "message" in required

    def test_read_memory_tool_schema(self) -> None:
        assert READ_MEMORY_TOOL["name"] == "read_memory"
        required = READ_MEMORY_TOOL["input_schema"]["required"]
        assert "key" in required

    def test_write_memory_tool_schema(self) -> None:
        assert WRITE_MEMORY_TOOL["name"] == "write_memory"
        required = WRITE_MEMORY_TOOL["input_schema"]["required"]
        assert "key" in required
        assert "value" in required

    def test_compact_history_tool_schema(self) -> None:
        assert COMPACT_HISTORY_TOOL["name"] == "compact_history"


class TestExecuteTool:
    def test_send_message(self) -> None:
        executor = MockToolExecutor()
        result = asyncio.run(
            execute_tool(
                tool_name="send_message_to_thread",
                tool_input={"thread_id": str(ThreadId()), "content": "hello"},
                tool_use_id="test_id",
                executor=executor,
            )
        )
        assert not result.is_error
        assert "message sent" in result.content
        assert len(executor.calls) == 1

    def test_create_sub_agent(self) -> None:
        executor = MockToolExecutor()
        result = asyncio.run(
            execute_tool(
                tool_name="create_sub_agent",
                tool_input={"name": "helper", "agent_type": "claude", "message": "do stuff"},
                tool_use_id="test_id",
                executor=executor,
            )
        )
        assert not result.is_error
        assert "agent created" in result.content

    def test_read_memory(self) -> None:
        executor = MockToolExecutor()
        result = asyncio.run(
            execute_tool(
                tool_name="read_memory",
                tool_input={"key": "my_key"},
                tool_use_id="test_id",
                executor=executor,
            )
        )
        assert not result.is_error
        assert "stored_value" in result.content

    def test_write_memory(self) -> None:
        executor = MockToolExecutor()
        result = asyncio.run(
            execute_tool(
                tool_name="write_memory",
                tool_input={"key": "my_key", "value": "my_value"},
                tool_use_id="test_id",
                executor=executor,
            )
        )
        assert not result.is_error
        assert "written" in result.content

    def test_compact_history(self) -> None:
        executor = MockToolExecutor()
        result = asyncio.run(
            execute_tool(
                tool_name="compact_history",
                tool_input={},
                tool_use_id="test_id",
                executor=executor,
            )
        )
        assert not result.is_error
        assert "compacted" in result.content

    def test_unknown_tool(self) -> None:
        executor = MockToolExecutor()
        result = asyncio.run(
            execute_tool(
                tool_name="nonexistent_tool",
                tool_input={},
                tool_use_id="test_id",
                executor=executor,
            )
        )
        assert result.is_error
        assert "Unknown tool" in result.content

    def test_tool_execution_error(self) -> None:
        class FailingExecutor(ToolExecutor):
            async def send_message_to_thread(self, thread_id: ThreadId, content: str) -> str:
                raise ToolExecutionError("connection failed")

            async def create_sub_agent(self, name: str, agent_type: str, message: str) -> str:
                return ""

            async def read_memory(self, key: MemoryKey) -> str:
                return ""

            async def write_memory(self, key: MemoryKey, value: str) -> str:
                return ""

            async def compact_history(self) -> str:
                return ""

        result = asyncio.run(
            execute_tool(
                tool_name="send_message_to_thread",
                tool_input={"thread_id": str(ThreadId()), "content": "hello"},
                tool_use_id="test_id",
                executor=FailingExecutor(),
            )
        )
        assert result.is_error
        assert "connection failed" in result.content
