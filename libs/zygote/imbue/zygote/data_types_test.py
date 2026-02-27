from datetime import datetime
from datetime import timezone

import pydantic
import pytest

from imbue.imbue_common.primitives import NonEmptyStr
from imbue.zygote.data_types import AgentMemory
from imbue.zygote.data_types import InnerDialogMessage
from imbue.zygote.data_types import InnerDialogState
from imbue.zygote.data_types import Notification
from imbue.zygote.data_types import Thread
from imbue.zygote.data_types import ThreadMessage
from imbue.zygote.data_types import ToolResult
from imbue.zygote.data_types import ZygoteAgentConfig
from imbue.zygote.primitives import MemoryKey
from imbue.zygote.primitives import MessageId
from imbue.zygote.primitives import MessageRole
from imbue.zygote.primitives import ModelName
from imbue.zygote.primitives import NotificationId
from imbue.zygote.primitives import NotificationSource
from imbue.zygote.primitives import ThreadId


def test_thread_message_construction() -> None:
    now = datetime.now(timezone.utc)
    msg = ThreadMessage(
        id=MessageId(),
        role=MessageRole.USER,
        content="hello",
        timestamp=now,
    )
    assert msg.role == MessageRole.USER
    assert msg.content == "hello"
    assert msg.timestamp == now


def test_thread_message_frozen() -> None:
    msg = ThreadMessage(
        id=MessageId(),
        role=MessageRole.USER,
        content="hello",
        timestamp=datetime.now(timezone.utc),
    )
    with pytest.raises(pydantic.ValidationError):
        msg.content = "changed"  # type: ignore[misc]


def test_thread_empty() -> None:
    thread = Thread(id=ThreadId())
    assert thread.messages == ()


def test_thread_with_messages() -> None:
    msg = ThreadMessage(
        id=MessageId(),
        role=MessageRole.USER,
        content="hello",
        timestamp=datetime.now(timezone.utc),
    )
    thread = Thread(id=ThreadId(), messages=(msg,))
    assert len(thread.messages) == 1
    assert thread.messages[0].content == "hello"


def test_notification_construction_with_thread() -> None:
    thread_id = ThreadId()
    notif = Notification(
        id=NotificationId(),
        source=NotificationSource.USER_MESSAGE,
        content="new message",
        thread_id=thread_id,
        timestamp=datetime.now(timezone.utc),
    )
    assert notif.source == NotificationSource.USER_MESSAGE
    assert notif.thread_id == thread_id


def test_notification_construction_without_thread() -> None:
    notif = Notification(
        id=NotificationId(),
        source=NotificationSource.SYSTEM,
        content="system event",
        timestamp=datetime.now(timezone.utc),
    )
    assert notif.thread_id is None


def test_tool_result_success() -> None:
    result = ToolResult(tool_use_id="id_123", content="done")
    assert not result.is_error


def test_tool_result_error() -> None:
    result = ToolResult(tool_use_id="id_123", content="failed", is_error=True)
    assert result.is_error


def test_inner_dialog_state_empty() -> None:
    state = InnerDialogState()
    assert state.messages == ()
    assert state.compacted_summary is None


def test_inner_dialog_state_with_messages() -> None:
    msg = InnerDialogMessage(role=MessageRole.USER, content="hello")
    state = InnerDialogState(messages=(msg,))
    assert len(state.messages) == 1


def test_inner_dialog_state_with_summary() -> None:
    state = InnerDialogState(compacted_summary="previous context")
    assert state.compacted_summary == "previous context"


def test_agent_memory_empty() -> None:
    mem = AgentMemory()
    assert mem.entries == {}


def test_agent_memory_with_entries() -> None:
    mem = AgentMemory(entries={MemoryKey("key1"): "value1"})
    assert mem.entries[MemoryKey("key1")] == "value1"


def test_zygote_agent_config_defaults() -> None:
    config = ZygoteAgentConfig(
        agent_name=NonEmptyStr("test"),
        agent_description=NonEmptyStr("test agent"),
        base_system_prompt=NonEmptyStr("base"),
        inner_dialog_system_prompt=NonEmptyStr("inner"),
        chat_system_prompt=NonEmptyStr("chat"),
    )
    assert config.model == ModelName("claude-sonnet-4-5-20250514")
    assert config.max_tokens == 4096
    assert config.max_inner_dialog_messages == 100


def test_zygote_agent_config_custom_model() -> None:
    config = ZygoteAgentConfig(
        agent_name=NonEmptyStr("test"),
        agent_description=NonEmptyStr("test agent"),
        base_system_prompt=NonEmptyStr("base"),
        inner_dialog_system_prompt=NonEmptyStr("inner"),
        chat_system_prompt=NonEmptyStr("chat"),
        model=ModelName("claude-opus-4-6"),
    )
    assert config.model == ModelName("claude-opus-4-6")
