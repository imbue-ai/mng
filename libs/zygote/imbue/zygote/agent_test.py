import asyncio

import anthropic
import pytest

from imbue.zygote.agent import DefaultToolExecutor
from imbue.zygote.agent import ZygoteAgent
from imbue.zygote.conftest import FakeAsyncAnthropic
from imbue.zygote.conftest import make_default_config
from imbue.zygote.conftest import make_text_response
from imbue.zygote.conftest import make_tool_use_response
from imbue.zygote.errors import ToolExecutionError
from imbue.zygote.errors import ZygoteError
from imbue.zygote.primitives import MemoryKey
from imbue.zygote.primitives import MessageRole
from imbue.zygote.primitives import NotificationSource
from imbue.zygote.primitives import ThreadId


class TestZygoteAgent:
    def test_initialization(self) -> None:
        config = make_default_config()
        client = FakeAsyncAnthropic()
        agent = ZygoteAgent(config=config, client=client)  # type: ignore[arg-type]

        assert agent.config == config
        assert agent.inner_dialog_state.messages == ()
        assert agent.threads == {}
        assert agent.memory.entries == {}

    def test_get_thread_creates_new(self) -> None:
        agent = ZygoteAgent(config=make_default_config(), client=FakeAsyncAnthropic())  # type: ignore[arg-type]
        thread_id = ThreadId()
        thread = agent.get_thread(thread_id)

        assert thread.id == thread_id
        assert thread.messages == ()

    def test_get_thread_returns_existing(self) -> None:
        agent = ZygoteAgent(config=make_default_config(), client=FakeAsyncAnthropic())  # type: ignore[arg-type]
        thread_id = ThreadId()
        thread1 = agent.get_thread(thread_id)
        thread2 = agent.get_thread(thread_id)

        assert thread1.id == thread2.id

    def test_add_user_message(self) -> None:
        agent = ZygoteAgent(config=make_default_config(), client=FakeAsyncAnthropic())  # type: ignore[arg-type]
        thread_id = ThreadId()
        msg = agent.add_user_message(thread_id, "hello")

        assert msg.role == MessageRole.USER
        assert msg.content == "hello"

        thread = agent.get_thread(thread_id)
        assert len(thread.messages) == 1
        assert thread.messages[0].content == "hello"

    def test_add_assistant_message(self) -> None:
        agent = ZygoteAgent(config=make_default_config(), client=FakeAsyncAnthropic())  # type: ignore[arg-type]
        thread_id = ThreadId()
        msg = agent.add_assistant_message(thread_id, "hi there")

        assert msg.role == MessageRole.ASSISTANT
        assert msg.content == "hi there"

    def test_set_memory(self) -> None:
        agent = ZygoteAgent(config=make_default_config(), client=FakeAsyncAnthropic())  # type: ignore[arg-type]
        key = MemoryKey("test_key")
        agent.set_memory(key, "test_value")

        assert agent.memory.entries[key] == "test_value"

    def test_set_memory_overwrites(self) -> None:
        agent = ZygoteAgent(config=make_default_config(), client=FakeAsyncAnthropic())  # type: ignore[arg-type]
        key = MemoryKey("test_key")
        agent.set_memory(key, "value1")
        agent.set_memory(key, "value2")

        assert agent.memory.entries[key] == "value2"

    def test_receive_user_message(self) -> None:
        # Inner dialog response (no tools), then chat response
        client = FakeAsyncAnthropic(
            [
                make_text_response("Noted, user said hello."),
                make_text_response("Hi! How can I help?"),
            ]
        )

        agent = ZygoteAgent(config=make_default_config(), client=client)  # type: ignore[arg-type]
        thread_id = ThreadId()

        response = asyncio.run(agent.receive_user_message(thread_id, "Hello!"))

        assert response == "Hi! How can I help?"
        thread = agent.get_thread(thread_id)
        assert len(thread.messages) == 2
        assert thread.messages[0].role == MessageRole.USER
        assert thread.messages[1].role == MessageRole.ASSISTANT

    def test_receive_user_message_when_inner_dialog_already_replied(self) -> None:
        """If the inner dialog sends a message to the same thread via tool,
        that message should be returned directly without a second chat call."""
        client = FakeAsyncAnthropic(
            [
                # Inner dialog calls send_message_to_thread on the same thread
                make_tool_use_response(
                    "send_message_to_thread",
                    {"thread_id": "", "content": "I already replied!"},
                ),
                # After tool result, inner dialog finishes
                make_text_response("Done processing."),
            ]
        )

        agent = ZygoteAgent(config=make_default_config(), client=client)  # type: ignore[arg-type]
        thread_id = ThreadId()

        # Patch the tool_use_response to use the actual thread_id
        # We need to set the thread_id in the tool input after we know it
        client.messages._responses[0].content[0] = anthropic.types.ToolUseBlock(
            id="tool_1",
            type="tool_use",
            name="send_message_to_thread",
            input={"thread_id": str(thread_id), "content": "I already replied!"},
        )

        response = asyncio.run(agent.receive_user_message(thread_id, "Hello!"))

        # Should return the inner dialog's tool-sent message, not generate a new chat response
        assert response == "I already replied!"
        thread = agent.get_thread(thread_id)
        assert len(thread.messages) == 2
        assert thread.messages[0].role == MessageRole.USER
        assert thread.messages[1].role == MessageRole.ASSISTANT

    def test_receive_event(self) -> None:
        client = FakeAsyncAnthropic([make_text_response("Processing system event.")])

        agent = ZygoteAgent(config=make_default_config(), client=client)  # type: ignore[arg-type]

        asyncio.run(
            agent.receive_event(
                source=NotificationSource.SYSTEM,
                content="Daily check-in",
            )
        )

        assert len(agent.inner_dialog_state.messages) == 2

    def test_create_sub_agent_default_raises(self) -> None:
        agent = ZygoteAgent(config=make_default_config(), client=FakeAsyncAnthropic())  # type: ignore[arg-type]

        with pytest.raises(ZygoteError, match="not configured"):
            asyncio.run(agent.create_sub_agent("helper", "claude", "do stuff"))


class TestDefaultToolExecutor:
    def test_construction(self) -> None:
        agent = ZygoteAgent(config=make_default_config(), client=FakeAsyncAnthropic())  # type: ignore[arg-type]
        executor = DefaultToolExecutor(agent)
        assert executor._agent is agent

    def test_send_message(self) -> None:
        agent = ZygoteAgent(config=make_default_config(), client=FakeAsyncAnthropic())  # type: ignore[arg-type]
        executor = DefaultToolExecutor(agent)
        thread_id = ThreadId()

        result = asyncio.run(executor.send_message_to_thread(thread_id, "hello from agent"))

        assert "sent" in result.lower()
        thread = agent.get_thread(thread_id)
        assert len(thread.messages) == 1
        assert thread.messages[0].role == MessageRole.ASSISTANT

    def test_write_and_read_memory(self) -> None:
        agent = ZygoteAgent(config=make_default_config(), client=FakeAsyncAnthropic())  # type: ignore[arg-type]
        executor = DefaultToolExecutor(agent)

        asyncio.run(executor.write_memory(MemoryKey("key1"), "value1"))
        result = asyncio.run(executor.read_memory(MemoryKey("key1")))

        assert result == "value1"

    def test_read_missing_key_raises(self) -> None:
        agent = ZygoteAgent(config=make_default_config(), client=FakeAsyncAnthropic())  # type: ignore[arg-type]
        executor = DefaultToolExecutor(agent)

        with pytest.raises(ToolExecutionError, match="not found"):
            asyncio.run(executor.read_memory(MemoryKey("nonexistent")))

    def test_create_sub_agent_delegates_to_agent(self) -> None:
        agent = ZygoteAgent(config=make_default_config(), client=FakeAsyncAnthropic())  # type: ignore[arg-type]
        executor = DefaultToolExecutor(agent)

        with pytest.raises(ZygoteError, match="not configured"):
            asyncio.run(executor.create_sub_agent("helper", "claude", "task"))

    def test_compact_history(self) -> None:
        client = FakeAsyncAnthropic([make_text_response("Summary")])

        agent = ZygoteAgent(config=make_default_config(), client=client)  # type: ignore[arg-type]
        messages = tuple({"role": "user" if i % 2 == 0 else "assistant", "content": f"msg {i}"} for i in range(20))
        agent._inner_dialog_state = agent._inner_dialog_state.model_copy(update={"messages": messages})

        executor = DefaultToolExecutor(agent)
        result = asyncio.run(executor.compact_history())

        assert "compacted" in result.lower()
