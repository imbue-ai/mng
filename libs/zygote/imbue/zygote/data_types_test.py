from datetime import datetime
from datetime import timezone

from imbue.zygote.data_types import AgentMemory
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


class TestThreadMessage:
    def test_construction(self) -> None:
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

    def test_frozen(self) -> None:
        msg = ThreadMessage(
            id=MessageId(),
            role=MessageRole.USER,
            content="hello",
            timestamp=datetime.now(timezone.utc),
        )
        # FrozenModel should not allow mutation
        try:
            msg.content = "changed"  # type: ignore[misc]
            assert False, "Should have raised"
        except Exception:
            pass


class TestThread:
    def test_empty_thread(self) -> None:
        thread = Thread(id=ThreadId())
        assert thread.messages == ()

    def test_thread_with_messages(self) -> None:
        msg = ThreadMessage(
            id=MessageId(),
            role=MessageRole.USER,
            content="hello",
            timestamp=datetime.now(timezone.utc),
        )
        thread = Thread(id=ThreadId(), messages=(msg,))
        assert len(thread.messages) == 1
        assert thread.messages[0].content == "hello"


class TestNotification:
    def test_construction_with_thread(self) -> None:
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

    def test_construction_without_thread(self) -> None:
        notif = Notification(
            id=NotificationId(),
            source=NotificationSource.SYSTEM,
            content="system event",
            timestamp=datetime.now(timezone.utc),
        )
        assert notif.thread_id is None


class TestToolResult:
    def test_success(self) -> None:
        result = ToolResult(tool_use_id="id_123", content="done")
        assert not result.is_error

    def test_error(self) -> None:
        result = ToolResult(tool_use_id="id_123", content="failed", is_error=True)
        assert result.is_error


class TestInnerDialogState:
    def test_empty(self) -> None:
        state = InnerDialogState()
        assert state.messages == ()
        assert state.compacted_summary is None

    def test_with_messages(self) -> None:
        state = InnerDialogState(
            messages=({"role": "user", "content": "hello"},),
        )
        assert len(state.messages) == 1

    def test_with_summary(self) -> None:
        state = InnerDialogState(compacted_summary="previous context")
        assert state.compacted_summary == "previous context"


class TestAgentMemory:
    def test_empty(self) -> None:
        mem = AgentMemory()
        assert mem.entries == {}

    def test_with_entries(self) -> None:
        mem = AgentMemory(entries={MemoryKey("key1"): "value1"})
        assert mem.entries[MemoryKey("key1")] == "value1"


class TestZygoteAgentConfig:
    def test_defaults(self) -> None:
        config = ZygoteAgentConfig(
            agent_name="test",
            agent_description="test agent",
            base_system_prompt="base",
            inner_dialog_system_prompt="inner",
            chat_system_prompt="chat",
        )
        assert config.model == ModelName("claude-sonnet-4-5-20250514")
        assert config.max_tokens == 4096
        assert config.max_inner_dialog_messages == 100

    def test_custom_model(self) -> None:
        config = ZygoteAgentConfig(
            agent_name="test",
            agent_description="test agent",
            base_system_prompt="base",
            inner_dialog_system_prompt="inner",
            chat_system_prompt="chat",
            model=ModelName("claude-opus-4-6"),
        )
        assert config.model == ModelName("claude-opus-4-6")
