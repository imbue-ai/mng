import asyncio
from datetime import datetime
from datetime import timezone
from typing import Any
from unittest.mock import AsyncMock
from unittest.mock import MagicMock

import anthropic

from imbue.zygote.data_types import InnerDialogState
from imbue.zygote.data_types import Notification
from imbue.zygote.inner_dialog import _build_notification_user_message
from imbue.zygote.inner_dialog import _build_system_with_summary
from imbue.zygote.inner_dialog import compact_inner_dialog
from imbue.zygote.inner_dialog import get_inner_dialog_summary
from imbue.zygote.inner_dialog import process_notification
from imbue.zygote.primitives import MemoryKey
from imbue.zygote.primitives import ModelName
from imbue.zygote.primitives import NotificationId
from imbue.zygote.primitives import NotificationSource
from imbue.zygote.primitives import ThreadId
from imbue.zygote.tools import ToolExecutor


class MockToolExecutor(ToolExecutor):
    async def send_message_to_thread(self, thread_id: ThreadId, content: str) -> str:
        return "sent"

    async def create_sub_agent(self, name: str, agent_type: str, message: str) -> str:
        return "created"

    async def read_memory(self, key: MemoryKey) -> str:
        return "value"

    async def write_memory(self, key: MemoryKey, value: str) -> str:
        return "written"

    async def compact_history(self) -> str:
        return "compacted"


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


def _make_text_block(text: str) -> MagicMock:
    block = MagicMock()
    block.type = "text"
    block.text = text
    block.model_dump.return_value = {"type": "text", "text": text}
    return block


def _make_tool_use_block(
    name: str, tool_input: dict[str, Any], block_id: str = "tool_1"
) -> anthropic.types.ToolUseBlock:
    return anthropic.types.ToolUseBlock(
        id=block_id,
        type="tool_use",
        name=name,
        input=tool_input,
    )


def _make_response(*content_blocks: Any) -> MagicMock:
    response = MagicMock()
    response.content = list(content_blocks)
    return response


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
        client = AsyncMock()
        client.messages.create = AsyncMock(return_value=_make_response(_make_text_block("I'll look into that.")))

        state = InnerDialogState()
        notification = _make_notification("user says hello")

        new_state = asyncio.run(
            process_notification(
                state=state,
                notification=notification,
                system_prompt="You are a helpful agent.",
                tool_executor=MockToolExecutor(),
                client=client,
                model=ModelName("claude-sonnet-4-5-20250514"),
            )
        )

        assert len(new_state.messages) == 2  # notification + response
        assert new_state.messages[0]["role"] == "user"
        assert new_state.messages[1]["role"] == "assistant"

    def test_notification_with_tool_call(self) -> None:
        """Test processing a notification where the model calls a tool."""
        client = AsyncMock()

        # First response: tool call
        tool_response = _make_response(_make_tool_use_block("write_memory", {"key": "user_name", "value": "Alice"}))
        # Second response: text only (loop ends)
        text_response = _make_response(_make_text_block("Got it, I'll remember that."))

        client.messages.create = AsyncMock(side_effect=[tool_response, text_response])

        state = InnerDialogState()
        notification = _make_notification("My name is Alice")

        new_state = asyncio.run(
            process_notification(
                state=state,
                notification=notification,
                system_prompt="You are a helpful agent.",
                tool_executor=MockToolExecutor(),
                client=client,
                model=ModelName("claude-sonnet-4-5-20250514"),
            )
        )

        # Should have: notification, tool_call_response, tool_result, final_response
        assert len(new_state.messages) == 4

    def test_preserves_existing_state(self) -> None:
        """Test that existing messages in state are preserved."""
        client = AsyncMock()
        client.messages.create = AsyncMock(return_value=_make_response(_make_text_block("ok")))

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
                client=client,
                model=ModelName("claude-sonnet-4-5-20250514"),
            )
        )

        # 2 existing + 1 notification + 1 response = 4
        assert len(new_state.messages) == 4


class TestCompactInnerDialog:
    def test_compact_when_short(self) -> None:
        """Test that compaction is a no-op when history is short."""
        client = AsyncMock()
        state = InnerDialogState(
            messages=({"role": "user", "content": "hello"},),
        )

        result = asyncio.run(
            compact_inner_dialog(
                state=state,
                client=client,
                model=ModelName("claude-sonnet-4-5-20250514"),
                messages_to_preserve=10,
            )
        )

        assert result == state
        client.messages.create.assert_not_called()

    def test_compact_when_long(self) -> None:
        """Test that compaction summarizes older messages."""
        client = AsyncMock()
        summary_block = MagicMock()
        summary_block.text = "Summary of conversation."
        client.messages.create = AsyncMock(return_value=MagicMock(content=[summary_block]))

        messages: tuple[dict[str, Any], ...] = tuple(
            {"role": "user" if i % 2 == 0 else "assistant", "content": f"msg {i}"} for i in range(20)
        )
        state = InnerDialogState(messages=messages)

        result = asyncio.run(
            compact_inner_dialog(
                state=state,
                client=client,
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
        # Should be truncated to 200 chars
        assert len(summary) < len(long_content)
