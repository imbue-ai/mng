from typing import Any

import anthropic

from imbue.imbue_common.conftest_hooks import register_conftest_hooks
from imbue.zygote.data_types import ZygoteAgentConfig
from imbue.zygote.errors import ToolExecutionError
from imbue.zygote.primitives import MemoryKey
from imbue.zygote.primitives import ModelName
from imbue.zygote.primitives import ThreadId
from imbue.zygote.tools import ToolExecutor

register_conftest_hooks(globals())


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


class FailingSendExecutor(ToolExecutor):
    """Mock executor where send_message_to_thread raises ToolExecutionError."""

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


class FakeTextBlock:
    """Concrete fake for anthropic text content blocks."""

    def __init__(self, text: str) -> None:
        self.type = "text"
        self.text = text

    def model_dump(self) -> dict[str, str]:
        return {"type": "text", "text": self.text}


class FakeMessage:
    """Concrete fake for anthropic.types.Message responses."""

    def __init__(self, content: list[Any]) -> None:
        self.content = content


class FakeMessagesAPI:
    """Concrete fake for the messages.create API."""

    def __init__(self, responses: list[Any] | None = None) -> None:
        self._responses = list(responses) if responses else []
        self._call_count = 0
        self.last_call_kwargs: dict[str, Any] = {}

    async def create(self, **kwargs: Any) -> Any:
        self.last_call_kwargs = kwargs
        if self._responses:
            response = self._responses[self._call_count % len(self._responses)]
            self._call_count += 1
            return response
        return FakeMessage([FakeTextBlock("default response")])


class FakeAsyncAnthropic:
    """Concrete fake for anthropic.AsyncAnthropic."""

    def __init__(self, responses: list[Any] | None = None) -> None:
        self.messages = FakeMessagesAPI(responses)


def make_text_response(text: str) -> FakeMessage:
    """Create a FakeMessage with a single text block."""
    return FakeMessage([FakeTextBlock(text)])


def make_tool_use_response(name: str, tool_input: dict[str, Any], block_id: str = "tool_1") -> FakeMessage:
    """Create a FakeMessage with a single tool_use block."""
    block = anthropic.types.ToolUseBlock(
        id=block_id,
        type="tool_use",
        name=name,
        input=tool_input,
    )
    return FakeMessage([block])


def make_default_config() -> ZygoteAgentConfig:
    """Create a default ZygoteAgentConfig for tests."""
    return ZygoteAgentConfig(
        agent_name="test-agent",
        agent_description="A test agent",
        base_system_prompt="You are a test agent.",
        inner_dialog_system_prompt="Process notifications carefully.",
        chat_system_prompt="Reply concisely.",
        model=ModelName("claude-sonnet-4-5-20250514"),
    )
