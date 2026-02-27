import asyncio
from datetime import datetime
from datetime import timezone
from typing import Any

from imbue.zygote.conftest import FakeAsyncAnthropic
from imbue.zygote.conftest import MockToolExecutor
from imbue.zygote.conftest import make_text_response
from imbue.zygote.conftest import make_tool_use_response
from imbue.zygote.data_types import InnerDialogState
from imbue.zygote.data_types import Notification
from imbue.zygote.inner_dialog import _build_notification_user_message
from imbue.zygote.inner_dialog import _build_system_with_summary
from imbue.zygote.inner_dialog import compact_inner_dialog
from imbue.zygote.inner_dialog import get_inner_dialog_summary
from imbue.zygote.inner_dialog import process_notification
from imbue.zygote.primitives import ModelName
from imbue.zygote.primitives import NotificationId
from imbue.zygote.primitives import NotificationSource
from imbue.zygote.primitives import ThreadId


def _make_notification(
    content: str = "test notification",
    source: NotificationSource = NotificationSource.USER_MESSAGE,
    thread_id: ThreadId | None = None,
) -> Notification:
    return Notification(
        id=NotificationId(),
        source=source,
        content=content,
        thread_id=thread_id,
        timestamp=datetime.now(timezone.utc),
    )


class TestBuildNotificationUserMessage:
    def test_with_thread(self) -> None:
        thread_id = ThreadId()
        notif = _make_notification(content="hello", thread_id=thread_id)
        msg = _build_notification_user_message(notif)
        assert msg["role"] == "user"
        assert "USER_MESSAGE" in msg["content"]
        assert str(thread_id) in msg["content"]
        assert "hello" in msg["content"]

    def test_without_thread(self) -> None:
        notif = _make_notification(content="event", source=NotificationSource.SYSTEM)
        msg = _build_notification_user_message(notif)
        assert msg["role"] == "user"
        assert "SYSTEM" in msg["content"]
        assert "event" in msg["content"]


class TestBuildSystemWithSummary:
    def test_without_summary(self) -> None:
        result = _build_system_with_summary("base prompt", None)
        assert result == "base prompt"

    def test_with_summary(self) -> None:
        result = _build_system_with_summary("base prompt", "previous context")
        assert "base prompt" in result
        assert "previous context" in result
        assert "Previous Context" in result


class TestProcessNotification:
    def test_basic_notification(self) -> None:
        """Test processing a notification that gets a text-only response."""
        client = FakeAsyncAnthropic([make_text_response("I'll look into that.")])

        state = InnerDialogState()
        notification = _make_notification("user says hello")

        new_state = asyncio.run(
            process_notification(
                state=state,
                notification=notification,
                system_prompt="You are a helpful agent.",
                tool_executor=MockToolExecutor(),
                client=client,  # type: ignore[arg-type]
                model=ModelName("claude-sonnet-4-5-20250514"),
            )
        )

        assert len(new_state.messages) == 2  # notification + response
        assert new_state.messages[0]["role"] == "user"
        assert new_state.messages[1]["role"] == "assistant"

    def test_notification_with_tool_call(self) -> None:
        """Test processing a notification where the model calls a tool."""
        client = FakeAsyncAnthropic(
            [
                make_tool_use_response("write_memory", {"key": "user_name", "value": "Alice"}),
                make_text_response("Got it, I'll remember that."),
            ]
        )

        state = InnerDialogState()
        notification = _make_notification("My name is Alice")

        new_state = asyncio.run(
            process_notification(
                state=state,
                notification=notification,
                system_prompt="You are a helpful agent.",
                tool_executor=MockToolExecutor(),
                client=client,  # type: ignore[arg-type]
                model=ModelName("claude-sonnet-4-5-20250514"),
            )
        )

        # Should have: notification, tool_call_response, tool_result, final_response
        assert len(new_state.messages) == 4

    def test_preserves_existing_state(self) -> None:
        """Test that existing messages in state are preserved."""
        client = FakeAsyncAnthropic([make_text_response("ok")])

        existing_messages: tuple[dict[str, Any], ...] = (
            {"role": "user", "content": "previous message"},
            {"role": "assistant", "content": [{"type": "text", "text": "previous response"}]},
        )
        state = InnerDialogState(messages=existing_messages)
        notification = _make_notification("new message")

        new_state = asyncio.run(
            process_notification(
                state=state,
                notification=notification,
                system_prompt="prompt",
                tool_executor=MockToolExecutor(),
                client=client,  # type: ignore[arg-type]
                model=ModelName("claude-sonnet-4-5-20250514"),
            )
        )

        # 2 existing + 1 notification + 1 response = 4
        assert len(new_state.messages) == 4


class TestCompactInnerDialog:
    def test_compact_when_short(self) -> None:
        """Test that compaction is a no-op when history is short."""
        client = FakeAsyncAnthropic()
        state = InnerDialogState(
            messages=({"role": "user", "content": "hello"},),
        )

        result = asyncio.run(
            compact_inner_dialog(
                state=state,
                client=client,  # type: ignore[arg-type]
                model=ModelName("claude-sonnet-4-5-20250514"),
                messages_to_preserve=10,
            )
        )

        assert result == state

    def test_compact_when_long(self) -> None:
        """Test that compaction summarizes older messages."""
        client = FakeAsyncAnthropic([make_text_response("Summary of conversation.")])

        messages: tuple[dict[str, Any], ...] = tuple(
            {"role": "user" if i % 2 == 0 else "assistant", "content": f"msg {i}"} for i in range(20)
        )
        state = InnerDialogState(messages=messages)

        result = asyncio.run(
            compact_inner_dialog(
                state=state,
                client=client,  # type: ignore[arg-type]
                model=ModelName("claude-sonnet-4-5-20250514"),
                messages_to_preserve=5,
            )
        )

        assert result.compacted_summary == "Summary of conversation."
        assert len(result.messages) == 5


class TestGetInnerDialogSummary:
    def test_empty_state(self) -> None:
        state = InnerDialogState()
        summary = get_inner_dialog_summary(state)
        assert "no prior activity" in summary

    def test_with_compacted_summary(self) -> None:
        state = InnerDialogState(compacted_summary="Agent has been working on X.")
        summary = get_inner_dialog_summary(state)
        assert "Agent has been working on X." in summary

    def test_with_recent_messages(self) -> None:
        state = InnerDialogState(
            messages=(
                {"role": "user", "content": "hello from user"},
                {"role": "assistant", "content": [{"type": "text", "text": "agent thinking"}]},
            ),
        )
        summary = get_inner_dialog_summary(state)
        assert "hello from user" in summary
        assert "agent thinking" in summary

    def test_truncates_long_content(self) -> None:
        long_content = "x" * 500
        state = InnerDialogState(
            messages=({"role": "user", "content": long_content},),
        )
        summary = get_inner_dialog_summary(state)
        assert len(summary) < len(long_content)
