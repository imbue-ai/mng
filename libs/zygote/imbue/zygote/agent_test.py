import asyncio

import pytest

from imbue.zygote.agent import DefaultToolExecutor
from imbue.zygote.agent import ZygoteAgent
from imbue.zygote.agent import create_zygote_agent
from imbue.zygote.conftest import FakeAsyncAnthropic
from imbue.zygote.conftest import make_default_config
from imbue.zygote.conftest import make_text_response
from imbue.zygote.conftest import make_tool_use_response
from imbue.zygote.data_types import InnerDialogMessage
from imbue.zygote.errors import ToolExecutionError
from imbue.zygote.errors import ZygoteError
from imbue.zygote.primitives import MemoryKey
from imbue.zygote.primitives import MessageRole
from imbue.zygote.primitives import NotificationSource
from imbue.zygote.primitives import ThreadId


def _make_agent(
    responses: list | None = None,
) -> tuple[ZygoteAgent, FakeAsyncAnthropic]:
    client = FakeAsyncAnthropic(responses)
    agent = create_zygote_agent(config=make_default_config(), client=client)  # type: ignore[arg-type]
    return agent, client


def test_zygote_agent_initialization() -> None:
    agent, _ = _make_agent()
    assert agent.config == make_default_config()
    assert agent.inner_dialog_state.messages == ()
    assert agent.threads == {}
    assert agent.memory.entries == {}


def test_zygote_agent_get_thread_creates_new() -> None:
    agent, _ = _make_agent()
    thread_id = ThreadId()
    thread = agent.get_thread(thread_id)
    assert thread.id == thread_id
    assert thread.messages == ()


def test_zygote_agent_get_thread_returns_existing() -> None:
    agent, _ = _make_agent()
    thread_id = ThreadId()
    thread1 = agent.get_thread(thread_id)
    thread2 = agent.get_thread(thread_id)
    assert thread1.id == thread2.id


def test_zygote_agent_add_user_message() -> None:
    agent, _ = _make_agent()
    thread_id = ThreadId()
    msg = agent.add_user_message(thread_id, "hello")
    assert msg.role == MessageRole.USER
    assert msg.content == "hello"
    thread = agent.get_thread(thread_id)
    assert len(thread.messages) == 1
    assert thread.messages[0].content == "hello"


def test_zygote_agent_add_assistant_message() -> None:
    agent, _ = _make_agent()
    thread_id = ThreadId()
    msg = agent.add_assistant_message(thread_id, "hi there")
    assert msg.role == MessageRole.ASSISTANT
    assert msg.content == "hi there"


def test_zygote_agent_set_memory() -> None:
    agent, _ = _make_agent()
    key = MemoryKey("test_key")
    agent.set_memory(key, "test_value")
    assert agent.memory.entries[key] == "test_value"


def test_zygote_agent_set_memory_overwrites() -> None:
    agent, _ = _make_agent()
    key = MemoryKey("test_key")
    agent.set_memory(key, "value1")
    agent.set_memory(key, "value2")
    assert agent.memory.entries[key] == "value2"


def test_zygote_agent_receive_user_message() -> None:
    agent, _ = _make_agent(
        [
            make_text_response("Noted, user said hello."),
            make_text_response("Hi! How can I help?"),
        ]
    )
    thread_id = ThreadId()
    response = asyncio.run(agent.receive_user_message(thread_id, "Hello!"))
    assert response == "Hi! How can I help?"
    thread = agent.get_thread(thread_id)
    assert len(thread.messages) == 2
    assert thread.messages[0].role == MessageRole.USER
    assert thread.messages[1].role == MessageRole.ASSISTANT


def test_zygote_agent_receive_user_message_when_inner_dialog_already_replied() -> None:
    """If the inner dialog sends a message to the same thread via tool,
    that message should be returned directly without a second chat call."""
    thread_id = ThreadId()
    agent, client = _make_agent(
        [
            make_tool_use_response(
                "send_message_to_thread",
                {"thread_id": str(thread_id), "content": "I already replied!"},
            ),
            make_text_response("Done processing."),
        ]
    )

    response = asyncio.run(agent.receive_user_message(thread_id, "Hello!"))
    assert response == "I already replied!"
    thread = agent.get_thread(thread_id)
    assert len(thread.messages) == 2
    assert thread.messages[0].role == MessageRole.USER
    assert thread.messages[1].role == MessageRole.ASSISTANT


def test_zygote_agent_receive_event() -> None:
    agent, _ = _make_agent([make_text_response("Processing system event.")])
    asyncio.run(agent.receive_event(source=NotificationSource.SYSTEM, content="Daily check-in"))
    assert len(agent.inner_dialog_state.messages) == 2


def test_zygote_agent_create_sub_agent_default_raises() -> None:
    agent, _ = _make_agent()
    with pytest.raises(ZygoteError, match="not configured"):
        asyncio.run(agent.create_sub_agent("helper", "claude", "do stuff"))


def test_default_tool_executor_construction() -> None:
    agent, _ = _make_agent()
    executor = DefaultToolExecutor(agent=agent)
    assert executor.agent is agent


def test_default_tool_executor_send_message() -> None:
    agent, _ = _make_agent()
    executor = DefaultToolExecutor(agent=agent)
    thread_id = ThreadId()
    result = asyncio.run(executor.send_message_to_thread(thread_id, "hello from agent"))
    assert "sent" in result.lower()
    thread = agent.get_thread(thread_id)
    assert len(thread.messages) == 1
    assert thread.messages[0].role == MessageRole.ASSISTANT


def test_default_tool_executor_write_and_read_memory() -> None:
    agent, _ = _make_agent()
    executor = DefaultToolExecutor(agent=agent)
    asyncio.run(executor.write_memory(MemoryKey("key1"), "value1"))
    result = asyncio.run(executor.read_memory(MemoryKey("key1")))
    assert result == "value1"


def test_default_tool_executor_read_missing_key_raises() -> None:
    agent, _ = _make_agent()
    executor = DefaultToolExecutor(agent=agent)
    with pytest.raises(ToolExecutionError, match="not found"):
        asyncio.run(executor.read_memory(MemoryKey("nonexistent")))


def test_default_tool_executor_create_sub_agent_delegates_to_agent() -> None:
    agent, _ = _make_agent()
    executor = DefaultToolExecutor(agent=agent)
    with pytest.raises(ZygoteError, match="not configured"):
        asyncio.run(executor.create_sub_agent("helper", "claude", "task"))


def test_default_tool_executor_compact_history() -> None:
    agent, _ = _make_agent([make_text_response("Summary")])
    messages = tuple(
        InnerDialogMessage(
            role=MessageRole.USER if i % 2 == 0 else MessageRole.ASSISTANT,
            content=f"msg {i}",
        )
        for i in range(20)
    )
    agent.inner_dialog_state = agent.inner_dialog_state.model_copy(update={"messages": messages})
    executor = DefaultToolExecutor(agent=agent)
    result = asyncio.run(executor.compact_history())
    assert "compacted" in result.lower()
