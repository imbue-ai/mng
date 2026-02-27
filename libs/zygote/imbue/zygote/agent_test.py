import asyncio
from unittest.mock import AsyncMock
from unittest.mock import MagicMock

import pytest

from imbue.zygote.agent import DefaultToolExecutor
from imbue.zygote.agent import ZygoteAgent
from imbue.zygote.data_types import ZygoteAgentConfig
from imbue.zygote.errors import ToolExecutionError
from imbue.zygote.errors import ZygoteError
from imbue.zygote.primitives import MemoryKey
from imbue.zygote.primitives import MessageRole
from imbue.zygote.primitives import ModelName
from imbue.zygote.primitives import NotificationSource
from imbue.zygote.primitives import ThreadId


def _make_config() -> ZygoteAgentConfig:
    return ZygoteAgentConfig(
        agent_name="test-agent",
        agent_description="A test agent",
        base_system_prompt="You are a test agent.",
        inner_dialog_system_prompt="Process notifications carefully.",
        chat_system_prompt="Reply concisely.",
        model=ModelName("claude-sonnet-4-5-20250514"),
    )


def _make_text_block(text: str) -> MagicMock:
    block = MagicMock()
    block.type = "text"
    block.text = text
    block.model_dump.return_value = {"type": "text", "text": text}
    return block


def _make_text_response(text: str) -> MagicMock:
    response = MagicMock()
    response.content = [_make_text_block(text)]
    return response


class TestZygoteAgent:
    def test_initialization(self) -> None:
        config = _make_config()
        client = AsyncMock()
        agent = ZygoteAgent(config=config, client=client)

        assert agent.config == config
        assert agent.inner_dialog_state.messages == ()
        assert agent.threads == {}
        assert agent.memory.entries == {}

    def test_get_thread_creates_new(self) -> None:
        agent = ZygoteAgent(config=_make_config(), client=AsyncMock())
        thread_id = ThreadId()
        thread = agent.get_thread(thread_id)

        assert thread.id == thread_id
        assert thread.messages == ()

    def test_get_thread_returns_existing(self) -> None:
        agent = ZygoteAgent(config=_make_config(), client=AsyncMock())
        thread_id = ThreadId()
        thread1 = agent.get_thread(thread_id)
        thread2 = agent.get_thread(thread_id)

        assert thread1.id == thread2.id

    def test_add_user_message(self) -> None:
        agent = ZygoteAgent(config=_make_config(), client=AsyncMock())
        thread_id = ThreadId()
        msg = agent.add_user_message(thread_id, "hello")

        assert msg.role == MessageRole.USER
        assert msg.content == "hello"

        thread = agent.get_thread(thread_id)
        assert len(thread.messages) == 1
        assert thread.messages[0].content == "hello"

    def test_add_assistant_message(self) -> None:
        agent = ZygoteAgent(config=_make_config(), client=AsyncMock())
        thread_id = ThreadId()
        msg = agent.add_assistant_message(thread_id, "hi there")

        assert msg.role == MessageRole.ASSISTANT
        assert msg.content == "hi there"

    def test_set_memory(self) -> None:
        agent = ZygoteAgent(config=_make_config(), client=AsyncMock())
        key = MemoryKey("test_key")
        agent.set_memory(key, "test_value")

        assert agent.memory.entries[key] == "test_value"

    def test_set_memory_overwrites(self) -> None:
        agent = ZygoteAgent(config=_make_config(), client=AsyncMock())
        key = MemoryKey("test_key")
        agent.set_memory(key, "value1")
        agent.set_memory(key, "value2")

        assert agent.memory.entries[key] == "value2"

    def test_receive_user_message(self) -> None:
        client = AsyncMock()
        # Inner dialog response (no tools)
        inner_response = _make_text_response("Noted, user said hello.")
        # Chat response
        chat_response = _make_text_response("Hi! How can I help?")
        client.messages.create = AsyncMock(side_effect=[inner_response, chat_response])

        agent = ZygoteAgent(config=_make_config(), client=client)
        thread_id = ThreadId()

        response = asyncio.run(agent.receive_user_message(thread_id, "Hello!"))

        assert response == "Hi! How can I help?"
        # Thread should have user message + assistant response
        thread = agent.get_thread(thread_id)
        assert len(thread.messages) == 2
        assert thread.messages[0].role == MessageRole.USER
        assert thread.messages[1].role == MessageRole.ASSISTANT

    def test_receive_event(self) -> None:
        client = AsyncMock()
        inner_response = _make_text_response("Processing system event.")
        client.messages.create = AsyncMock(return_value=inner_response)

        agent = ZygoteAgent(config=_make_config(), client=client)

        asyncio.run(
            agent.receive_event(
                source=NotificationSource.SYSTEM,
                content="Daily check-in",
            )
        )

        # Inner dialog should have processed the notification
        assert len(agent.inner_dialog_state.messages) == 2

    def test_create_sub_agent_default_raises(self) -> None:
        agent = ZygoteAgent(config=_make_config(), client=AsyncMock())

        with pytest.raises(ZygoteError, match="not configured"):
            asyncio.run(agent.create_sub_agent("helper", "claude", "do stuff"))


class TestDefaultToolExecutor:
    def test_construction(self) -> None:
        agent = ZygoteAgent(config=_make_config(), client=AsyncMock())
        executor = DefaultToolExecutor(agent)
        assert executor._agent is agent

    def test_send_message(self) -> None:
        agent = ZygoteAgent(config=_make_config(), client=AsyncMock())
        executor = DefaultToolExecutor(agent)
        thread_id = ThreadId()

        result = asyncio.run(executor.send_message_to_thread(thread_id, "hello from agent"))

        assert "sent" in result.lower()
        thread = agent.get_thread(thread_id)
        assert len(thread.messages) == 1
        assert thread.messages[0].role == MessageRole.ASSISTANT

    def test_write_and_read_memory(self) -> None:
        agent = ZygoteAgent(config=_make_config(), client=AsyncMock())
        executor = DefaultToolExecutor(agent)

        asyncio.run(executor.write_memory(MemoryKey("key1"), "value1"))
        result = asyncio.run(executor.read_memory(MemoryKey("key1")))

        assert result == "value1"

    def test_read_missing_key_raises(self) -> None:
        agent = ZygoteAgent(config=_make_config(), client=AsyncMock())
        executor = DefaultToolExecutor(agent)

        with pytest.raises(ToolExecutionError, match="not found"):
            asyncio.run(executor.read_memory(MemoryKey("nonexistent")))

    def test_create_sub_agent_delegates_to_agent(self) -> None:
        agent = ZygoteAgent(config=_make_config(), client=AsyncMock())
        executor = DefaultToolExecutor(agent)

        with pytest.raises(ZygoteError, match="not configured"):
            asyncio.run(executor.create_sub_agent("helper", "claude", "task"))

    def test_compact_history(self) -> None:
        client = AsyncMock()
        summary_block = MagicMock()
        summary_block.text = "Summary"
        client.messages.create = AsyncMock(return_value=MagicMock(content=[summary_block]))

        agent = ZygoteAgent(config=_make_config(), client=client)
        # Add enough messages to trigger compaction
        messages = tuple({"role": "user" if i % 2 == 0 else "assistant", "content": f"msg {i}"} for i in range(20))
        agent._inner_dialog_state = agent._inner_dialog_state.model_copy(update={"messages": messages})

        executor = DefaultToolExecutor(agent)
        result = asyncio.run(executor.compact_history())

        assert "compacted" in result.lower()
